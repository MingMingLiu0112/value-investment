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
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import official_report_acquisition as receipts
from ....infrastructure.filings import operating_statement_basis_v1 as statements
from ....infrastructure.filings import pdf_text, pdfium_runtime, official_pdf
from ....domain.valuation import parent_cash_policy

VERSION = "operating-horizon-sources-v1"
CONFIG = "config/current-operating-horizon-sources-v1.json"
MAX_CONTEXT_CHARS = 48000


def implementation():
    modules = (base_sources, cash, receipts, receipts.disclosures, statements, pdf_text,
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
    if (not isinstance(value, dict)
            or set(value) != {"issuer_name", "parent_cash_observation_receipts", "excerpts"}
            or not isinstance(value["issuer_name"], str) or not value["issuer_name"].strip()
            or not isinstance(value["excerpts"], list) or not 1 <= len(value["excerpts"]) <= 12
            or not isinstance(value["parent_cash_observation_receipts"], list)
            or not 1 <= len(value["parent_cash_observation_receipts"]) <= 3):
        raise ValueError("HORIZON_SOURCE_SELECTION_REQUIRED")
    keys = [(e["period"], e["physical_page"]) for e in value["excerpts"]]
    if len(set(keys)) != len(keys):
        raise ValueError("HORIZON_DUPLICATE_PAGE_SELECTION")
    return deepcopy(value)


def _supplement(root, symbol, selection, now):
    bindings = selection["parent_cash_observation_receipts"]
    # Existing cash receipt replay first: discovery indexes, issuer, original and
    # parent-statement provenance are checked before any new excerpt is consumed.
    cash.replay_bound_parent_cash_observations(root=root, symbol=symbol,
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
        # Source-bound H1 rows are admitted by the existing statement parser,
        # never converted from narrative or confused with full-year actuals.
        if period.endswith("-06-30"):
            report = statements.load_operating_statement_basis(root=root, source=source, evaluation_at=now)
            if (report.get("symbol") != symbol or report.get("source_binding") != source
                    or report.get("action") != "no_order" or report.get("financial_quality_granted") is not False):
                raise ValueError("HORIZON_STATEMENT_BINDING_INVALID")
            for row in report["evidence"]:
                if (row.get("pdf_sha256") != source["sha256"] or row.get("period_basis") != "H1"
                        or row.get("available_at") != available or row.get("source_binding") != source):
                    raise ValueError("HORIZON_INTERIM_ROW_BINDING_INVALID")
                evidence.append(dict(_fact(row), receipt_binding=deepcopy(pin)))
            gaps.extend(dict(gap, report_period=period) for gap in report["gaps"])
        selected = [e for e in selection["excerpts"] if e["period"] == period]
        if selected:
            pages = pdf_text.extract_pages(original, limit=max(e["physical_page"] for e in selected))
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
    return evidence, sources, gaps


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
        base = base_sources.build_operating_source_context(root=root, symbol=symbol, now=now)
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
        base = base_sources.build_operating_source_context(root=root, symbol=symbol, now=now,
                                                           binding=manifest["base_binding"])
        path = None
    if (base["symbol"] != symbol or base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("HORIZON_BASE_CONTEXT_CHANGED")
    extra, sources, gaps = _supplement(root, symbol, selection, now)
    # Replace automatic first-page narrative sampling with complete curated spans.
    evidence = [_fact(row) for row in base["evidence"] if "field" in row and "value" in row]
    evidence.extend(extra)
    if not evidence or len(evidence) > 100 or len({r["id"] for r in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    for row in evidence:
        _clock(row["available_at"], now)
    value = dict(schema_version=VERSION, symbol=symbol, issuer_name=selection["issuer_name"],
        as_of=now.isoformat(), financial_basis=base["financial_basis"], source_binding=deepcopy(binding),
        base_source_binding=deepcopy(manifest["base_binding"]), supplemental_sources=sources,
        evidence=evidence, statement_basis_gaps=gaps, implementation_sha256=manifest["implementation_sha256"],
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

