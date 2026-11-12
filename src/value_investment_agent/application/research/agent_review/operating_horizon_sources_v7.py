"""Bind the original return-plan terms together with the later approval vote.

This is historical policy evidence, not future distributable cash or a payout.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re

from . import operating_horizon_sources_v6 as approved_sources
from . import operating_horizon_sources_v1 as base_sources
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import pdf_text

VERSION = "operating-horizon-sources-v7"
CONFIG = "config/current-operating-return-plan-text-v1.json"
MAX_CONTEXT_CHARS = 75000


def implementation():
    return {**approved_sources.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    raw = (root / CONFIG).read_bytes()
    config = json.loads(raw)
    if config.get("schema_version") != "operating-return-plan-text-selection-v1" or config.get("action") != "no_order":
        raise ValueError("RETURN_PLAN_SELECTION_INVALID")
    selected = config.get("cases", {}).get(symbol)
    if (not isinstance(selected, dict)
            or set(selected) != {"receipt_path", "receipt_sha256", "source_id", "published_date", "plan_period"}
            or not isinstance(selected["receipt_path"], str) or not selected["receipt_path"].startswith("runtime/")
            or not isinstance(selected["receipt_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", selected["receipt_sha256"])
            or not isinstance(selected["source_id"], str) or not re.fullmatch(r"cninfo:[0-9]+", selected["source_id"])
            or not isinstance(selected["published_date"], str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", selected["published_date"])
            or not isinstance(selected["plan_period"], str) or not re.fullmatch(r"20[0-9]{2}-12-31", selected["plan_period"])):
        raise ValueError("RETURN_PLAN_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def _plan(root, symbol, issuer, selected, now):
    receipt_path = require_inside(root / "runtime", root / selected["receipt_path"], "return plan receipt")
    raw = receipt_path.read_bytes()
    if _hash(raw) != selected["receipt_sha256"]:
        raise ValueError("RETURN_PLAN_RECEIPT_CHANGED")
    receipt = json.loads(raw)
    expected_url = ("https://static.cninfo.com.cn/finalpage/" + selected["published_date"]
                    + "/" + selected["source_id"].split(":", 1)[1] + ".PDF")
    if (receipt.get("schema_version") != "bound-public-notice-v1" or receipt.get("symbol") != symbol
            or receipt.get("issuer_name") != issuer or receipt.get("source_id") != selected["source_id"]
            or receipt.get("published_date") != selected["published_date"]
            or receipt.get("source_url") != expected_url or receipt.get("action") != "no_order"):
        raise ValueError("RETURN_PLAN_RECEIPT_IDENTITY_INVALID")
    acquired = datetime.fromisoformat(receipt["acquired_at"])
    if acquired.utcoffset() is None or acquired > now:
        raise ValueError("RETURN_PLAN_AFTER_CUTOFF")
    original = require_inside(root / "runtime", root / receipt["path"], "return plan original")
    if _hash(original.read_bytes()) != receipt["sha256"]:
        raise ValueError("RETURN_PLAN_ORIGINAL_CHANGED")
    pages = pdf_text.extract_pages(original, limit=4)
    if not pages or symbol not in pages[0] or issuer not in "".join(pages).replace(" ", ""):
        raise ValueError("RETURN_PLAN_ISSUER_NOT_PROVEN")
    matches = []
    for page_number, page in enumerate(pages, 1):
        compact = re.sub(r"\s+", "", page)
        match = re.search(
            r"2025-2027年度，公司每年度现金分红总额占当年归属于母公司股东净利润的比例不低于75%，"
            r"且每股派发现金红利金额不低于2024年度每股派发现金红利1\.22元（含税）", compact)
        if match:
            matches.append((page_number, match.group()))
    if len(matches) != 1 or "在满足公司生产经营的资金需求" not in "".join(pages).replace("\n", ""):
        raise ValueError("RETURN_PLAN_TERMS_NOT_PROVEN")
    page_number, excerpt = matches[0]
    if _hash(original.read_bytes()) != receipt["sha256"]:
        raise ValueError("RETURN_PLAN_ORIGINAL_CHANGED_DURING_EXTRACTION")
    row = dict(id=receipt["source_id"] + ":conditional-return-plan", source_id=receipt["source_id"],
        pdf_sha256=receipt["sha256"], available_at=receipt["acquired_at"],
        period=selected["plan_period"], period_basis="FY", scope="DISCLOSED_CONDITIONAL_RETURN_PLAN",
        unit="TEXT", text=excerpt, text_sha256=_hash(excerpt.encode("utf-8")),
        physical_page=page_number, kind="PLAN_TARGET_NOT_FUTURE_CASH_OR_PAYMENT",
        receipt_binding=deepcopy(selected))
    source = dict(source_id=receipt["source_id"], path=receipt["path"], sha256=receipt["sha256"],
        source_url=receipt["source_url"], available_at=receipt["acquired_at"],
        scope="HISTORICAL_CONDITIONAL_POLICY_NOT_FORECAST")
    return row, source


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("RETURN_PLAN_AS_OF_INVALID")
    selected, config_binding = _selection(root, symbol)
    if binding is None:
        base = approved_sources.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=deepcopy(selected), selected_from=config_binding, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"), "return plan manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = base_sources._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("selection") != selected or manifest.get("selected_from") != config_binding
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("RETURN_PLAN_MANIFEST_CHANGED")
        base = approved_sources.build_operating_horizon_source_context(
            root=root, symbol=symbol, now=now, binding=manifest["base_binding"])
        path = None
    if base["source_binding"] != manifest["base_binding"] or _hash(_bytes(base)) != manifest["base_context_sha256"]:
        raise ValueError("RETURN_PLAN_BASE_CHANGED")
    row, source = _plan(root, symbol, base["issuer_name"], selected, now)
    value = deepcopy(base)
    if len(value["evidence"]) >= 100 or any(item["id"] == row["id"] for item in value["evidence"]):
        raise ValueError("RETURN_PLAN_EVIDENCE_LIMIT_OR_DUPLICATE")
    value["evidence"].append(row)
    value["supplemental_sources"].append(source)
    value["limitations"].append("75% of attributable profit and 1.22 CNY/share are conditional policy floors; neither proves parent cash capacity")
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
        implementation_sha256=manifest["implementation_sha256"])
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items() if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("RETURN_PLAN_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base_sources._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value
