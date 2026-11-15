"""Opt-in source version for parent trade-balance counterevidence."""

from copy import deepcopy
import json
from pathlib import Path

from . import operating_horizon_sources_v4_cash_constraints as base
from . import parent_trade_evidence as evidence
from . import parent_fund_evidence as fund
from .operating_horizon_sources_v1 import _bound
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import parent_trade_balances as trade

VERSION = "operating-horizon-sources-v5-parent-trade"
CONFIG = "config/current-operating-parent-trade-v1.json"


def implementation():
    return {**base.implementation(), **{
        module.__name__: _hash(Path(module.__file__).read_bytes())
        for module in (evidence, fund, trade)
    }, __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("PARENT_TRADE_AWARE_CUTOFF_REQUIRED")
    identity = dict(schema_version=VERSION, action="no_order", symbol=symbol,
                    as_of=now.isoformat(), implementation_sha256=implementation())
    if binding is None:
        selection = json.loads((root / CONFIG).read_bytes())[symbol]
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        raw = _bytes(dict(identity, selection=selection, base_binding=original["source_binding"],
                          base_context_sha256=_hash(_bytes(original))))
        digest = _hash(raw)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (digest + ".json"),
                              "parent trade manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=digest)
    else:
        path = None
        manifest = _bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("PARENT_TRADE_MANIFEST_CHANGED")
        selection = manifest["selection"]
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        if _hash(_bytes(original)) != manifest["base_context_sha256"]:
            raise ValueError("PARENT_TRADE_CONTEXT_CHANGED")
    trade_selection = {key: value for key, value in selection.items() if key != "fund"}
    if original.get("symbol") != symbol or trade_selection.get("symbol") != symbol:
        raise ValueError("PARENT_TRADE_CONTEXT_ISSUER_CHANGED")
    row = evidence.replay_parent_trade_evidence(root=root, context=original, selection=trade_selection, cutoff=now)
    result = deepcopy(original)
    result["evidence"].insert(0, row)
    if "fund" in selection:
        result["evidence"].insert(1, fund.replay_parent_fund_evidence(
            root=root, context=original, selection=selection["fund"], cutoff=now))
    if len(result["evidence"]) > 100 or len({item["id"] for item in result["evidence"]}) != len(result["evidence"]):
        raise ValueError("PARENT_TRADE_EVIDENCE_LIMIT_OR_DUPLICATE")
    result.update(source_binding=binding, source_adapter_version=VERSION,
                  implementation_sha256=identity["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({key: value for key, value in result.items()
                                                  if key != "snapshot_fingerprint"}))
    if len(_bytes(result).decode("utf-8")) > base.base.base.plan.MAX_CONTEXT_CHARS:
        raise ValueError("PARENT_TRADE_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _bound(root, binding)
        else:
            write_new_bytes(path, raw)
    return result
