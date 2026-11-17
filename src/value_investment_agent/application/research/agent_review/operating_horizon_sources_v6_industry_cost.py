"""Add audited industry-cost counterevidence to the sealed parent-trade context."""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path

from . import operating_horizon_sources_v5_parent_trade as base
from .operating_horizon_sources_v1 import _bound
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import industry_cost_composition as cost, pdf_text


VERSION = "operating-horizon-sources-v6-industry-cost"
CONFIG = "config/current-operating-industry-cost-v1.json"


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if now.utcoffset() is None:
        raise ValueError("INDUSTRY_COST_CUTOFF_INVALID")
    identity = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
                    implementation_sha256={m.__name__: _hash(Path(m.__file__).read_bytes())
                                           for m in (cost, pdf_text)})
    identity["implementation_sha256"][__name__] = _hash(Path(__file__).read_bytes())
    if binding is None:
        selection = json.loads((root / CONFIG).read_bytes())[symbol]
        original = base.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        raw = _bytes(dict(identity, selection=selection, base_binding=original["source_binding"],
                          base_context_sha256=_hash(_bytes(original))))
        digest = _hash(raw)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (digest + ".json"),
                              "industry cost manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=digest)
    else:
        path = None
        manifest = _bound(root, binding)
        if any(manifest.get(key) != value for key, value in identity.items()):
            raise ValueError("INDUSTRY_COST_MANIFEST_CHANGED")
        selection = manifest["selection"]
        original = base.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        if _hash(_bytes(original)) != manifest["base_context_sha256"]:
            raise ValueError("INDUSTRY_COST_BASE_CHANGED")
    if not isinstance(selection, dict) or set(selection) != {"source_id", "page", "year", "industry"}:
        raise ValueError("INDUSTRY_COST_SELECTION_INVALID")
    matches = [ref for ref in original["supplemental_sources"] if ref["source_id"] == selection["source_id"]]
    if len(matches) != 1 or original["symbol"] != symbol:
        raise ValueError("INDUSTRY_COST_SOURCE_NOT_IN_CONTEXT")
    source = matches[0]
    available = datetime.fromisoformat(source["available_at"])
    page = selection["page"]
    if available.utcoffset() is None or available > now or type(page) is not int or not 1 <= page <= 100:
        raise ValueError("INDUSTRY_COST_FUTURE_SOURCE_OR_PAGE_INVALID")
    pdf = require_inside(root, root / source["path"], "industry cost PDF")
    if _hash(pdf.read_bytes()) != source["sha256"]:
        raise ValueError("INDUSTRY_COST_PDF_CHANGED")
    pages = pdf_text.extract_pages(pdf, limit=page)
    evidence = cost.parse_industry_cost_composition(
        cover=pages[0], page=pages[page - 1], symbol=symbol, issuer_name=original["issuer_name"],
        fiscal_year=selection["year"], industry=selection["industry"])
    if _hash(pdf.read_bytes()) != source["sha256"]:
        raise ValueError("INDUSTRY_COST_PDF_CHANGED")
    ratios = evidence["labor_and_overhead_share_pct"]
    text = (f"{selection['industry']}（行业口径，非合并集团）{selection['year']}及上年"
            f"人工与制造费用的披露成本占比分别为{ratios[0]}%、{ratios[1]}%。材料及运输并不必然全随量变，"
            "人工及制造费用也不是纯固定成本。仅允许据此构造可反驳的分摊敏感性；"
            "解释集团其他业务和区间边界，不能将此数值写成已知固定成本率。"
            f"披露占比复算差异：{evidence['printed_share_discrepancies']}。")
    row = dict(id=f"{source['source_id']}:industry-cost-p{page}", source_id=source["source_id"],
               pdf_sha256=source["sha256"], physical_page=page, available_at=source["available_at"],
               period=evidence["periods"][0], period_basis="FY", scope="ISSUER_INDUSTRY_COST_COMPOSITION",
               unit="TEXT", field="industry_cost_composition", text=text,
               text_sha256=_hash(text.encode("utf-8")), kind="HISTORICAL_MIX_NOT_FIXED_COST_RATE")
    result = deepcopy(original)
    if len(result["evidence"]) >= 100 or any(e["id"] == row["id"] for e in result["evidence"]):
        raise ValueError("INDUSTRY_COST_EVIDENCE_LIMIT_OR_DUPLICATE")
    result["evidence"].append(row)
    result.update(source_binding=binding, source_adapter_version=VERSION,
                  implementation_sha256=identity["implementation_sha256"])
    result["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in result.items()
                                                  if k != "snapshot_fingerprint"}))
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _bound(root, binding)
        else:
            write_new_bytes(path, raw)
    return result
