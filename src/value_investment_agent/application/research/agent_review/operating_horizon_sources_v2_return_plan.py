"""Add a bound official return plan to the current generic horizon facts.

The model-facing projection retains the v1 evidence schema. The separate v2
source binding records the added original and loader implementation; historical
v1 task inputs and responses are never rewritten.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re

from . import operating_horizon_sources_v1 as base
from . import operating_horizon_sources_v7 as plan
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-v2-return-plan"


def implementation():
    return {**plan.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def configured_for(root, symbol):
    """Choose the extra source only when an explicit local selector names it."""
    location = Path(root).resolve() / plan.CONFIG
    if not location.is_file():
        return False
    registry = json.loads(location.read_bytes())
    if (registry.get("schema_version") != "operating-return-plan-text-selection-v1"
            or registry.get("action") != "no_order"
            or not isinstance(registry.get("cases"), dict)):
        raise ValueError("RETURN_PLAN_SELECTION_INVALID")
    if symbol not in registry["cases"]:
        return False
    plan._selection(Path(root).resolve(), symbol)
    return True


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None):
        raise ValueError("RETURN_PLAN_SOURCE_IDENTITY_INVALID")
    if binding is None:
        selected, selected_from = plan._selection(root, symbol)
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(original["source_binding"]),
            base_context_sha256=_hash(_bytes(original)), selection=deepcopy(selected),
            selected_from=selected_from, implementation_sha256=implementation(),
            action="no_order")
        raw = _bytes(manifest)
        location = require_inside(root / "runtime", root / "runtime" / VERSION /
            (_hash(raw) + ".json"), "return plan source manifest")
        binding = dict(path=location.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = base._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("symbol") != symbol
                or manifest.get("as_of") != now.isoformat() or manifest.get("action") != "no_order"
                or manifest.get("implementation_sha256") != implementation()
                or not isinstance(manifest.get("selection"), dict)):
            raise ValueError("RETURN_PLAN_SOURCE_MANIFEST_CHANGED")
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol,
            now=now, binding=manifest["base_binding"])
        selected = manifest["selection"]
        location = None
    if (original["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(original)) != manifest["base_context_sha256"]):
        raise ValueError("RETURN_PLAN_BASE_CHANGED")
    row, source = plan._plan(root, symbol, original["issuer_name"], selected, now)
    if len(original["evidence"]) >= 100 or any(
            item["id"] == row["id"] for item in original["evidence"]):
        raise ValueError("RETURN_PLAN_EVIDENCE_LIMIT_OR_DUPLICATE")
    result = deepcopy(original)
    result["evidence"].append(row)
    result["supplemental_sources"].append(source)
    result["limitations"].append(
        "Return-plan floor uses attributable consolidated profit, not standalone parent profit; "
        "it is conditional policy evidence, not 2027 cash capacity or approved payment")
    result.update(source_binding=deepcopy(binding), source_adapter_version=VERSION,
        implementation_sha256=manifest["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({
        key: value for key, value in result.items() if key != "snapshot_fingerprint"}))
    if len(_bytes(result).decode("utf-8")) > plan.MAX_CONTEXT_CHARS:
        raise ValueError("RETURN_PLAN_CONTEXT_OVER_BUDGET")
    if location is not None:
        location.parent.mkdir(parents=True, exist_ok=True)
        if location.exists():
            base._bound(root, binding)
        else:
            write_new_bytes(location, _bytes(manifest))
    return result
