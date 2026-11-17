"""Versioned provenance compaction for oversized public operating source contexts."""
from copy import deepcopy
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v1 as legacy
from . import operating_horizon_context_budget as budget
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes

VERSION = "operating-horizon-sources-compact-v1"
CONFIG = "config/current-operating-compact-sources-v1.json"


def _implementation():
    return {**legacy.implementation(),
            budget.__name__: _hash(Path(budget.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if now.utcoffset() is None or not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol):
        raise ValueError("HORIZON_SOURCE_IDENTITY_OR_CLOCK_INVALID")
    identity = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(), action="no_order",
        implementation_sha256=_implementation())
    if binding is None:
        raw = require_inside(root, root / legacy.CONFIG, "horizon source selection").read_bytes()
        registry = json.loads(raw)
        if registry.get("schema_version") != legacy.VERSION or registry.get("action") != "no_order":
            raise ValueError("HORIZON_SOURCE_REGISTRY_INVALID")
        selection = legacy._selection(registry["cases"].get(symbol))
        manifest = dict(identity, selection=selection,
                        selected_from=dict(path=legacy.CONFIG, sha256=_hash(raw)))
    else:
        manifest = legacy._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("COMPACT_HORIZON_SOURCE_MANIFEST_CHANGED")
        selection = legacy._selection(manifest["selection"])
    # This transport only covers the complete default fact selection.
    if {"base_fact_fields", "supplement_fact_fields", "prior_conditional_assumption_binding"} & selection.keys():
        raise ValueError("COMPACT_HORIZON_REQUIRES_UNFILTERED_SOURCE")
    if selection.get("parent_cash_layout") == "LEGACY_BLANK_SAFE_V3":
        base = legacy._receipt_operating_base(root, symbol, selection, now)
    else:
        base = legacy.base_sources.build_operating_source_context(root=root, symbol=symbol, now=now,
            binding=None if binding is None else manifest["base_binding"])
    base_identity = dict(base_binding=base["source_binding"], base_context_sha256=_hash(_bytes(base)))
    if base["symbol"] != symbol or (binding is not None
            and any(manifest[key] != value for key, value in base_identity.items())):
        raise ValueError("HORIZON_BASE_CONTEXT_CHANGED")
    manifest.update(base_identity)
    raw = _bytes(manifest)
    path = require_inside(root, root / "runtime" / VERSION / (_hash(raw) + ".json"), "compact horizon manifest")
    expected = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    if binding is not None and binding != expected:
        raise ValueError("COMPACT_HORIZON_SOURCE_MANIFEST_CHANGED")
    extra, sources, gaps = legacy._supplement(root, symbol, selection, now)
    evidence = [legacy._fact(row) for row in base["evidence"] if "field" in row and "value" in row]
    evidence.extend(extra)
    if not evidence or len(evidence) > 100 or len({row["id"] for row in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    for row in evidence:
        legacy._clock(row["available_at"], now)
    context = dict(schema_version=legacy.VERSION, source_adapter_version=VERSION, symbol=symbol,
        issuer_name=selection["issuer_name"], as_of=now.isoformat(), financial_basis=base["financial_basis"],
        source_binding=expected, base_source_binding=deepcopy(base["source_binding"]), supplemental_sources=sources,
        parent_cash_observation_receipts=deepcopy(selection["parent_cash_observation_receipts"]),
        evidence=evidence, statement_basis_gaps=gaps, implementation_sha256=identity["implementation_sha256"],
        scope_decomposition=deepcopy(selection.get("scope_decomposition")), prior_conditional_hypothesis=None,
        action="no_order", formal_eligibility=False,
        limitations=["Interim consolidated facts are H1, never full-year actuals or annualized forecasts",
            "Narrative is issuer disclosure, not verified economic claims or independent review",
            "No current-event completeness, valuation, approval or cash capacity inferred"])
    context["snapshot_fingerprint"] = _hash(_bytes(context))
    if budget.measure_compact_context_chars(context) > legacy.MAX_CONTEXT_CHARS:
        raise ValueError("HORIZON_SOURCE_CONTEXT_OVER_BUDGET")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        write_new_bytes(path, raw)
    else:
        legacy._bound(root, expected)
    return context
