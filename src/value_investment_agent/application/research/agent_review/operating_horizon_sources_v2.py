"""Versioned public-notice supplement for the existing D2 source context.

The v1 source loader and its historical manifests remain unchanged. A new
manifest pins one official notice receipt plus the exact v1 base binding.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re

from . import operating_horizon_sources_v1 as v1
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import official_dividend_notice_ocr_v1 as notice

VERSION = "operating-horizon-sources-v2"
CONFIG = "config/current-operating-public-notices-v1.json"
# Measured 600519 FY/H1 plus the pinned notice is 64,774 characters. No rows
# are truncated; v1 retains its own 64,000-character historical cap.
MAX_CONTEXT_CHARS = 65536


def implementation():
    return {**v1.implementation(),
        notice.__name__: _hash(Path(notice.__file__).read_bytes()),
        __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    config_path = root / CONFIG
    raw = config_path.read_bytes()
    config = json.loads(raw)
    if config.get("schema_version") != "operating-public-notice-selection-v1" or config.get("action") != "no_order":
        raise ValueError("PUBLIC_NOTICE_CONFIG_INVALID")
    selected = config.get("cases", {}).get(symbol)
    if (not isinstance(selected, dict) or set(selected) != {"receipt_path", "receipt_sha256"}
            or not isinstance(selected["receipt_path"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", selected["receipt_sha256"])):
        raise ValueError("PUBLIC_NOTICE_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("PUBLIC_NOTICE_AS_OF_INVALID")
    if binding is None:
        selected, config_binding = _selection(root, symbol)
        base = v1.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol,
            as_of=now.isoformat(), base_binding=deepcopy(base["source_binding"]),
            base_context_sha256=_hash(_bytes(base)), selected_from=config_binding,
            selection=deepcopy(selected), implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root, root / "runtime" / VERSION / (_hash(raw) + ".json"),
                              "public notice manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = v1._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("PUBLIC_NOTICE_MANIFEST_CHANGED")
        selected, config_binding = _selection(root, symbol)
        if manifest.get("selection") != selected or manifest.get("selected_from") != config_binding:
            raise ValueError("PUBLIC_NOTICE_SELECTION_CHANGED")
        base = v1.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if (base["source_binding"] != manifest["base_binding"]
            or _hash(_bytes(base)) != manifest["base_context_sha256"]):
        raise ValueError("PUBLIC_NOTICE_BASE_CONTEXT_CHANGED")
    receipt_path = require_inside(root, root / selected["receipt_path"], "public notice receipt")
    if _hash(receipt_path.read_bytes()) != selected["receipt_sha256"]:
        raise ValueError("PUBLIC_NOTICE_RECEIPT_HASH_CHANGED")
    proposal = notice.replay_proposed_dividend(
        root=root, receipt_path=receipt_path, symbol=symbol,
        issuer_name=base["issuer_name"], as_of=now)
    if proposal["receipt_sha256"] != selected["receipt_sha256"]:
        raise ValueError("PUBLIC_NOTICE_REPLAY_BINDING_CHANGED")
    text = (f"2025年年度利润分配拟向全体股东每股派发现金红利{proposal['per_share_cny']}元；"
            f"按公告时可参与分配股数{proposal['entitled_shares']}股，拟派现金红利"
            f"{proposal['proposed_total_cny']}元；本次分配方案尚需提交公司股东会审议。"
            "这是历史提案，不证明实际支付或未来母公司现金可达、维护投入及分红政策。")
    row = dict(id=f"cninfo:{proposal['source_url'].split('/')[-1].split('.')[0]}:ocr-p2-proposal",
        source_id=f"cninfo:{proposal['source_url'].split('/')[-1].split('.')[0]}",
        pdf_sha256=proposal["original_sha256"], available_at=proposal["available_at"],
        period="2025-12-31", period_basis="FY", scope="ISSUER_REPORTED_DIVIDEND_PROPOSAL",
        unit="TEXT", text=text, text_sha256=_hash(text.encode("utf-8")),
        physical_page=proposal["physical_page"],
        kind="OCR_VERIFIED_DERIVED_PROPOSAL_NOT_PAYMENT_OR_FORECAST_POLICY",
        receipt_binding=deepcopy(selected))
    value = deepcopy(base)
    if len(value["evidence"]) >= 100 or any(item["id"] == row["id"] for item in value["evidence"]):
        raise ValueError("PUBLIC_NOTICE_EVIDENCE_LIMIT_OR_DUPLICATE")
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
                 implementation_sha256=manifest["implementation_sha256"])
    value["evidence"].append(row)
    value["supplemental_sources"].append(dict(source_id=row["source_id"],
        path=selected["receipt_path"], sha256=selected["receipt_sha256"],
        original_sha256=proposal["original_sha256"], available_at=proposal["available_at"],
        source_url=proposal["source_url"], scope=proposal["status"]))
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items()
                                                  if k != "snapshot_fingerprint"}))
    context_chars = len(_bytes(value).decode("utf-8"))
    if context_chars > MAX_CONTEXT_CHARS:
        raise ValueError("PUBLIC_NOTICE_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            v1._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value
