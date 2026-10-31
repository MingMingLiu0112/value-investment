"""Bounded official report bundles feeding the existing financial enrichment contract.

A bundle verifies requested originals, not all-market completeness or investment
admission. Cached availability clocks never advance on replay.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ...infrastructure.filings.official_report_acquisition import (
    acquire_official_report, load_retained_official_report,
)
from ...infrastructure.filings.official_pdf import is_transient_evidence_failure
from ...infrastructure.screening.value_evidence_enrichment_v1 import RetainedAnnualSource
from .value_evidence_enrichment_v1 import enrich_retained_company

VERSION = "public-evidence-bundle-v1"
POINTER = Path("runtime/public-evidence/current.json")


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)


def _binding(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=_digest(path))


def _bound(root, binding):
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
        raise ValueError("EVIDENCE_BINDING_INVALID")
    path = (root / binding["path"]).resolve()
    if (not path.is_relative_to(root / "runtime")
            or not re.fullmatch(r"[0-9a-f]{64}", str(binding["sha256"]))
            or _digest(path) != binding["sha256"]):
        raise ValueError("EVIDENCE_HASH_OR_PATH_INVALID")
    return path


def _requests(requests):
    if not isinstance(requests, list) or not 1 <= len(requests) <= 6:
        raise ValueError("REQUEST_BUDGET_ONE_TO_SIX")
    seen = set()
    for item in requests:
        if (not isinstance(item, dict) or set(item) != {"symbol", "issuer_name", "period", "exchange"}
                or not re.fullmatch(r"[0-9]{6}", str(item["symbol"]))
                or not isinstance(item["issuer_name"], str) or not item["issuer_name"].strip()
                or item["exchange"] not in {"SSE", "SZSE", "BSE"}):
            raise ValueError("EXACT_REQUEST_IDENTITY_REQUIRED")
        datetime.strptime(item["period"], "%Y-%m-%d")
        if item["period"][4:] not in {"-12-31", "-06-30"}:
            raise ValueError("UNSUPPORTED_REPORT_PERIOD")
        expected = "SSE" if item["symbol"].startswith("6") else "SZSE" if item["symbol"].startswith(("0", "3")) else "BSE"
        if item["exchange"] != expected:
            raise ValueError("EXCHANGE_IDENTITY_CONFLICT")
        key = (item["symbol"], item["period"])
        if key in seen:
            raise ValueError("DUPLICATE_REPORT_REQUEST")
        seen.add(key)
    return requests


def _clock(value):
    clock = datetime.fromisoformat(value)
    if clock.utcoffset() is None or clock > datetime.now(timezone.utc):
        raise ValueError("EVIDENCE_CLOCK_INVALID")
    return clock


def load_bundle(root, binding):
    root = root.resolve()
    packet = json.loads(_bound(root, binding).read_bytes())
    if (packet.get("schema_version") != VERSION or packet.get("action") != "no_order"
            or packet.get("scope") != "REQUESTED_REPORTS_ONLY"
            or packet.get("formal_eligibility") is not False
            or packet.get("strict_historical_pit") is not False):
        raise ValueError("BUNDLE_SCOPE_INVALID")
    _requests(packet["requests"])
    if not isinstance(packet.get("items"), list) or len(packet["items"]) != len(packet["requests"]):
        raise ValueError("BUNDLE_COVERAGE_INVALID")
    clock = _clock(packet["generated_at"])
    export = json.loads(_bound(root, packet["financial_export"]).read_bytes())
    if (export.get("action") != "no_order" or export.get("formal_eligibility") is not False
            or export.get("points") != [] or _clock(export["generated_at"]) > clock):
        raise ValueError("FINANCIAL_EXPORT_SCOPE_OR_CLOCK_INVALID")
    expected_points, expected_sources = [], []
    for request, item in zip(packet["requests"], packet["items"]):
        if (item.get("request") != request
                or item.get("status") not in {"VERIFIED", "PARTIAL", "MISSING", "CONFLICT", "UNSUPPORTED"}
                or type(item.get("reused")) is not bool
                or type(item.get("fresh_index_checked")) is not bool
                or type(item.get("adopted_fact_count")) is not int
                or item["adopted_fact_count"] < 0):
            raise ValueError("BUNDLE_ITEM_IDENTITY_INVALID")
        usable = item["status"] in {"VERIFIED", "PARTIAL"}
        if usable != bool(item.get("receipt")):
            raise ValueError("BUNDLE_ITEM_RECEIPT_REQUIRED")
        if not usable and (item.get("fact_snapshot") or item["adopted_fact_count"]):
            raise ValueError("UNUSABLE_SOURCE_CANNOT_DECLARE_FACTS")
        if not usable:
            continue
        receipt = json.loads(_bound(root, item["receipt"]).read_bytes())
        source = receipt["source"]
        if (source["symbol"] != request["symbol"] or source["period"] != request["period"]
                or _clock(receipt["completed_at"]) > clock
                or _clock(source["available_at"]) > _clock(receipt["completed_at"])):
            raise ValueError("BUNDLE_RECEIPT_IDENTITY_OR_CLOCK_INVALID")
        if item.get("fact_snapshot"):
            facts = json.loads(_bound(root, item["fact_snapshot"]).read_bytes())
            if (facts.get("action") != "no_order" or facts.get("formal_eligibility") is not False
                    or facts.get("symbol") != request["symbol"] or facts.get("period") != request["period"]
                    or facts["source_extraction"]["identity"]["source"] != source
                    or not _clock(receipt["completed_at"]) <= _clock(facts["evaluation_at"]) <= _clock(export["generated_at"])
                    or not isinstance(facts.get("adopted_points"), list)
                    or len(facts["adopted_points"]) != item["adopted_fact_count"]
                    or item["fact_status"] != ("SCOPED_FACTS_VERIFIED" if facts["adopted_points"] else "OBSERVATIONS_ONLY")):
                raise ValueError("FACT_SNAPSHOT_SCOPE_OR_CLOCK_INVALID")
            expected_points.extend(facts["adopted_points"])
            expected_sources.append(source)
        elif item["adopted_fact_count"] or item["fact_status"] not in {"FACT_EXTRACTION_REJECTED", "UNSUPPORTED_INTERIM_FACT_PARSER"}:
            raise ValueError("FACT_SNAPSHOT_REQUIRED")
    if (export.get("annual_points") != expected_points
            or export.get("value_enrichment_sources") != expected_sources):
        raise ValueError("FINANCIAL_EXPORT_DIFFERS_FROM_BOUND_FACTS")
    expected_status = "VERIFIED" if all(i["status"] == "VERIFIED" for i in packet["items"]) else "PARTIAL"
    if packet.get("status") != expected_status:
        raise ValueError("BUNDLE_STATUS_DIFFERS_FROM_COVERAGE")
    return packet


def _retained(root, item):
    request = item["request"]
    return load_retained_official_report(root=root, receipt_binding=item["receipt"],
        symbol=request["symbol"], issuer_name=request["issuer_name"], period=request["period"])


def _fact_snapshot(root, source, request, output):
    if not request["period"].endswith("-12-31"):
        return None, "UNSUPPORTED_INTERIM_FACT_PARSER", [], None
    result = enrich_retained_company(root, RetainedAnnualSource(**source), [],
        evaluation_at=datetime.now(timezone.utc),
        cache_dir=root / ".tmp/public-evidence-extraction", name=request["issuer_name"])
    result["source_extraction"].pop("page_texts", None)
    result = json.loads(json.dumps(result, default=str, allow_nan=False))
    path = output / "fact-snapshot.json"
    _write(path, result)
    # Only the existing narrow official-balance method can admit without a
    # separately verified provider. Unmatched amounts remain observations.
    points = result.get("adopted_points", [])
    state = "SCOPED_FACTS_VERIFIED" if points else "OBSERVATIONS_ONLY"
    return _binding(root, path), state, points, result["source_extraction"]["identity"]["source"]


def run_public_evidence(*, root, requests, output_dir, allow_network=False,
                        previous_binding=None, refresh=False):
    root = root.resolve()
    requests = _requests(requests)
    if type(allow_network) is not bool or type(refresh) is not bool:
        raise ValueError("EXPLICIT_NETWORK_AND_REFRESH_FLAGS_REQUIRED")
    if refresh and not allow_network:
        raise ValueError("REFRESH_REQUIRES_NETWORK_PERMISSION")
    output = (root / output_dir).resolve()
    if not output.is_relative_to(root / "runtime") or output.exists():
        raise ValueError("FRESH_RUNTIME_OUTPUT_REQUIRED")
    previous = load_bundle(root, previous_binding) if previous_binding else None
    old = {(i["request"]["symbol"], i["request"]["period"]): i for i in previous["items"]} if previous else {}
    output.mkdir(parents=True)
    items, annual_points, declarations = [], [], []
    for index, request in enumerate(requests):
        folder = output / str(index)
        folder.mkdir()
        item = dict(request=request, status="MISSING", receipt=None,
                    reused=False, reason=None, fact_status="NOT_RUN", fact_snapshot=None,
                    adopted_fact_count=0, fresh_index_checked=False)
        cached = old.get((request["symbol"], request["period"]))
        retained = None
        try:
            if cached and cached.get("receipt"):
                # A corrupted registered original is not silently replaced.
                retained = _retained(root, dict(cached, request=request))
                item["receipt"] = cached["receipt"]
            if request["exchange"] == "BSE":
                item.update(status="UNSUPPORTED", reason="BSE_REPORT_DISCOVERY_NOT_VALIDATED")
            elif retained and not refresh:
                item.update(status="VERIFIED", reused=True,
                    reason="RETAINED_ORIGINAL_NOT_LATEST_REPORT_ASSERTION")
            elif allow_network:
                try:
                    retained = acquire_official_report(root=root, symbol=request["symbol"],
                        issuer_name=request["issuer_name"], period=request["period"],
                        output_dir=folder / "acquisition", allow_network=True)
                    item.update(receipt=_binding(root, folder / "acquisition/receipt.json"),
                                status="VERIFIED", fresh_index_checked=True)
                except Exception as error:
                    if retained and is_transient_evidence_failure(error):
                        item.update(status="PARTIAL", reused=True,
                            reason="REFRESH_FAILED_RETAINED_HISTORY:" + type(error).__name__)
                    else:
                        raise
            else:
                item["reason"] = "NO_RETAINED_ORIGINAL_NETWORK_DISABLED"
            if retained and item["status"] in {"VERIFIED", "PARTIAL"}:
                # Same validator is used for new acquisition, reuse and reader.
                retained = _retained(root, item)
                try:
                    binding, state, points, source = _fact_snapshot(root, retained["source"], request, folder)
                    item.update(fact_snapshot=binding, fact_status=state, adopted_fact_count=len(points))
                    annual_points.extend(points)
                    if source:
                        declarations.append(source)
                except Exception as error:
                    item.update(status="PARTIAL", fact_status="FACT_EXTRACTION_REJECTED",
                                reason="FACT_EXTRACTION_REJECTED:" + type(error).__name__)
        except Exception as error:
            item.update(status="MISSING" if is_transient_evidence_failure(error) else "CONFLICT",
                        reason=type(error).__name__ + ":" + str(error),
                        fact_status="NOT_RUN", receipt=None)
        _write(folder / "item.json", item)
        items.append(item)
    export = output / "financial-export.json"
    _write(export, dict(generated_at=datetime.now(timezone.utc).isoformat(),
        points=[], annual_points=annual_points, value_enrichment_sources=declarations,
        action="no_order", formal_eligibility=False))
    packet = dict(schema_version=VERSION, requests=requests, items=items,
        generated_at=datetime.now(timezone.utc).isoformat(),
        status="VERIFIED" if all(i["status"] == "VERIFIED" for i in items) else "PARTIAL",
        financial_export=_binding(root, export), previous_bundle=previous_binding,
        scope="REQUESTED_REPORTS_ONLY", formal_eligibility=False,
        strict_historical_pit=False, action="no_order")
    _write(output / "bundle.json", packet)
    return _binding(root, output / "bundle.json")


def publish_public_evidence(root, binding):
    root = root.resolve()
    packet = load_bundle(root, binding)
    for item in packet["items"]:
        if item.get("receipt"):
            _retained(root, item)
    # Public research pointer only; never touches portfolio or approved results.
    target = root / POINTER
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(uuid4().hex + ".tmp")
    _write(temporary, dict(schema_version="public-evidence-pointer-v1",
                          bundle=binding, action="no_order"))
    os.replace(temporary, target)


def public_evidence_status(root):
    root = root.resolve()
    result = dict(schema_version="public-evidence-status-v1", action="no_order",
        status="MISSING", scope="REQUESTED_REPORTS_ONLY", generated_at=None,
        reason=None, items=[], exchanges={key: dict(requested=0, verified=0)
            for key in ("SSE", "SZSE", "BSE")}, formal_eligibility=False,
        strict_historical_pit=False)
    path = root / POINTER
    if not path.exists():
        result["reason"] = "PUBLIC_EVIDENCE_NOT_RUN"
        return result
    try:
        pointer = json.loads(path.read_bytes())
        if pointer.get("schema_version") != "public-evidence-pointer-v1" or pointer.get("action") != "no_order":
            raise ValueError("PUBLIC_EVIDENCE_POINTER_INVALID")
        packet = load_bundle(root, pointer["bundle"])
        result["generated_at"] = packet["generated_at"]
        for item in packet["items"]:
            request = item["request"]
            row = dict(request, status=item["status"], reason=item["reason"],
                reused=item["reused"], source_url=None, sha256=None, published_date=None,
                fetched_at=None, fact_status=item["fact_status"], adopted_fact_count=0,
                fact_issues=[], adopted_fields=[])
            result["exchanges"][request["exchange"]]["requested"] += 1
            if item.get("receipt"):
                try:
                    receipt = _retained(root, item)
                    row.update(source_url=receipt["source"]["source_url"],
                        sha256=receipt["source"]["sha256"], published_date=receipt["published_date"],
                        fetched_at=receipt["fetched_at"])
                    if item.get("fact_snapshot"):
                        facts = json.loads(_bound(root, item["fact_snapshot"]).read_bytes())
                        if facts["source_extraction"]["identity"]["source"] != receipt["source"]:
                            raise ValueError("FACT_SOURCE_IDENTITY_CONFLICT")
                        reconciliation = facts.get("official_balance_reconciliation", {})
                        if not isinstance(reconciliation, dict):
                            raise ValueError("FACT_ISSUES_TYPE_INVALID")
                        issues = reconciliation.get("issues", [])
                        if not isinstance(issues, list) or not all(isinstance(issue, str) for issue in issues):
                            raise ValueError("FACT_ISSUES_TYPE_INVALID")
                        points = facts["adopted_points"]
                        if not all(isinstance(point, dict) and isinstance(point.get("field_name"), str)
                                   and point["field_name"].strip() for point in points):
                            raise ValueError("ADOPTED_FIELDS_TYPE_INVALID")
                        row.update(adopted_fact_count=len(points), fact_issues=list(issues),
                                   adopted_fields=list(dict.fromkeys(point["field_name"] for point in points)))
                    if row["status"] == "VERIFIED":
                        result["exchanges"][request["exchange"]]["verified"] += 1
                except Exception:
                    row.update(status="CONFLICT", reason="REGISTERED_ORIGINAL_OR_FACTS_INVALID",
                               fact_status="NOT_ADMITTED", adopted_fact_count=0, fact_issues=[], adopted_fields=[])
            result["items"].append(row)
        result["status"] = "VERIFIED" if all(r["status"] == "VERIFIED" for r in result["items"]) else "PARTIAL"
    except Exception:
        result.update(status="CONFLICT", reason="PUBLIC_EVIDENCE_BUNDLE_INVALID", items=[])
    return result



def validate_queue_public_evidence(*, root, bundle_path, bundle_sha256,
                                  financial_export_path, financial_export_sha256):
    """Read-only gate for the existing v2 queue's exact financial export.

    A closure-verified PARTIAL bundle may retain missing/unsupported/conflicted
    requests as gaps, without their facts. At least one retained source must
    verify, and EVERY declared receipt is replayed: a damaged original rejects
    the whole consumption, never silently drops a company. Source verification
    does not assert complete facts, latest reports, strict historical PIT or
    research admission. No acquisition, fallback, timestamp refresh, pointer or
    queue write occurs.
    """
    from ..product.common import require_inside

    root = Path(root).resolve()
    bundle_path = require_inside(root / "runtime", root / bundle_path, "public evidence bundle")
    financial_export_path = require_inside(
        root / "runtime", root / financial_export_path, "public evidence financial export")
    for digest in (bundle_sha256, financial_export_sha256):
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("PUBLIC_EVIDENCE_CONSUMER_HASH_REQUIRED")
    bundle_binding = dict(path=bundle_path.relative_to(root).as_posix(), sha256=bundle_sha256)
    export_binding = dict(path=financial_export_path.relative_to(root).as_posix(),
                          sha256=financial_export_sha256)
    packet = load_bundle(root, bundle_binding)
    if packet["financial_export"] != export_binding:
        raise ValueError("PUBLIC_EVIDENCE_FINANCIAL_EXPORT_BINDING_MISMATCH")
    # load_bundle enforces that unusable items have neither receipts nor facts.
    # Keep those gaps, but never suppress failure of a declared retained source.
    retained_items = [item for item in packet["items"] if item.get("receipt")]
    if not retained_items:
        raise ValueError("PUBLIC_EVIDENCE_NO_VERIFIABLE_SOURCE")
    for item in retained_items:
        request = item["request"]
        load_retained_official_report(
            root=root, receipt_binding=item["receipt"], symbol=request["symbol"],
            issuer_name=request["issuer_name"], period=request["period"])
    # Do not hand off an export/bundle that changed during original replay.
    _bound(root, bundle_binding)
    _bound(root, export_binding)
    return packet
