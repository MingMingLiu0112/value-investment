"""Replay retained accounting bridges for an exact pending candidate, never approve it."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
import json
from pathlib import Path

from ..product.common import load_json_object
from ..product.source_bound_inputs import verify_package_local_sources
from .value_research_analysis import _available, _bound, load_current_value_research_analysis
from ...domain.research.issuer_identity import source_identity_matches_registered_issuer


SCHEMA = "economic-review-bundle-v1"
BRIDGE_VERSION = "600519-parent-distribution-capital-bridge-v1"
MAPPING_VERSION = "economic-bridge-original-catalog-mapping-v1"


def _bridge_entries(analysis):
    catalog = analysis["source_catalog"]
    binding = analysis.get("financial_summary", {}).get("parent_distribution_capital_research_binding")
    if binding is None:
        return [s for s in catalog if str(s.get("local_path", "")).endswith(
            "/parent-distribution-capital-bridge-v1.json")]
    if not isinstance(binding, dict) or set(binding) != {"id", "path", "sha256"}:
        raise ValueError("Bridge discovery requires exact id/path/hash binding")
    entries = [s for s in catalog if s["id"] == binding["id"]]
    if not entries or any((s["local_path"], s["sha256"]) !=
                          (binding["path"], binding["sha256"]) for s in entries):
        raise ValueError("Bridge discovery differs from bound source catalog")
    return entries


def _verify_original_period(path, source, issuer):
    # This bounded adapter verifies document identity/period, NOT financial rows.
    from pypdf import PdfReader

    reader = PdfReader(path)
    text = "".join("".join((page.extract_text() or "").split()) for page in reader.pages[:3])
    if not isinstance(issuer, str) or not issuer or "".join(issuer.split()) not in text:
        raise ValueError("Bridge original PDF issuer mismatch")
    period = source.get("report_period")
    headings = {"2025-01-01/2025-12-31": "2025年年度报告",
                "2026-01-01/2026-06-30": "2026年半年度报告"}
    if period is not None:
        if period not in headings or headings[period] not in text:
            raise ValueError("Bridge original PDF report period mismatch")
    else:
        day = source.get("assessment_balance_date")
        if not isinstance(day, str):
            raise ValueError("Bridge original requires report or assessment period")
        from datetime import date

        parsed = date.fromisoformat(day)
        if not any(token + "财务报表" in text for token in (day, f"{parsed.year}年{parsed.month}月{parsed.day}日",
                   f"{parsed.year}年{parsed.month:02d}月{parsed.day:02d}日")):
            raise ValueError("Bridge original PDF assessment period mismatch")


def _map_originals(*, root, bridge, catalog, symbol):
    """Adapt verified content-addressed originals only, retaining frozen lineage."""
    adapted = deepcopy(bridge)
    mappings = []
    for original, target in zip(bridge["sources"], adapted["sources"]):
        aliases = [s for s in catalog if s["sha256"] == original["sha256"]]
        pairs = {(s["local_path"], s["sha256"]) for s in aliases}
        if len(pairs) != 1:
            raise ValueError("Bridge original missing or ambiguous catalog copy")
        official = []
        for entry in aliases:
            if entry.get("kind") == "official_issuer_filing":
                if (entry.get("location") != original["source_url"]
                        or not source_identity_matches_registered_issuer(symbol=symbol,
                            location=entry["location"], issuer_identity=entry.get("issuer_identity") or {})):
                    raise ValueError("Bridge original catalog URL or issuer conflict")
                official.append(entry)
            elif (entry.get("kind") != "research_artifact"
                    or entry.get("location") != entry["local_path"]
                    or entry.get("issuer_identity") is not None):
                raise ValueError("Bridge original lineage alias metadata conflict")
            for key in ("report_period", "assessment_balance_date"):
                if key in entry and entry[key] != original.get(key):
                    raise ValueError("Bridge original catalog period conflict")
        if not official:
            raise ValueError("Bridge original requires an official issuer source, not hash-only aliases")
        path, digest = next(iter(pairs))
        current = {"path": path, "sha256": digest}
        actual = _bound(root, current)
        _verify_original_period(actual, original, bridge.get("issuer"))
        target["path"] = path
        mappings.append(dict(source_id=original["id"],
            original_binding={k: original[k] for k in ("path", "sha256")},
            catalog_binding=current, catalog_source_ids=sorted(s["id"] for s in aliases),
            source_url=original["source_url"], report_period=original.get("report_period"),
            assessment_balance_date=original.get("assessment_balance_date"),
            issuer_identity=deepcopy(official[0]["issuer_identity"]),
            official_source_ids=sorted(s["id"] for s in official),
            availability_evidence=[{k: s.get(k) for k in ("id", "source_available_at", "retrieved_at")}
                                   for s in sorted(aliases, key=lambda s: s["id"])],
            assurance="ORIGINAL_IDENTITY_AND_PERIOD_NOT_PDF_ROW_CERTIFICATION"))
    return adapted, dict(version=MAPPING_VERSION, originals=mappings,
                         frozen_bridge_bytes_changed=False)


def _decimal(value):
    if not isinstance(value, str):
        raise ValueError("Bridge amounts require decimal strings")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("Invalid bridge amount") from error
    if not number.is_finite():
        raise ValueError("Bridge amount must be finite")
    return number


def _unknowns(value, path=""):
    if value is None:
        return [path]
    if isinstance(value, dict):
        return [p for key, item in value.items() for p in _unknowns(item, f"{path}/{key}")]
    if isinstance(value, list):
        return [p for index, item in enumerate(value) for p in _unknowns(item, f"{path}/{index}")]
    return []


def _replay(bridge, analysis):
    sources = {s["id"]: s for s in bridge["sources"]}
    if len(sources) != len(bridge["sources"]):
        raise ValueError("Duplicate bridge source")
    results = []
    seen = set()
    for kind, rows in (("parent_cash", bridge["parent_cash_bridges"]),
                       ("equity", bridge["equity_bridges"])):
        for index, row in enumerate(rows):
            key = (kind, row["period"], row["entity_scope"])
            if key in seen:
                raise ValueError("Duplicate bridge period/scope")
            seen.add(key)
            source = sources[row["source_id"]]
            period = {"FY2025": "2025-01-01/2025-12-31",
                      "H1_2026": "2026-01-01/2026-06-30"}.get(row["period"])
            if period is None or source.get("report_period") != period:
                raise ValueError("Bridge period differs from filing")
            scope = row["entity_scope"]
            if scope not in {"issuer_parent_standalone", "consolidated_attributable_to_parent"}:
                raise ValueError("Unsupported bridge ownership scope")
            pages = row.get("physical_pages", [row.get("physical_page")])
            if not pages or any(type(p) is not int or p < 1 for p in pages):
                raise ValueError("Bridge requires positive physical pages")
            if kind == "parent_cash":
                if scope != "issuer_parent_standalone":
                    raise ValueError("Parent cash cannot use consolidated scope")
                fields = ["opening_cash_and_equivalents_cny", "cfo_cny", "cfi_cny", "cff_cny"]
                residual_field = "fx_effect_reconciliation_residual_cny"
                reported_field = "fx_effect_reported_cny"
                closing_field = "closing_cash_and_equivalents_cny"
            else:
                fields = ["opening_equity_cny", "net_profit_cny", "distribution_signed_cny",
                          "net_owner_capital_change_signed_cny"]
                residual_field = ("oci_and_other_reconciliation_residual_cny"
                                  if scope == "issuer_parent_standalone" else "oci_cny")
                reported_field = "oci_reported_cny" if scope == "issuer_parent_standalone" else "oci_cny"
                closing_field = "closing_equity_cny"
            terms = {f: row[f] for f in fields}
            computed_residual = _decimal(row[closing_field]) - sum(
                (_decimal(v) for v in terms.values()), Decimal(0))
            if computed_residual != _decimal(row[residual_field]):
                raise ValueError("Bridge residual does not reconcile")
            if row.get(reported_field) is not None and _decimal(row[reported_field]) != computed_residual:
                raise ValueError("Reported bridge adjustment differs from residual")
            closing = sum((_decimal(v) for v in terms.values()), computed_residual)
            if closing != _decimal(row[closing_field]):
                raise ValueError("Bridge closing balance mismatch")
            if kind == "parent_cash":
                net = closing - _decimal(row[fields[0]])
                if net != _decimal(row["reported_net_change_cny"]):
                    raise ValueError("Cash net change differs")
            if _decimal(row.get("reconciliation_difference_cny",
                                row.get("closing_reconciliation_difference_cny"))) != 0:
                raise ValueError("Research bridge reports an unexplained difference")
            results.append(dict(kind=kind, period=row["period"], entity_scope=scope,
                unit="CNY", source_binding={k: source[k] for k in ("path", "sha256")},
                source_url=source["source_url"], report_period=period, physical_pages=pages,
                terms=terms, reported_adjustment=row.get(reported_field),
                derived_adjustment_cny=str(computed_residual),
                computed_closing_cny=str(closing), reported_closing_cny=row[closing_field],
                difference_cny=str(closing - _decimal(row[closing_field])),
                evidence_pointer=f"/{'parent_cash_bridges' if kind == 'parent_cash' else 'equity_bridges'}/{index}",
                assurance="BOUND_RESEARCH_ARITHMETIC_NOT_NEW_PDF_ROW_CERTIFICATION"))
    expected = {(kind, period, scope)
        for period in ("FY2025", "H1_2026")
        for kind, scope in (("parent_cash", "issuer_parent_standalone"),
                            ("equity", "issuer_parent_standalone"),
                            ("equity", "consolidated_attributable_to_parent"))}
    if seen != expected:
        raise ValueError("Bridge must cover both periods and separate ownership scopes")
    for kind, scope in {(key[0], key[2]) for key in seen}:
        original = bridge["parent_cash_bridges" if kind == "parent_cash" else "equity_bridges"]
        by_period = {r["period"]: r for r in original if r["entity_scope"] == scope}
        prefix = "cash_and_equivalents" if kind == "parent_cash" else "equity"
        if _decimal(by_period["FY2025"][f"closing_{prefix}_cny"]) != _decimal(
                by_period["H1_2026"][f"opening_{prefix}_cny"]):
            raise ValueError("Bridge cross-period continuity mismatch")
    latest = next(r for r in results if r["kind"] == "equity" and r["period"] == "H1_2026"
                  and r["entity_scope"] == "consolidated_attributable_to_parent")
    if _decimal(latest["computed_closing_cny"]) != _decimal(
            str(analysis["consumed_operating_inputs"]["start_book_equity"])):
        raise ValueError("Bridge closing equity differs from consumed model equity")
    return results


def build_current_economic_review_bundle(*, root: Path, symbol: str, now: datetime) -> dict:
    """No writes/network or caller-provided facts; use the registered candidate only.

    The historical research has its own older model binding. Carry it as lineage,
    not as approval of this candidate. Source identity and arithmetic can be
    revalidated now without pretending this review existed at a historical cutoff.
    """
    if now.utcoffset() is None:
        raise ValueError("Review cutoff requires timezone")
    root = root.resolve()
    analysis = load_current_value_research_analysis(root=root, symbol=symbol, now=now)
    if analysis is None:
        raise ValueError("No registered pending valuation candidate")
    return _build_economic_review_bundle(root=root, analysis=analysis, now=now)


def _build_economic_review_bundle(*, root: Path, analysis: dict, now: datetime) -> dict:
    """Internal reuse of loader-verified inputs, with binding/cutoff rechecks."""
    if now.utcoffset() is None:
        raise ValueError("Review cutoff requires timezone")
    candidate = load_json_object(_bound(root, analysis["review_binding"]["candidate_binding"]),
                                 "economic review candidate")
    if (candidate["model_context"]["input_descriptor_sha256"] != analysis["input_descriptor_sha256"]
            or candidate["symbol"] != analysis["symbol"] or analysis["action"] != "no_order"):
        raise ValueError("Economic review descriptor or candidate identity mismatch")
    _available(candidate["generated_at"], now)
    for binding in analysis["review_binding"].values():
        if isinstance(binding, dict) and set(binding) == {"path", "sha256"}:
            _bound(root, binding)
    catalog = analysis["source_catalog"]
    for source in catalog:
        for field in ("source_available_at", "retrieved_at", "published_at"):
            if source.get(field):
                _available(source[field], now)
    verify_package_local_sources(root, {"sources": catalog})
    aliases = _bridge_entries(analysis)
    for source in aliases:
        for field in ("source_available_at", "retrieved_at", "published_at"):
            if source.get(field):
                _available(source[field], now)
    candidates = list({(s["local_path"], s["sha256"]): s for s in aliases}.values())
    if len(candidates) > 1:
        raise ValueError("Ambiguous bridge source")
    output = dict(schema_version=SCHEMA, symbol=analysis["symbol"], action="no_order",
        evaluated_at=now.isoformat(), input_descriptor_sha256=analysis["input_descriptor_sha256"],
        review_binding=deepcopy(analysis["review_binding"]),
        source_bindings=deepcopy(analysis["source_bindings"]),
        status="NO_SUPPORTED_BOUND_BRIDGE", bridge_results=[], unknown_fields=[],
        future_distribution_capacity_cny=None, future_retained_capital_return=None,
        forward_economic_status="NOT_ESTABLISHED",
        coverage_status="NOT_COVERED_UNKNOWN_COMPLETENESS_NOT_ASSESSED",
        primary_valuation_usable=False, economic_approval_granted=False,
        approval_changed=False, strategy_admitted=False, action_admitted=False,
        scope="HISTORICAL_ACCOUNTING_REVIEW_NOT_FORWARD_ECONOMIC_ADMISSION",
        strict_contemporaneous_pit="NOT_PROVEN")
    if candidates:
        entry = candidates[0]
        for field in ("source_available_at", "retrieved_at", "published_at"):
            if entry.get(field):
                _available(entry[field], now)
        binding = dict(path=entry["local_path"], sha256=entry["sha256"])
        bridge = load_json_object(_bound(root, binding), "bound economic research bridge")
        if (bridge.get("symbol") != analysis["symbol"] or bridge.get("action") != "no_order"
                or bridge.get("unit") != "CNY" or bridge.get("research_version") != BRIDGE_VERSION
                or bridge.get("artifact_kind") != "independent_parent_distribution_capital_research"):
            raise ValueError("Bridge identity/version/unit mismatch")
        if bridge["research_date"] > now.date().isoformat():
            raise ValueError("Future bridge research date")
        indexed = {(s.get("local_path"), s["sha256"]) for s in catalog}
        replay_bridge = bridge
        mapping = None
        explicit_binding = analysis.get("financial_summary", {}).get(
            "parent_distribution_capital_research_binding")
        missing_original = any((s["path"], s["sha256"]) not in indexed for s in bridge["sources"])
        if missing_original and explicit_binding is None:
            raise ValueError("Bridge original is not bound to current candidate")
        if explicit_binding is not None:
            replay_bridge, mapping = _map_originals(root=root, bridge=bridge,
                catalog=catalog, symbol=analysis["symbol"])
        for source in replay_bridge["sources"]:
            if (source["path"], source["sha256"]) not in indexed:
                raise ValueError("Bridge original is not bound to current candidate")
            _bound(root, {k: source[k] for k in ("path", "sha256")})
            if source["published_date"] > now.date().isoformat():
                raise ValueError("Future bridge filing")
        with localcontext() as context:
            context.prec = 48
            results = _replay(replay_bridge, analysis)
        output.update(status="HISTORICAL_BRIDGES_REPLAYED_NOT_ECONOMIC_APPROVAL",
            coverage_status="SUPPORTED_HISTORICAL_BRIDGES_ONLY",
            bridge_binding=binding, bridge_results=results,
            historical_model_binding=deepcopy(bridge["model_binding"]),
            unknown_fields=_unknowns(bridge))
        if mapping is not None:
            output["original_catalog_mapping"] = mapping
    for binding in output["source_bindings"]:
        _bound(root, binding)
    payload = {k: v for k, v in output.items() if k != "evaluated_at"}
    output["bundle_sha256"] = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
        allow_nan=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return output
