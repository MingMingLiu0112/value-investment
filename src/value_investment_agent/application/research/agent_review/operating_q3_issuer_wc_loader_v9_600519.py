"""Opt-in source loader adding verified parent balance movements to V8 D2.

This is an evidence extension, not a working-capital cash-flow forecast.
Historical tasks retain their original loader and source binding.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from . import operating_q3_issuer_plan_loader_v8_600519 as prior
from . import operating_task_v2 as live
from . import parent_wc_balance_request_v1 as wc_request
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside
from ....infrastructure.filings import parent_wc_history_600519_v1 as wc_source

VERSION = "operating-q3-issuer-wc-loader-v9-600519"


def implementation():
    return {**prior.implementation(),
            wc_request.__name__: _hash(Path(wc_request.__file__).read_bytes()),
            wc_source.__name__: _hash(Path(wc_source.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def _history(root: Path, now: datetime):
    history = wc_source.read_parent_wc_history(root, now)
    if history.get("status") != "PARENT_BALANCE_MOVEMENTS_ONLY":
        raise ValueError("V9_PARENT_WC_HISTORY_NOT_VERIFIED")
    registry_path = require_inside(root, root / wc_source.REGISTRY, "parent WC registry")
    raw = registry_path.read_bytes()
    registry = wc_source._json(raw)
    sources = registry.get("sources")
    if not isinstance(sources, list) or len(sources) < 2:
        raise ValueError("V9_PARENT_WC_REGISTRY_INVALID")
    originals = []
    for source in sources:
        path = require_inside(root, root / source["path"], "parent WC original")
        if wc_source._sha(path) != source["sha256"]:
            raise ValueError("V9_PARENT_WC_ORIGINAL_CHANGED")
        originals.append(dict(path=source["path"], sha256=source["sha256"]))
    pin = dict(registry=dict(path=wc_source.REGISTRY, sha256=_hash(raw)),
               originals=originals, history_sha256=_hash(_bytes(history)))
    return history, pin


def load_current(*, root, symbol, now: datetime, binding=None):
    root = Path(root).resolve()
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or (binding is not None and
                (not isinstance(binding, dict) or set(binding) != {"base", "parent_wc"}))):
        raise ValueError("V9_PARENT_WC_IDENTITY_OR_BINDING_INVALID")
    base = prior.load_current(root=root, symbol=symbol, now=now,
                              binding=binding["base"] if binding else None)
    history, pin = _history(root, now)
    observed = dict(base=base["source_binding"], parent_wc=pin)
    if binding is not None and binding != observed:
        raise ValueError("V9_PARENT_WC_SOURCE_CHANGED")
    projected = live.research_context(base, drivers=True)
    enriched, anchor = wc_request.attach_parent_wc_balance_anchor(
        projected, history=history, as_of=now)
    added = enriched["evidence"][len(projected["evidence"]):]
    if len(added) != len(history["observations"]) or anchor["operating_wc_cash_cny"] != "UNKNOWN":
        raise ValueError("V9_PARENT_WC_EVIDENCE_INVALID")
    result = deepcopy(base)
    result["evidence"].extend(added)
    result["source_binding"] = observed
    result["parent_wc_balance_anchor"] = anchor
    result["snapshot_fingerprint"] = _hash(_bytes([
        VERSION, base["snapshot_fingerprint"], observed, added]))
    result["formal_eligibility"] = False
    result["action"] = "no_order"
    return result
