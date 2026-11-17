"""Prepare a D2 source selection from two archived official report receipts."""
from copy import deepcopy
from datetime import datetime
import json
from itertools import islice
from pathlib import Path

from ...product.common import require_inside, write_new_bytes
from ..sse_research_pipeline_v1 import read_sse_research_pool
from ..parent_cash_layout_observation import observe_parent_cash_rows
from . import operating_horizon_sources_v1 as horizon
from .task_execution_v1 import _bytes, _hash

REQUIRED_PERIODS = ("2025-12-31", "2026-06-30")


def prepare_receipt_selection(*, root: Path, symbol: str, issuer_name: str,
                              receipts_by_period: dict, as_of: datetime) -> dict:
    """Replay the supported layout before handing a candidate to the source registry.

    The proposal does not install a registry entry or qualify the cash policy.
    A filing using another layout needs a supported, separately verified parser.
    """
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("HORIZON_SELECTION_REQUIRES_AWARE_CUTOFF")
    if set(receipts_by_period) != set(REQUIRED_PERIODS):
        raise ValueError("HORIZON_RECEIPT_BASE_PERIODS_REQUIRED")
    selection = horizon._selection({
        "issuer_name": issuer_name,
        "parent_cash_observation_receipts": [
            {"period": period, "receipt_binding": deepcopy(receipts_by_period[period])}
            for period in REQUIRED_PERIODS
        ],
        "parent_cash_layout": "LEGACY_BLANK_SAFE_V3",
        "excerpts": [],
    })
    base = horizon._receipt_operating_base(root, symbol, selection, as_of)
    try:
        evidence, _, gaps = horizon._supplement(root, symbol, selection, as_of)
    except ValueError as error:
        if not (str(error) == "PARENT_CASH_ISSUER_OR_REPORT_MISMATCH"
                or str(error).startswith("PARENT_CASH_ROW_MISSING_OR_AMBIGUOUS:")):
            raise
        return _observe_alternate_layout(root, symbol, selection, as_of)
    if not evidence:
        raise ValueError("HORIZON_SELECTION_HAS_NO_VERIFIED_EVIDENCE")
    return dict(selection=selection, base_source_binding=base["source_binding"],
                evidence_ids=[row["id"] for row in evidence], statement_basis_gaps=gaps,
                status="SOURCE_REPLAYED_SELECTION_PROPOSAL", formal_eligibility=False,
                action="no_order")


def _observe_alternate_layout(root, symbol, selection, as_of):
    """Preserve verified source observations pending a versioned model adapter."""
    statements = []
    for item in selection["parent_cash_observation_receipts"]:
        pin, period = item["receipt_binding"], item["period"]
        query = horizon.cash._receipt_issuer_query(root=root, receipt_binding=pin)
        packet = horizon.receipts.load_retained_official_report(
            root=root, receipt_binding=pin, symbol=symbol, issuer_name=query, period=period)
        source = packet["source"]
        for stamp in (packet["fetched_at"], packet["completed_at"], source["available_at"]):
            horizon._clock(stamp, as_of)
        original = require_inside(root / "runtime", root / source["path"], "parent cash original")
        observed = observe_parent_cash_rows(pages=horizon.pdf_text.extract_pages(original),
            symbol=symbol, issuer_name=selection["issuer_name"], period=period)
        if _hash(original.read_bytes()) != source["sha256"]:
            raise ValueError("HORIZON_ORIGINAL_CHANGED_DURING_EXTRACTION")
        statements.append(dict(period=period, receipt_binding=deepcopy(pin),
                               source_binding=deepcopy(source), **observed))
    first, second = statements
    closing = first["rows"]["closing_cash_and_equivalents_cny"]["columns"][0]["value"]
    opened = second["rows"].get("opening_cash_and_equivalents_cny")
    if not opened or opened["columns"][0]["value"] != closing:
        raise ValueError("PARENT_CASH_LAYOUT_PERIOD_CONTINUITY_NOT_PROVEN")
    return dict(status="PARENT_CASH_LAYOUT_REPLAYED_D2_ADAPTER_REQUIRED",
                historical_parent_cash=statements, formal_eligibility=False,
                action="no_order")


def prepare_receipt_selection_batch(*, root: Path, queue_rows: list, receipts: dict,
                                    budget: int, as_of: datetime) -> dict:
    """Replay retained receipt pairs in queue order within a bounded local budget."""
    if type(budget) is not int or not 1 <= budget <= 30:
        raise ValueError("HORIZON_SELECTION_BATCH_BUDGET_INVALID")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("HORIZON_SELECTION_REQUIRES_AWARE_CUTOFF")
    rows = []
    seen = set()
    for item in queue_rows:
        symbol = item["symbol"]
        if symbol in seen:
            raise ValueError("HORIZON_SELECTION_BATCH_DUPLICATE_SYMBOL")
        seen.add(symbol)
        if len(rows) < budget:
            pins = receipts.get(symbol)
            if pins is None:
                rows.append(dict(symbol=symbol, status="OFFICIAL_RECEIPT_PAIR_REQUIRED"))
                continue
            try:
                proposal = prepare_receipt_selection(root=root, symbol=symbol,
                    issuer_name=pins["issuer_name"], receipts_by_period=pins["receipts_by_period"],
                    as_of=as_of)
                rows.append(dict(symbol=symbol, **proposal))
            except (ValueError, OSError, KeyError, TypeError) as error:
                rows.append(dict(symbol=symbol, status="SOURCE_REPLAY_REJECTED",
                                 reason=str(error)))
    return dict(as_of=as_of.isoformat(), budget=budget, queue_count=len(seen), items=rows,
                action="no_order", formal_eligibility=False)

def persist_current_queue_receipt_batch(*, queue_root: Path, research_root: Path,
                                        expected_queue: dict, budget: int,
                                        as_of: datetime) -> dict:
    """Run source replay for the exact current tracking queue and archive its result."""
    if type(budget) is not int or not 1 <= budget <= 30:
        raise ValueError("HORIZON_SELECTION_BATCH_BUDGET_INVALID")
    queue = read_sse_research_pool(root=queue_root, now=as_of)
    if (queue["status"] != "AVAILABLE" or not expected_queue
            or queue["queue_binding"] != expected_queue):
        raise ValueError("HORIZON_SELECTION_TRACKING_QUEUE_CHANGED")
    research_root = research_root.resolve()
    registry_path = require_inside(research_root, research_root / horizon.CONFIG, "source registry")
    registry_raw = registry_path.read_bytes()
    registry = json.loads(registry_raw)
    if registry.get("schema_version") != horizon.VERSION or registry.get("action") != "no_order":
        raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
    inputs = {}
    for item in queue["items"][:budget]:
        entry = registry["cases"].get(item["symbol"])
        if entry is not None:
            pins = entry["parent_cash_observation_receipts"]
            periods = {pin["period"]: pin["receipt_binding"] for pin in pins}
            if len(periods) == len(pins) and set(periods) == set(REQUIRED_PERIODS):
                inputs[item["symbol"]] = dict(issuer_name=entry["issuer_name"], receipts_by_period=periods)
    result = prepare_receipt_selection_batch(root=research_root, queue_rows=queue["items"],
        receipts=inputs, budget=budget, as_of=as_of)
    result.update(schema_version="horizon-queue-receipt-selection-v1",
                  queue_binding=deepcopy(expected_queue), receipt_inputs=inputs,
                  registry_sha256=_hash(registry_raw), new_llm_calls=0)
    raw = _bytes(result)
    relative = Path("runtime/horizon-queue-receipt-selection-v1") / (_hash(raw) + ".json")
    output = require_inside(research_root, research_root / relative, "receipt batch result")
    try:
        write_new_bytes(output, raw)
    except FileExistsError:
        if output.read_bytes() != raw:
            raise ValueError("HORIZON_SELECTION_BATCH_OUTPUT_CHANGED")
    return dict(result=result, binding=dict(path=relative.as_posix(), sha256=_hash(raw)))

def read_queue_receipt_batch(*, research_root: Path, queue_binding: dict,
                             as_of: datetime) -> dict | None:
    """Return a public summary of the latest verified archive for this exact queue."""
    research_root = research_root.resolve()
    directory = require_inside(research_root, research_root / "runtime/horizon-queue-receipt-selection-v1",
                               "receipt batch directory")
    candidates = list(islice(directory.glob("*.json"), 257))
    if len(candidates) > 256:
        raise ValueError("HORIZON_SELECTION_BATCH_ARCHIVE_LIMIT")
    registry_path = require_inside(research_root, research_root / horizon.CONFIG, "source registry")
    if not candidates:
        return None
    registry_sha = _hash(registry_path.read_bytes())
    latest = None
    for path in candidates:
        path = require_inside(directory, path, "receipt batch")
        if path.stat().st_size > 1_000_000:
            raise ValueError("HORIZON_SELECTION_BATCH_RESULT_TOO_LARGE")
        raw = path.read_bytes()
        result = json.loads(raw)
        if (result.get("queue_binding") != queue_binding
                or result.get("registry_sha256") != registry_sha):
            continue
        if (_hash(raw) != path.stem or result.get("schema_version") != "horizon-queue-receipt-selection-v1"
                or result.get("action") != "no_order" or result.get("formal_eligibility") is not False
                or result.get("new_llm_calls") != 0):
            raise ValueError("HORIZON_SELECTION_BATCH_INTEGRITY_FAILED")
        stamp = datetime.fromisoformat(result["as_of"])
        if stamp.utcoffset() is None or stamp > as_of:
            raise ValueError("HORIZON_SELECTION_BATCH_CUTOFF_INVALID")
        if latest is None or (stamp, path.stem) > latest[:2]:
            latest = stamp, path.stem, result
    if latest is None:
        return None
    _, digest, result = latest
    return dict(as_of=result["as_of"], sha256=digest,
                items=[dict(symbol=row["symbol"], status=row["status"],
                            evidence_count=len(row.get("evidence_ids", [])) or
                            sum(len(statement["rows"]) for statement in row.get("historical_parent_cash", []))) for row in result["items"]])
