"""Add parent nine-month statements to a separately pinned D2 source context."""
from copy import deepcopy
from pathlib import Path

from . import operating_horizon_sources_v2_return_plan as base
from . import quarterly_parent_cash_source as quarter
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import quarterly_parent_cash_facts as parser

VERSION = "operating-horizon-sources-v3-parent-quarter"
CONFIG = "config/current-operating-parent-quarter-v1.json"


def implementation():
    modules = (quarter, parser)
    return {**base.implementation(), **{
        module.__name__: _hash(Path(module.__file__).read_bytes()) for module in modules
    }, __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    import json

    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("PARENT_QUARTER_AWARE_CUTOFF_REQUIRED")
    identity = dict(schema_version=VERSION, action="no_order", symbol=symbol,
                    as_of=now.isoformat(), implementation_sha256=implementation())
    if binding is None:
        selection = json.loads((root / CONFIG).read_bytes())[symbol]
        if set(selection) != {"source", "period_end"}:
            raise ValueError("PARENT_QUARTER_SELECTION_INVALID")
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(**identity, selection=selection, base_binding=original["source_binding"],
                        base_context_sha256=_hash(_bytes(original)))
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "parent quarter manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        path = None
        manifest = base.base._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("PARENT_QUARTER_MANIFEST_CHANGED")
        selection = manifest["selection"]
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
    if _hash(_bytes(original)) != manifest["base_context_sha256"]:
        raise ValueError("PARENT_QUARTER_BASE_CONTEXT_CHANGED")
    rows = quarter.quarterly_parent_cash_evidence(
        root=root, symbol=symbol, issuer_name=original["issuer_name"], now=now, **selection)
    result = deepcopy(original)
    result["evidence"].extend(rows)
    if len(result["evidence"]) > 100 or len({row["id"] for row in result["evidence"]}) != len(result["evidence"]):
        raise ValueError("PARENT_QUARTER_EVIDENCE_LIMIT_OR_DUPLICATE")
    result["limitations"].append(
        "The parent nine-month cash rows are comparative historical observations. "
        "Supplier payments may reflect timing; total cash capex does not isolate maintenance."
    )
    result.update(source_binding=binding, source_adapter_version=VERSION,
                  implementation_sha256=manifest["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({
        key: value for key, value in result.items() if key != "snapshot_fingerprint"
    }))
    if len(_bytes(result).decode("utf-8")) > base.plan.MAX_CONTEXT_CHARS:
        raise ValueError("PARENT_QUARTER_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base.base._bound(root, binding)
        else:
            write_new_bytes(path, raw)
    return result
