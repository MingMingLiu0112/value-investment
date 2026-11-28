"""Replay the tracking queue against both registered official receipt layouts."""
from datetime import datetime
import json
from itertools import islice
from pathlib import Path

from ...product.common import require_inside, write_new_bytes
from ..sse_research_pipeline_v2 import read_sse_research_pool_for_web
from . import horizon_receipt_selection as legacy
from . import operating_horizon_sources_parent_layout as alternate
from .task_execution_v1 import _bytes, _hash

VERSION = "horizon-queue-receipt-selection-v2"


def _registry(root, relative, *, optional=False):
    path = require_inside(root, root / relative, "receipt source registry")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        if optional:
            return {}, None
        raise
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
    return data, _hash(raw)


def _registries(root):
    base, base_hash = _registry(root, legacy.horizon.CONFIG)
    variants, alternate_hash = _registry(root, alternate.CONFIG, optional=True)
    if base.get("schema_version") != legacy.horizon.VERSION or base.get("action") != "no_order":
        raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
    return base["cases"], variants, {"base": base_hash, "parent_layout": alternate_hash}


def _registered_receipt_pair(entry):
    invalid = "HORIZON_SELECTION_REGISTRY_ENTRY_INVALID"
    if not isinstance(entry, dict):
        raise ValueError(invalid)
    issuer = entry.get("issuer_name")
    pins = entry.get("parent_cash_observation_receipts")
    if not isinstance(issuer, str) or not issuer.strip() or not isinstance(pins, list):
        raise ValueError(invalid)
    periods = {}
    for pin in pins:
        if not isinstance(pin, dict):
            raise ValueError(invalid)
        period, binding = pin.get("period"), pin.get("receipt_binding")
        if not isinstance(period, str) or period in periods or not isinstance(binding, dict):
            raise ValueError(invalid)
        periods[period] = binding
    if set(periods) != set(legacy.REQUIRED_PERIODS):
        return None
    return dict(issuer_name=issuer, receipts_by_period=periods)


def persist_current_queue_receipt_batch(*, queue_root, research_root, expected_queue, budget, as_of):
    if type(budget) is not int or not 1 <= budget <= 30:
        raise ValueError("HORIZON_SELECTION_BATCH_BUDGET_INVALID")
    if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
        raise ValueError("HORIZON_SELECTION_REQUIRES_AWARE_CUTOFF")
    queue = read_sse_research_pool_for_web(root=queue_root, now=as_of)
    if queue["status"] != "AVAILABLE" or not expected_queue or queue["queue_binding"] != expected_queue:
        raise ValueError("HORIZON_SELECTION_TRACKING_QUEUE_CHANGED")
    root = Path(research_root).resolve()
    base, variants, registry_hashes = _registries(root)
    inputs = {}
    rejections = {}
    for item in queue["items"][:budget]:
        symbol = item["symbol"]
        for registry in (base, variants):
            if symbol not in registry:
                continue
            try:
                proposed = _registered_receipt_pair(registry[symbol])
            except ValueError as error:
                rejections[symbol] = str(error)
                inputs.pop(symbol, None)
                break
            if proposed is None:
                continue
            if symbol in inputs and inputs[symbol] != proposed:
                rejections[symbol] = "HORIZON_SELECTION_REGISTRY_CONFLICT"
                del inputs[symbol]
                break
            inputs[symbol] = proposed
    result = legacy.prepare_receipt_selection_batch(
        root=root, queue_rows=queue["items"], receipts=inputs, budget=budget, as_of=as_of,
    )
    for row in result["items"]:
        if row["symbol"] in rejections:
            row.update(status="SOURCE_REPLAY_REJECTED", reason=rejections[row["symbol"]])
    result.update(schema_version=VERSION, queue_binding=expected_queue, registry_hashes=registry_hashes,
                  receipt_inputs=inputs, new_llm_calls=0)
    raw = _bytes(result)
    digest = _hash(raw)
    relative = Path("runtime") / VERSION / (digest + ".json")
    path = require_inside(root, root / relative, "receipt batch result")
    try:
        write_new_bytes(path, raw)
    except FileExistsError:
        if path.read_bytes() != raw:
            raise ValueError("HORIZON_SELECTION_BATCH_OUTPUT_CHANGED")
    return dict(result=result, binding=dict(path=relative.as_posix(), sha256=digest))


def read_queue_receipt_batch(*, research_root, queue_binding, as_of):
    root = Path(research_root).resolve()
    directory = require_inside(root, root / "runtime" / VERSION, "receipt batch directory")
    paths = list(islice(directory.glob("*.json"), 257))
    if not paths:
        # V1 cannot describe queue entries registered in the second registry.
        _, variants, _ = _registries(root)
        if variants:
            return None
        return legacy.read_queue_receipt_batch(
            research_root=root, queue_binding=queue_binding, as_of=as_of,
        )
    if len(paths) > 256:
        raise ValueError("HORIZON_SELECTION_BATCH_ARCHIVE_LIMIT")
    _, _, hashes = _registries(root)
    latest = None
    for path in paths:
        path = require_inside(directory, path, "receipt batch")
        if path.stat().st_size > 1_000_000:
            raise ValueError("HORIZON_SELECTION_BATCH_RESULT_TOO_LARGE")
        raw = path.read_bytes()
        result = json.loads(raw)
        if result.get("queue_binding") != queue_binding or result.get("registry_hashes") != hashes:
            continue
        if (_hash(raw) != path.stem or result.get("schema_version") != VERSION
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
    return dict(as_of=result["as_of"], sha256=digest, items=[
        dict(symbol=row["symbol"], status=row["status"],
             reason_code=(
                 row['reason']
                 if row.get('reason') in {'HORIZON_SELECTION_REGISTRY_CONFLICT',
                                          'HORIZON_SELECTION_REGISTRY_ENTRY_INVALID'}
                 else 'HORIZON_SELECTION_SOURCE_REPLAY_FAILED'
                 if row['status'] == 'SOURCE_REPLAY_REJECTED' else None),
             evidence_count=len(row.get("evidence_ids", [])) or
             sum(len(statement["rows"]) for statement in row.get("historical_parent_cash", [])))
        for row in result["items"]
    ])
