"""Pinned annual/interim supplement from retained official cash receipts.

No acquisition, forecasts or scalar extraction from narrative. Selection lives in
configuration; replay uses the immutable manifest, never the current selection.
"""
from copy import deepcopy
from datetime import datetime, date, time, timedelta
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from . import operating_sources_v1 as base_sources
from .task_execution_v1 import _bytes, _hash
from .. import parent_cash_research as cash
from .. import parent_cash_observation_v2 as numbered_cash
from .. import parent_cash_observation_v3 as blank_safe_cash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import official_report_acquisition as receipts
from ....infrastructure.filings import operating_statement_basis_v1 as statements
from ....infrastructure.filings import parent_balance_basis_v1 as parent_balance
from ....infrastructure.filings import parent_balance_basis_v2 as numbered_balance
from ....infrastructure.filings import parent_income_basis_v1 as numbered_income
from ....infrastructure.filings import parent_income_basis_v2 as unnumbered_income
from ....infrastructure.filings import pdf_text, pdfium_runtime, official_pdf
from ....domain.valuation import parent_cash_policy

VERSION = "operating-horizon-sources-v1"
CONFIG = "config/current-operating-horizon-sources-v1.json"
# The bounded 000568 pair serializes to 54,952 characters; the 600519 FY/H1
# pair with exact parent income, balance and cash rows measures 60,580.
# Retain full provenance under a measured hard cap; never truncate source rows.
MAX_CONTEXT_CHARS = 64000


def implementation():
    modules = (base_sources, cash, numbered_cash, blank_safe_cash, receipts, receipts.disclosures, statements, parent_balance,
               numbered_balance, numbered_income, unnumbered_income, pdf_text,
               pdfium_runtime, official_pdf, parent_cash_policy)
    return {**{m.__name__: _hash(Path(m.__file__).read_bytes()) for m in modules},
            __name__: _hash(Path(__file__).read_bytes())}


def _bound(root, pin):
    if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
            or not isinstance(pin["path"], str) or Path(pin["path"]).is_absolute()
            or ".." in Path(pin["path"]).parts
            or not isinstance(pin["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
        raise ValueError("HORIZON_SOURCE_BINDING_INVALID")
    path = require_inside(root, root / pin["path"], "horizon source")
    raw = path.read_bytes()
    if _hash(raw) != pin["sha256"]:
        raise ValueError("HORIZON_SOURCE_HASH_CHANGED")
    return json.loads(raw)


def _clock(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError("HORIZON_SOURCE_NOT_YET_ACQUIRED")
    return stamp


def _excerpt(page, selection):
    """Exact contiguous span, at line/paragraph boundaries; never size slicing."""
    if (set(selection) != {"period", "physical_page", "start_marker", "end_marker"}
            or type(selection["physical_page"]) is not int
            or not 1 <= selection["physical_page"] <= 600):
        raise ValueError("HORIZON_EXCERPT_SELECTION_INVALID")
    def offset(marker):
        if not isinstance(marker, str) or not 1 <= len(marker) <= 200 or page.count(marker) != 1:
            raise ValueError("HORIZON_EXCERPT_MARKER_MISSING_OR_AMBIGUOUS")
        position = page.index(marker)
        if position and page[position-1] not in "\r\n":
            raise ValueError("HORIZON_EXCERPT_MUST_START_ON_FULL_LINE")
        return position
    start = offset(selection["start_marker"])
    end = len(page) if selection["end_marker"] is None else offset(selection["end_marker"])
    text = page[start:end]
    if (end <= start or not text.strip() or len(text) > 2000
            or not text.rstrip().endswith(("。", "！", "？", ".", "!", "?"))):
        raise ValueError("HORIZON_EXCERPT_INCOMPLETE_OR_OVER_BUDGET")
    return text, start, end


def _fact(row):
    keys = ("id", "source_id", "pdf_sha256", "available_at", "period", "scope", "unit", "text",
            "physical_page", "physical_pages", "period_basis", "field", "value",
            "derivation_formula", "assurance_basis", "verification_method", "native_kind")
    result = {k: deepcopy(row[k]) for k in keys if k in row}
    if ("value" not in result or "physical_page" not in result
            or not isinstance(result.get("text"), str) or not 1 <= len(result["text"]) <= 2000):
        raise ValueError("HORIZON_REPORTED_FACT_PROVENANCE_REQUIRED")
    result.update(kind=row.get("kind", "SOURCE_BOUND_SCALAR_NOT_ECONOMIC_APPROVAL"),
                  text_sha256=_hash(result["text"].encode("utf-8")))
    return result


def _selection(value):
    required = {"issuer_name", "parent_cash_observation_receipts", "excerpts"}
    allowed = required | {"scope_decomposition", "parent_cash_layout", "parent_balance_layout",
                          "parent_income_layout", "base_fact_fields", "supplement_fact_fields",
                          "prior_conditional_assumption_binding"}
    if (not isinstance(value, dict)
            or not required <= set(value) or not set(value) <= allowed
            or not isinstance(value["issuer_name"], str) or not value["issuer_name"].strip()
            # Bound the evidence context but retain both operating and parent-cash
            # anchors from the annual/interim filing pair.
            or not isinstance(value["excerpts"], list) or not 0 <= len(value["excerpts"]) <= 20
            or not isinstance(value["parent_cash_observation_receipts"], list)
            or not 1 <= len(value["parent_cash_observation_receipts"]) <= 3):
        raise ValueError("HORIZON_SOURCE_SELECTION_REQUIRED")
    layout = value.get("parent_cash_layout", "LEGACY_V1")
    if layout not in {"LEGACY_V1", "LEGACY_BLANK_SAFE_V3", "NUMBERED_CNINFO_V2"} or (not value["excerpts"] and layout == "LEGACY_V1"):
        raise ValueError("HORIZON_SOURCE_LAYOUT_OR_EXCERPTS_INVALID")
    balance_layout = value.get("parent_balance_layout", "LEGACY_V1")
    if balance_layout not in {"LEGACY_V1", "NUMBERED_CNINFO_V2"} or (balance_layout == "NUMBERED_CNINFO_V2" and layout != "NUMBERED_CNINFO_V2"):
        raise ValueError("HORIZON_PARENT_BALANCE_LAYOUT_INVALID")
    income_layout = value.get("parent_income_layout")
    if income_layout not in (None, "NUMBERED_CNINFO_V1", "UNNUMBERED_CONTINUATION_V2") or (
            income_layout == "NUMBERED_CNINFO_V1" and layout != "NUMBERED_CNINFO_V2") or (
            income_layout == "UNNUMBERED_CONTINUATION_V2" and layout != "LEGACY_BLANK_SAFE_V3"):
        raise ValueError("HORIZON_PARENT_INCOME_LAYOUT_INVALID")
    fields = value.get("base_fact_fields")
    if fields is not None and (layout != "NUMBERED_CNINFO_V2" or not isinstance(fields, list)
            or not 1 <= len(fields) <= 20 or len(set(fields)) != len(fields)
            or any(not isinstance(field, str) or not re.fullmatch(r"[a-z_]{2,50}", field)
                   for field in fields)):
        raise ValueError("HORIZON_BASE_FACT_SELECTION_INVALID")
    supplement_fields = value.get("supplement_fact_fields")
    if supplement_fields is not None and (not isinstance(supplement_fields, list)
            or not 1 <= len(supplement_fields) <= 30
            or len(set(supplement_fields)) != len(supplement_fields)
            or any(not isinstance(field, str) or not re.fullmatch(r"[a-z_]{2,50}", field)
                   for field in supplement_fields)):
        raise ValueError("HORIZON_SUPPLEMENT_FACT_SELECTION_INVALID")
    # This is intentionally only an immutable source selection.  The domain
    # contract validates its economics after the selected evidence IDs have
    # actually been reconstructed below; it is never inferred from a missing
    # acquisition disclosure or from model output.
    if "scope_decomposition" in value and not isinstance(value["scope_decomposition"], dict):
        raise ValueError("HORIZON_SCOPE_DECOMPOSITION_SELECTION_INVALID")
    if "prior_conditional_assumption_binding" in value:
        pin = value["prior_conditional_assumption_binding"]
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256"}):
            raise ValueError("HORIZON_PRIOR_ASSUMPTION_BINDING_INVALID")
    keys = [(e["period"], e["physical_page"]) for e in value["excerpts"]]
    if len(set(keys)) != len(keys):
        raise ValueError("HORIZON_DUPLICATE_PAGE_SELECTION")
    return deepcopy(value)


def _prior_conditional_hypothesis(root, selection, symbol, basis, sources, now):
    """Carry an old conditional stress as a challengeable hypothesis, never fact."""
    pin = selection.get("prior_conditional_assumption_binding")
    if pin is None:
        return None
    previous = _bound(root, pin)
    if (previous.get("schema_version") != "first-research-assumptions-v1"
            or previous.get("action") != "no_order" or previous.get("symbol") != symbol
            or previous.get("financial_basis") != basis
            or previous.get("assumption_scope") != "RESEARCH_ASSUMPTIONS_NOT_OFFICIAL_FORECAST"):
        raise ValueError("HORIZON_PRIOR_ASSUMPTION_IDENTITY_INVALID")
    _clock(previous.get("generated_at"), now)
    source_hashes = {source["sha256"] for source in sources}
    prior_hashes = {item.get("sha256") for item in previous.get("source_bindings", [])
                    if isinstance(item, dict)}
    if not source_hashes <= prior_hashes:
        raise ValueError("HORIZON_PRIOR_ASSUMPTION_SOURCES_NOT_RECONCILED")
    result = {}
    for scenario in ("bear", "base", "bull"):
        years = previous.get("scenarios", {}).get(scenario, {}).get("drivers", {}).get("years")
        if not isinstance(years, list) or not years or years[0].get("year") != 1:
            raise ValueError("HORIZON_PRIOR_ASSUMPTION_YEAR_INVALID")
        keys = ("target_payout_ratio", "accessible_profit_ratio", "reserve_ratio",
                "net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny")
        if any(not isinstance(years[0].get(key), str) for key in keys):
            raise ValueError("HORIZON_PRIOR_ASSUMPTION_TERMS_INCOMPLETE")
        result[scenario] = {key: years[0][key] for key in keys}
    return dict(binding=deepcopy(pin), generated_at=previous["generated_at"],
        financial_basis=basis, forecast_year=date.fromisoformat(basis).year + 1,
        scenario_first_year=result,
        scope="OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY",
        limitation="Prior numbers are not official facts, current approval, or a policy default; each must be independently justified or rejected.")


def _supplement(root, symbol, selection, now):
    bindings = selection["parent_cash_observation_receipts"]
    # Existing cash receipt replay first: discovery indexes, issuer, original and
    # parent-statement provenance are checked before any new excerpt is consumed.
    if selection.get("parent_cash_layout") == "NUMBERED_CNINFO_V2":
        cash_result = numbered_cash.replay_numbered_parent_cash_observations(
            root=root, symbol=symbol, issuer_name=selection["issuer_name"],
            receipt_bindings=bindings, now=now)
    elif selection.get("parent_cash_layout") == "LEGACY_BLANK_SAFE_V3":
        cash_result = blank_safe_cash.replay_blank_safe_parent_cash_observations(
            root=root, symbol=symbol, issuer_name=selection["issuer_name"],
            receipt_bindings=bindings, now=now)
    else:
        cash_result = cash.replay_bound_parent_cash_observations(root=root, symbol=symbol,
            issuer_name=selection["issuer_name"], receipt_bindings=bindings, now=now)
    evidence, sources, gaps = [], [], []
    periods = {item["period"] for item in bindings}
    if any(e["period"] not in periods for e in selection["excerpts"]):
        raise ValueError("HORIZON_EXCERPT_RECEIPT_MISSING")
    for item in bindings:
        period, pin = item["period"], item["receipt_binding"]
        query = cash._receipt_issuer_query(root=root, receipt_binding=pin)
        packet = receipts.load_retained_official_report(root=root, receipt_binding=pin,
            symbol=symbol, issuer_name=query, period=period)
        clocks = [_clock(packet[k], now) for k in ("fetched_at", "completed_at")]
        clocks.append(_clock(packet["source"]["available_at"], now))
        published = datetime.combine(date.fromisoformat(packet["published_date"]) + timedelta(days=1),
                                     time(), ZoneInfo("Asia/Shanghai"))
        clocks.append(_clock(published.isoformat(), now))
        available = max(clocks).isoformat()
        source = dict(packet["source"], available_at=available)
        original = require_inside(root, root / source["path"], "horizon original")
        if _hash(original.read_bytes()) != source["sha256"]:
            raise ValueError("HORIZON_SOURCE_HASH_CHANGED")
        # The new blank-safe receipt path reads the annual basis as well as
        # H1 through the same authenticated statement parser. Earlier paths
        # keep their original H1-only selection and task semantics.
        if period.endswith("-06-30") or selection.get("parent_cash_layout") == "LEGACY_BLANK_SAFE_V3":
            report = statements.load_operating_statement_basis(root=root, source=source, evaluation_at=now)
            if (report.get("symbol") != symbol or report.get("source_binding") != source
                    or report.get("action") != "no_order" or report.get("financial_quality_granted") is not False):
                raise ValueError("HORIZON_STATEMENT_BINDING_INVALID")
            for row in report["evidence"]:
                if (row.get("pdf_sha256") != source["sha256"]
                        or row.get("period_basis") != ("FY" if period.endswith("-12-31") else "H1")
                        or row.get("available_at") != available or row.get("source_binding") != source):
                    raise ValueError("HORIZON_STATEMENT_ROW_BINDING_INVALID")
                evidence.append(dict(_fact(row), receipt_binding=deepcopy(pin)))
            gaps.extend(dict(gap, report_period=period) for gap in report["gaps"])
        selected = [e for e in selection["excerpts"] if e["period"] == period]
        if (selected or selection.get("parent_balance_layout") == "NUMBERED_CNINFO_V2"
                or selection.get("parent_income_layout") in {"NUMBERED_CNINFO_V1", "UNNUMBERED_CONTINUATION_V2"}):
            page_limit = max((e["physical_page"] for e in selected), default=0)
            if (selection.get("parent_balance_layout") == "NUMBERED_CNINFO_V2"
                    or selection.get("parent_income_layout") in {"NUMBERED_CNINFO_V1", "UNNUMBERED_CONTINUATION_V2"}):
                page_limit = max(page_limit, 100)
            pages = pdf_text.extract_pages(original, limit=page_limit)
            balance_parser = (numbered_balance.extract_numbered_parent_balance_facts
                              if selection.get("parent_balance_layout") == "NUMBERED_CNINFO_V2"
                              else parent_balance.extract_parent_balance_facts)
            balance = balance_parser(pages=pages, source=source,
                                     source_id=packet["source_id"], issuer_name=selection["issuer_name"])
            for row in balance["evidence"]:
                evidence.append(dict(_fact(row), receipt_binding=deepcopy(pin)))
            gaps.extend(dict(reason=reason, report_period=period)
                        for reason in balance["gaps"])
            if selection.get("parent_income_layout") == "NUMBERED_CNINFO_V1":
                income = numbered_income.extract_numbered_parent_income_facts(
                    pages=pages, source=source, source_id=packet["source_id"])
                for row in income["evidence"]:
                    evidence.append(dict(_fact(row), receipt_binding=deepcopy(pin)))
                gaps.extend(dict(reason=reason, report_period=period) for reason in income["gaps"])
            elif selection.get("parent_income_layout") == "UNNUMBERED_CONTINUATION_V2":
                income = unnumbered_income.extract_unnumbered_parent_income_facts(
                    pages=pages, source=source, source_id=packet["source_id"])
                for row in income["evidence"]:
                    evidence.append(dict(_fact(row), receipt_binding=deepcopy(pin)))
                gaps.extend(dict(reason=reason, report_period=period) for reason in income["gaps"])
            for entry in selected:
                number = entry["physical_page"]
                if len(pages) < number:
                    raise ValueError("HORIZON_EXCERPT_PAGE_MISSING")
                text, start, end = _excerpt(pages[number-1], entry)
                evidence.append(dict(id=packet["source_id"] + ":horizon-p" + str(number),
                    source_id=packet["source_id"], pdf_sha256=source["sha256"], physical_page=number,
                    available_at=available, acquired_at=packet["fetched_at"], period=period,
                    period_basis="H1" if period.endswith("-06-30") else "FY",
                    scope="ISSUER_REPORTED_NARRATIVE", unit="TEXT", text=text,
                    text_sha256=_hash(text.encode("utf-8")), page_text_sha256=_hash(pages[number-1].encode("utf-8")),
                    start_offset=start, end_offset=end, excerpt_truncated=False,
                    kind="OFFICIAL_EXCERPT_NOT_VERIFIED_ECONOMIC_CLAIM", receipt_binding=deepcopy(pin)))
        if _hash(original.read_bytes()) != source["sha256"]:
            raise ValueError("HORIZON_ORIGINAL_CHANGED_DURING_EXTRACTION")
        _bound(root, pin)
        sources.append(dict(source, receipt_binding=deepcopy(pin), source_id=packet["source_id"],
                            acquired_at=packet["fetched_at"], completed_at=packet["completed_at"]))
    if selection.get("parent_cash_layout") in {"NUMBERED_CNINFO_V2", "LEGACY_BLANK_SAFE_V3"}:
        selected_fields = {"cfo_cny", "gross_capex_cny", "investment_income_cash_cny",
            "mixed_distribution_interest_paid_cny", "opening_cash_and_equivalents_cny",
            "closing_cash_and_equivalents_cny", "debt_repaid_cny", "borrowings_received_cny"}
        source_by_id = {source["source_id"]: source for source in sources}
        for statement in cash_result["historical_statements"]:
            ref = statement["source_binding"]
            source = source_by_id[ref["source_id"]]
            current_period = "2025-12-31" if statement["periods"][0] == "FY2025" else "2026-06-30"
            for field, row in statement["rows"].items():
                if field not in selected_fields:
                    continue
                text = row["evidence_excerpt"]
                evidence.append(dict(id=ref["source_id"] + ":parent-cash-v2:" + field,
                    source_id=ref["source_id"], pdf_sha256=source["sha256"],
                    physical_page=row["physical_page"], available_at=source["available_at"],
                    period=current_period, period_basis="FY" if current_period.endswith("12-31") else "H1",
                    scope="ISSUER_PARENT_STANDALONE", unit="CNY", field=field,
                    value=row["columns"][0]["value"], text=text,
                    text_sha256=_hash(text.encode("utf-8")),
                    kind="SOURCE_BOUND_PARENT_CASH_OBSERVATION_NOT_POLICY",
                    receipt_binding=deepcopy(source["receipt_binding"])))
            for field in statement.get("ambiguous_printed_columns", statement.get("unknown_fields", [])):
                gaps.append(dict(reason="PARENT_CASH_PRINTED_COLUMN_AMBIGUOUS:" + field,
                                 report_period=current_period))
    return evidence, sources, gaps


def _receipt_operating_base(root, symbol, selection, now):
    """Anchor a receipt-native D2 context without copying reported values.

    The normal supplement replays both official originals and supplies every
    fact. This lightweight base only pins the latest reporting period so the
    existing horizon manifest/replay contract remains unchanged.
    """
    items = selection["parent_cash_observation_receipts"]
    periods = [item["period"] for item in items]
    if (len(items) != 2 or set(periods) != {"2025-12-31", "2026-06-30"}):
        raise ValueError("HORIZON_RECEIPT_BASE_PERIODS_REQUIRED")
    latest = next(item for item in items if item["period"] == "2026-06-30")
    pin = latest["receipt_binding"]
    query = cash._receipt_issuer_query(root=root, receipt_binding=pin)
    report = receipts.load_retained_official_report(root=root, receipt_binding=pin,
        symbol=symbol, issuer_name=query, period="2026-06-30")
    _clock(report["completed_at"], now)
    return dict(schema_version="operating-official-receipt-base-v1", symbol=symbol,
        issuer_name=selection["issuer_name"], as_of=now.isoformat(),
        financial_basis="2026-06-30", source_binding=deepcopy(pin),
        evidence=[], action="no_order", formal_eligibility=False)


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if now.utcoffset() is None or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("HORIZON_SOURCE_IDENTITY_OR_CLOCK_INVALID")
    if binding is None:
        config = require_inside(root, root / CONFIG, "horizon source selection")
        raw = config.read_bytes()
        registry = json.loads(raw)
        if registry.get("schema_version") != VERSION or registry.get("action") != "no_order":
            raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
        selection = _selection(registry["cases"].get(symbol))
        base = (_receipt_operating_base(root, symbol, selection, now)
                if selection.get("parent_cash_layout") == "LEGACY_BLANK_SAFE_V3"
                else base_sources.build_operating_source_context(root=root, symbol=symbol, now=now))
        manifest = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=selection, selected_from=dict(path=CONFIG, sha256=_hash(raw)),
            implementation_sha256=implementation(), action="no_order")
        raw = _bytes(manifest)
        path = require_inside(root, root / "runtime" / VERSION / (_hash(raw) + ".json"), "horizon manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = _bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("symbol") != symbol
                or manifest.get("as_of") != now.isoformat() or manifest.get("action") != "no_order"
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("HORIZON_SOURCE_MANIFEST_OR_IMPLEMENTATION_CHANGED")
        selection = _selection(manifest["selection"])
        base = (_receipt_operating_base(root, symbol, selection, now)
                if selection.get("parent_cash_layout") == "LEGACY_BLANK_SAFE_V3"
                else base_sources.build_operating_source_context(root=root, symbol=symbol, now=now,
                                                                  binding=manifest["base_binding"]))
        path = None
    if (base["symbol"] != symbol or base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("HORIZON_BASE_CONTEXT_CHANGED")
    extra, sources, gaps = _supplement(root, symbol, selection, now)
    # Replace automatic first-page narrative sampling with complete curated spans.
    selected_fields = set(selection["base_fact_fields"]) if "base_fact_fields" in selection else None
    evidence = [_fact(row) for row in base["evidence"] if "field" in row and "value" in row
                and (selected_fields is None or row["field"] in selected_fields)]
    if selected_fields is not None and selected_fields - {row["field"] for row in evidence}:
        raise ValueError("HORIZON_SELECTED_BASE_FACT_MISSING")
    supplement_fields = set(selection["supplement_fact_fields"]) if "supplement_fact_fields" in selection else None
    if supplement_fields is not None:
        extra = [row for row in extra if row.get("field") in supplement_fields]
        if supplement_fields - {row["field"] for row in extra}:
            raise ValueError("HORIZON_SELECTED_SUPPLEMENT_FACT_MISSING")
    evidence.extend(extra)
    if not evidence or len(evidence) > 100 or len({r["id"] for r in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    for row in evidence:
        _clock(row["available_at"], now)
    prior = _prior_conditional_hypothesis(root, selection, symbol, base["financial_basis"],
                                          sources, now)
    value = dict(schema_version=VERSION, symbol=symbol, issuer_name=selection["issuer_name"],
        as_of=now.isoformat(), financial_basis=base["financial_basis"], source_binding=deepcopy(binding),
        base_source_binding=deepcopy(manifest["base_binding"]), supplemental_sources=sources,
        parent_cash_observation_receipts=deepcopy(selection["parent_cash_observation_receipts"]),
        evidence=evidence, statement_basis_gaps=gaps, implementation_sha256=manifest["implementation_sha256"],
        scope_decomposition=deepcopy(selection.get("scope_decomposition")),
        prior_conditional_hypothesis=prior,
        action="no_order", formal_eligibility=False,
        limitations=["Interim consolidated facts are H1, never full-year actuals or annualized forecasts",
            "Narrative is issuer disclosure, not verified economic claims or independent review",
            "No current-event completeness, valuation, approval or cash capacity inferred"])
    value["snapshot_fingerprint"] = _hash(_bytes(value))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("HORIZON_SOURCE_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value

