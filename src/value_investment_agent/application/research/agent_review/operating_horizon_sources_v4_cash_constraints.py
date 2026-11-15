"""Add reviewed issuer cash constraints to a separately pinned D2 source context."""
from copy import deepcopy
from pathlib import Path

from . import operating_horizon_sources_v3_parent_quarter as base
from . import parent_cash_constraint_evidence as constraints
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-v4-cash-constraints"
CONFIG = "config/current-operating-cash-constraints-v1.json"


def implementation():
    modules = (constraints,)
    return {**base.implementation(), **{
        module.__name__: _hash(Path(module.__file__).read_bytes()) for module in modules
    }, __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    import json

    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("CASH_CONSTRAINT_AWARE_CUTOFF_REQUIRED")
    identity = dict(schema_version=VERSION, action="no_order", symbol=symbol,
                    as_of=now.isoformat(), implementation_sha256=implementation())
    if binding is None:
        selection = json.loads((root / CONFIG).read_bytes())[symbol]
        if set(selection) != {"path", "sha256"}:
            raise ValueError("CASH_CONSTRAINT_SELECTION_INVALID")
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(**identity, selection=selection, base_binding=original["source_binding"],
                        base_context_sha256=_hash(_bytes(original)))
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "cash constraint manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        path = None
        manifest = base.base.base._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("CASH_CONSTRAINT_MANIFEST_CHANGED")
        selection = manifest["selection"]
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
    if _hash(_bytes(original)) != manifest["base_context_sha256"]:
        raise ValueError("CASH_CONSTRAINT_BASE_CONTEXT_CHANGED")
    rows = constraints.replay_parent_cash_constraint_evidence(root=root, binding=selection, symbol=symbol, now=now)
    result = deepcopy(original)
    # The cash request lists only the first few candidate citations per term.
    # Give the direct charter evidence priority over indirect cash balance rows.
    charter = [row for row in rows if row["scope"] == "ISSUER_ARTICLES_RULE_TEXT"]
    financing = [row for row in rows if row["scope"] != "ISSUER_ARTICLES_RULE_TEXT"]
    result["evidence"] = charter + result["evidence"] + financing
    if len(result["evidence"]) > 100 or len({row["id"] for row in result["evidence"]}) != len(result["evidence"]):
        raise ValueError("CASH_CONSTRAINT_EVIDENCE_LIMIT_OR_DUPLICATE")
    result["limitations"].append(
        "The charter and financing disclosures constrain dated distribution and funding analysis. "
        "Future appropriations, debt settlement and refinancing require separate evidence."
    )
    result.update(source_binding=binding, source_adapter_version=VERSION,
                  implementation_sha256=manifest["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({
        key: value for key, value in result.items() if key != "snapshot_fingerprint"
    }))
    if len(_bytes(result).decode("utf-8")) > base.base.plan.MAX_CONTEXT_CHARS:
        raise ValueError("CASH_CONSTRAINT_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base.base.base._bound(root, binding)
        else:
            write_new_bytes(path, raw)
    return result
