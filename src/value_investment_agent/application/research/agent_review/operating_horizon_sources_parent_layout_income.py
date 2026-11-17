"""Extend a pinned parent-layout context with its complete annual operating statement."""
from copy import deepcopy
import json
from pathlib import Path

from ....infrastructure.filings import paginated_annual_income_table as annual
from ....domain.research import operating_driver_bridge_v1 as driver
from ...product.common import require_inside, write_new_bytes
from . import operating_horizon_sources_parent_layout as base
from .task_execution_v1 import _bytes, _hash

VERSION = "operating-horizon-sources-parent-layout-income-v1"
CONFIG = "config/current-operating-parent-layout-cost-sources-v1.json"


def implementation():
    return {**base.implementation(),
            annual.__name__: _hash(Path(annual.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    identity = dict(schema_version=VERSION, symbol=symbol, as_of=now.isoformat(),
                    implementation_sha256=implementation(), action="no_order")
    if binding is None:
        config = require_inside(root, root / CONFIG, "annual income layout opt-in")
        config_raw = config.read_bytes()
        if json.loads(config_raw).get(symbol) is not True:
            raise ValueError("PARENT_LAYOUT_INCOME_EXPLICIT_OPT_IN_REQUIRED")
        context = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(identity, base_binding=context["source_binding"],
                        selected_from=dict(path=CONFIG, sha256=_hash(config_raw)))
    else:
        manifest = base.legacy._bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("PARENT_LAYOUT_INCOME_MANIFEST_CHANGED")
        context = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
    fields = set(driver.FIELDS) | {"tax", "parent_profit"}
    evidence = deepcopy(context["evidence"])
    if any(row["period_basis"] == "FY" and row["field"] in fields for row in evidence):
        raise ValueError("PARENT_LAYOUT_INCOME_REQUIRES_MISSING_ANNUAL_BASELINE")
    sources = [source for source in context["supplemental_sources"] if source["period"].endswith("-12-31")]
    if len(sources) != 1:
        raise ValueError("PARENT_LAYOUT_ANNUAL_SOURCE_REQUIRED")
    source = sources[0]
    original = require_inside(root / "runtime", root / source["path"], "annual income original")
    report = annual.parse_paginated_annual_income(
        pages=base.legacy.pdf_text.extract_pages(original), source=source, issuer_name=context["issuer_name"])
    rows = [base.legacy._fact(row) for row in report["evidence"] if row["field"] in fields]
    if _hash(original.read_bytes()) != source["sha256"]:
        raise ValueError("HORIZON_ORIGINAL_CHANGED_DURING_EXTRACTION")
    for row in rows:
        if row["pdf_sha256"] != source["sha256"] or row["available_at"] != source["available_at"]:
            raise ValueError("HORIZON_STATEMENT_ROW_BINDING_INVALID")
        evidence.append(dict(row, receipt_binding=source["receipt_binding"]))
    if len(evidence) > 100 or len({row["id"] for row in evidence}) != len(evidence):
        raise ValueError("HORIZON_EVIDENCE_LIMIT_OR_DUPLICATE")
    raw = _bytes(manifest)
    digest = _hash(raw)
    relative = Path("runtime") / VERSION / (digest + ".json")
    expected = dict(path=relative.as_posix(), sha256=digest)
    if binding is not None and binding != expected:
        raise ValueError("PARENT_LAYOUT_INCOME_MANIFEST_CHANGED")
    context = {**context, "evidence": evidence, "source_binding": expected,
               "source_adapter_version": VERSION, "base_source_binding": manifest["base_binding"],
               "implementation_sha256": identity["implementation_sha256"]}
    context.pop("snapshot_fingerprint")
    context["snapshot_fingerprint"] = _hash(_bytes(context))
    if base.budget.measure_compact_context_chars(context) > base.legacy.MAX_CONTEXT_CHARS:
        raise ValueError("HORIZON_SOURCE_CONTEXT_OVER_BUDGET")
    path = require_inside(root, root / relative, "parent layout annual income manifest")
    try:
        write_new_bytes(path, raw)
    except FileExistsError:
        base.legacy._bound(root, expected)
    return context
