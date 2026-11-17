"""Add the charter's annual distribution floor to a sealed reserve-rule context."""

from pathlib import Path

from . import operating_horizon_charter_sources_v1 as base
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import charter_cash_distribution_clause as floor

VERSION = "operating-horizon-charter-distribution-sources-v1"
CONFIG = base.CONFIG


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    identity = dict(version=VERSION, symbol=symbol, as_of=now.isoformat(), action="no_order",
        implementation_sha256={m: _hash(Path(p).read_bytes())
            for m, p in ((__name__, __file__), (floor.__name__, floor.__file__))})
    if binding is None:
        context = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(identity, charter_context_binding=context["source_binding"])
    else:
        manifest = base.base._bound(root, binding)
        if any(manifest.get(k) != v for k, v in identity.items()):
            raise ValueError("CHARTER_DISTRIBUTION_MANIFEST_CHANGED")
        context = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["charter_context_binding"])
    prior = base.base._bound(root, manifest["charter_context_binding"])
    source = prior["selection"]
    pdf = require_inside(root / "runtime", root / source["path"], "charter distribution PDF")
    rule = floor.read_annual_cash_floor(pdf, issuer=context["issuer_name"], expected_sha256=source["sha256"])
    reserve = context["evidence"][0]
    pct = rule["cash_floor_percent"]
    text = (f"母公司章程现金分红下限为当年可分配利润的{pct}%，条件为年度盈利且"
            "累计未分配利润为正。勿将该比例套用于合并归母利润，或视为未来目标和到账金额。")
    row = dict(reserve, id=reserve["source_id"] + ":annual_cash_distribution_floor",
        field="annual_cash_distribution_floor", physical_page=rule["physical_page"],
        scope="ISSUER_ARTICLES_DISTRIBUTABLE_PROFIT_FLOOR",
        text=text, text_sha256=_hash(text.encode("utf-8")))
    if len(context["evidence"]) >= 100 or any(e["id"] == row["id"] for e in context["evidence"]):
        raise ValueError("CHARTER_DISTRIBUTION_EVIDENCE_DUPLICATE_OR_LIMIT")
    if binding is None:
        raw = _bytes(manifest)
        digest = _hash(raw)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (digest + ".json"),
                              "charter distribution manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=digest)
        if path.exists():
            base.base._bound(root, binding)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_new_bytes(path, raw)
    result = dict(context, evidence=[row, *context["evidence"]], source_binding=binding,
                  source_adapter_version=VERSION, implementation_sha256=identity["implementation_sha256"])
    result.pop("snapshot_fingerprint", None)
    result["snapshot_fingerprint"] = _hash(_bytes(result))
    return result
