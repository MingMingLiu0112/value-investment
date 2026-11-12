"""Add an approved historical distribution to the existing bounded D2 corpus.

V1 and V2 source manifests and tasks remain immutable. This supplement never
promotes a scheduled historical distribution to a future payout assumption.
"""
from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re

from . import operating_horizon_sources_v2 as v2
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import official_dividend_implementation_v1 as implementation_notice

VERSION = "operating-horizon-sources-v3"
CONFIG = "config/current-operating-distribution-implementations-v1.json"
MAX_CONTEXT_CHARS = 68000


def implementation():
    return {**v2.implementation(),
        implementation_notice.__name__: _hash(Path(implementation_notice.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


def _selection(root: Path, symbol: str):
    raw = (root / CONFIG).read_bytes()
    config = json.loads(raw)
    if (config.get("schema_version") != "operating-distribution-implementation-selection-v1"
            or config.get("action") != "no_order"):
        raise ValueError("IMPLEMENTED_DISTRIBUTION_CONFIG_INVALID")
    selected = config.get("cases", {}).get(symbol)
    if (not isinstance(selected, dict) or set(selected) != {"receipt_path", "receipt_sha256"}
            or not isinstance(selected["receipt_path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", selected["receipt_sha256"])):
        raise ValueError("IMPLEMENTED_DISTRIBUTION_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("IMPLEMENTED_DISTRIBUTION_AS_OF_INVALID")
    if binding is None:
        selected, config_pin = _selection(root, symbol)
        base = v2.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol,
            as_of=now.isoformat(), base_binding=deepcopy(base["source_binding"]),
            base_context_sha256=_hash(_bytes(base)), selection=deepcopy(selected),
            selected_from=config_pin, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root, root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "implemented distribution manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = v2.v1._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("IMPLEMENTED_DISTRIBUTION_MANIFEST_CHANGED")
        selected, config_pin = _selection(root, symbol)
        if manifest.get("selection") != selected or manifest.get("selected_from") != config_pin:
            raise ValueError("IMPLEMENTED_DISTRIBUTION_SELECTION_CHANGED")
        base = v2.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if (base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("IMPLEMENTED_DISTRIBUTION_BASE_CHANGED")
    receipt = require_inside(root, root / selected["receipt_path"], "implemented distribution receipt")
    if _hash(receipt.read_bytes()) != selected["receipt_sha256"]:
        raise ValueError("IMPLEMENTED_DISTRIBUTION_RECEIPT_CHANGED")
    report = implementation_notice.replay_implemented_distribution(
        root=root, receipt_path=receipt, symbol=symbol,
        issuer_name=base["issuer_name"], as_of=now)
    if report["receipt_sha256"] != selected["receipt_sha256"] or report["action"] != "no_order":
        raise ValueError("IMPLEMENTED_DISTRIBUTION_REPLAY_CHANGED")
    text = (f"2025年年度权益分派经股东会审议通过：每股现金红利{report['per_share_cny']}元；"
        f"实施基数{report['entitled_shares']}股；公告金额{report['scheduled_total_cny']}元；"
        f"股权登记日{report['record_date']}，除息日{report['ex_date']}，"
        f"公告现金红利发放日{report['scheduled_payment_date']}。"
        "这是已批准的历史实施安排，不证明个人实际到账，也不证明未来派息比例、"
        "母公司资金可达、维持投入、营运资金或未来资本承诺。")
    row = dict(id=f"cninfo:{report['source_url'].split('/')[-1].split('.')[0]}:implemented-distribution",
        source_id=f"cninfo:{report['source_url'].split('/')[-1].split('.')[0]}",
        pdf_sha256=report["original_sha256"], available_at=report["available_at"],
        period="2025-12-31", period_basis="FY", scope="ISSUER_APPROVED_DISTRIBUTION_SCHEDULE",
        unit="TEXT", text=text, text_sha256=_hash(text.encode("utf-8")),
        physical_pages=report["physical_pages"],
        kind="VERIFIED_HISTORICAL_IMPLEMENTATION_NOT_PERSONAL_PAYMENT_OR_FORECAST_POLICY",
        receipt_binding=deepcopy(selected))
    value = deepcopy(base)
    if len(value["evidence"]) >= 100 or any(item["id"] == row["id"] for item in value["evidence"]):
        raise ValueError("IMPLEMENTED_DISTRIBUTION_EVIDENCE_LIMIT_OR_DUPLICATE")
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
                 implementation_sha256=manifest["implementation_sha256"])
    value["evidence"].append(row)
    value["supplemental_sources"].append(dict(source_id=row["source_id"],
        path=selected["receipt_path"], sha256=selected["receipt_sha256"],
        original_sha256=report["original_sha256"], available_at=report["available_at"],
        source_url=report["source_url"], scope=report["status"]))
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items()
                                                  if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("IMPLEMENTED_DISTRIBUTION_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            v2.v1._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value
