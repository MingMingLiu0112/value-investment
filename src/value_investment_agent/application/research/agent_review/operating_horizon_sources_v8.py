"""Versioned return-plan source with its funding and approval conditions."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import re

from . import operating_horizon_sources_v7 as previous
from . import operating_horizon_sources_v1 as base_sources
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import pdf_text

VERSION = "operating-horizon-sources-v8"
CONFIG = previous.CONFIG
MAX_CONTEXT_CHARS = 77000
CONDITION = "在满足公司生产经营的资金需求及《公司章程》利润分配政策下，"
PROCEDURE = "公司利润分配方案由董事会拟定，经股东大会审议通过后实施。"


def implementation():
    from . import operating_cash_policy_task_v2
    return {**previous.implementation(),
        operating_cash_policy_task_v2.__name__: _hash(Path(operating_cash_policy_task_v2.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


def _conditions(root, base, now):
    plan = [row for row in base["evidence"]
            if row.get("id") == "cninfo:1224808850:conditional-return-plan"]
    sources = [source for source in base["supplemental_sources"]
               if source.get("source_id") == "cninfo:1224808850"]
    approved = [row for row in base["evidence"]
                if row.get("id") == "cninfo:1225321219:approved-return-plan"]
    if len(plan) != 1 or len(sources) != 1 or len(approved) != 1:
        raise ValueError("V8_PLAN_APPROVAL_IDENTITY_INVALID")
    source = sources[0]
    path = require_inside(root / "runtime", root / source["path"], "return plan original")
    if _hash(path.read_bytes()) != source["sha256"] or plan[0]["pdf_sha256"] != source["sha256"]:
        raise ValueError("V8_PLAN_ORIGINAL_CHANGED")
    pages = pdf_text.extract_pages(path, limit=4)
    compact = [re.sub(r"\s+", "", page) for page in pages]
    conditions = [i for i, page in enumerate(compact, 1) if CONDITION in page]
    procedures = [i for i, page in enumerate(compact, 1) if PROCEDURE in page]
    if (len(conditions) != 1 or len(procedures) != 1
            or conditions[0] > plan[0]["physical_page"] or procedures[0] < plan[0]["physical_page"]):
        raise ValueError("V8_PLAN_CONDITIONS_NOT_PROVEN")
    if _hash(path.read_bytes()) != source["sha256"]:
        raise ValueError("V8_PLAN_ORIGINAL_CHANGED_DURING_EXTRACTION")
    return dict(id="cninfo:1224808850:return-plan-conditions", source_id=source["source_id"],
        pdf_sha256=source["sha256"], available_at=source["available_at"],
        period=plan[0]["period"], period_basis="FY", scope="DISCLOSED_CONDITIONAL_RETURN_PLAN",
        unit="TEXT", text=CONDITION + "\n" + PROCEDURE,
        text_sha256=_hash((CONDITION + "\n" + PROCEDURE).encode("utf-8")),
        physical_pages=[conditions[0], procedures[0]],
        text_composition="TWO_VERBATIM_FRAGMENTS_FROM_SEPARATE_PAGES",
        kind="FUNDING_AND_APPROVAL_CONDITIONS_NOT_FORECAST", action="no_order")


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("V8_AS_OF_INVALID")
    selected, config_binding = previous._selection(root, symbol)
    if binding is None:
        base = previous.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=deepcopy(selected), selected_from=config_binding, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"), "v8 manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = base_sources._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("selection") != selected or manifest.get("selected_from") != config_binding
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("V8_MANIFEST_CHANGED")
        base = previous.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if base["source_binding"] != manifest["base_binding"] or _hash(_bytes(base)) != manifest["base_context_sha256"]:
        raise ValueError("V8_BASE_CHANGED")
    row = _conditions(root, base, now)
    value = deepcopy(base)
    if len(value["evidence"]) >= 100 or any(item["id"] == row["id"] for item in value["evidence"]):
        raise ValueError("V8_EVIDENCE_LIMIT_OR_DUPLICATE")
    value["evidence"].append(row)
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
        implementation_sha256=manifest["implementation_sha256"])
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items() if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("V8_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base_sources._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value
