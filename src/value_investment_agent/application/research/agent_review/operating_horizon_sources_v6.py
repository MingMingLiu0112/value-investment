"""Bind an approved shareholder return plan to D2 without assuming future cash."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import re

from . import operating_horizon_sources_v1 as base_sources
from .task_execution_v1 import _bytes, _hash
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.filings import pdf_text

VERSION = "operating-horizon-sources-v6"
CONFIG = "config/current-operating-approved-dividend-plans-v1.json"
MAX_CONTEXT_CHARS = 70000


def implementation():
    return {**base_sources.implementation(),
            pdf_text.__name__: _hash(Path(pdf_text.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


def _selection(root, symbol):
    raw = (root / CONFIG).read_bytes()
    config = json.loads(raw)
    if (config.get("schema_version") != "operating-approved-dividend-plan-selection-v1"
            or config.get("action") != "no_order" or not isinstance(config.get("cases"), dict)):
        raise ValueError("APPROVED_PLAN_SELECTION_INVALID")
    selected = config["cases"].get(symbol)
    if (not isinstance(selected, dict) or set(selected) != {"receipt_path", "receipt_sha256", "source_id", "published_date", "plan_period", "resolution_title"}
            or not isinstance(selected["receipt_path"], str)
            or not selected["receipt_path"].startswith("runtime/")
            or not isinstance(selected["receipt_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", selected["receipt_sha256"])
            or not isinstance(selected["source_id"], str)
            or not re.fullmatch(r"cninfo:[0-9]+", selected["source_id"])
            or not isinstance(selected["published_date"], str)
            or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}", selected["published_date"])
            or not isinstance(selected["plan_period"], str)
            or not re.fullmatch(r"20[0-9]{2}-12-31", selected["plan_period"])
            or not isinstance(selected["resolution_title"], str)
            or not 5 <= len(selected["resolution_title"]) <= 120):
        raise ValueError("APPROVED_PLAN_CASE_NOT_CONFIGURED")
    return selected, dict(path=CONFIG, sha256=_hash(raw))


def _resolution(root, symbol, base, selected, now):
    receipt_path = require_inside(root / "runtime", root / selected["receipt_path"], "plan receipt")
    raw = receipt_path.read_bytes()
    if _hash(raw) != selected["receipt_sha256"]:
        raise ValueError("APPROVED_PLAN_RECEIPT_CHANGED")
    receipt = json.loads(raw)
    if (receipt.get("schema_version") != "bound-public-notice-v1"
            or receipt.get("symbol") != symbol or receipt.get("issuer_name") != base["issuer_name"]
            or receipt.get("source_id") != selected["source_id"]
            or receipt.get("published_date") != selected["published_date"]
            or receipt.get("action") != "no_order"):
        raise ValueError("APPROVED_PLAN_RECEIPT_IDENTITY_INVALID")
    acquired = datetime.fromisoformat(receipt["acquired_at"])
    if acquired.utcoffset() is None or acquired > now:
        raise ValueError("APPROVED_PLAN_AFTER_CUTOFF")
    original = require_inside(root / "runtime", root / receipt["path"], "plan original")
    expected_url = ("https://static.cninfo.com.cn/finalpage/" + selected["published_date"]
                    + "/" + selected["source_id"].split(":", 1)[1] + ".PDF")
    if (_hash(original.read_bytes()) != receipt["sha256"] or receipt["source_url"] != expected_url):
        raise ValueError("APPROVED_PLAN_ORIGINAL_CHANGED")
    pages = pdf_text.extract_pages(original, limit=4)
    if not pages or symbol not in pages[0] or base["issuer_name"] not in "".join(pages).replace(" ", ""):
        raise ValueError("APPROVED_PLAN_ISSUER_NOT_PROVEN")
    text = "\n".join(pages)
    marker = "议案名称：" + selected["resolution_title"]
    match = re.search(re.escape(marker) + r"\s*审议结果：通过", text)
    if match is None or text.count(marker) != 1:
        raise ValueError("APPROVED_PLAN_VOTE_NOT_PROVEN")
    excerpt = text[match.start():match.end()]
    row = dict(id=receipt["source_id"] + ":approved-return-plan", source_id=receipt["source_id"],
        pdf_sha256=receipt["sha256"], available_at=receipt["acquired_at"],
        period=selected["plan_period"], period_basis="FY", scope="SHAREHOLDER_APPROVED_RETURN_PLAN",
        unit="TEXT", text=excerpt, text_sha256=_hash(excerpt.encode("utf-8")),
        physical_page=next(i for i, page in enumerate(pages, 1) if marker in page),
        kind="APPROVED_PLAN_NOT_FUTURE_PAYMENT_OR_CASH_CAPACITY",
        receipt_binding=deepcopy(selected))
    if _hash(original.read_bytes()) != receipt["sha256"]:
        raise ValueError("APPROVED_PLAN_ORIGINAL_CHANGED_DURING_EXTRACTION")
    return row, dict(source_id=receipt["source_id"], path=receipt["path"],
        sha256=receipt["sha256"], receipt_binding=deepcopy(selected),
        source_url=receipt["source_url"], available_at=receipt["acquired_at"],
        scope="HISTORICAL_APPROVAL_NOT_FORECAST")


def build_operating_horizon_source_context(*, root, symbol, now, binding=None):
    root = Path(root).resolve()
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("APPROVED_PLAN_AS_OF_INVALID")
    selected, config_binding = _selection(root, symbol)
    if binding is None:
        base = base_sources.build_operating_horizon_source_context(root=root, symbol=symbol, now=now)
        manifest = dict(schema_version=VERSION, action="no_order", symbol=symbol, as_of=now.isoformat(),
            base_binding=deepcopy(base["source_binding"]), base_context_sha256=_hash(_bytes(base)),
            selection=deepcopy(selected), selected_from=config_binding, implementation_sha256=implementation())
        raw = _bytes(manifest)
        path = require_inside(root / "runtime", root / "runtime" / VERSION / (_hash(raw) + ".json"), "plan manifest")
        binding = dict(path=path.relative_to(root).as_posix(), sha256=_hash(raw))
    else:
        manifest = base_sources._bound(root, binding)
        if (manifest.get("schema_version") != VERSION or manifest.get("action") != "no_order"
                or manifest.get("symbol") != symbol or manifest.get("as_of") != now.isoformat()
                or manifest.get("selection") != selected or manifest.get("selected_from") != config_binding
                or manifest.get("implementation_sha256") != implementation()):
            raise ValueError("APPROVED_PLAN_MANIFEST_CHANGED")
        base = base_sources.build_operating_horizon_source_context(root=root, symbol=symbol,
            now=now, binding=manifest["base_binding"])
        path = None
    if base["source_binding"] != manifest["base_binding"] or _hash(_bytes(base)) != manifest["base_context_sha256"]:
        raise ValueError("APPROVED_PLAN_BASE_CHANGED")
    row, source = _resolution(root, symbol, base, selected, now)
    value = deepcopy(base)
    if len(value["evidence"]) >= 100 or any(item["id"] == row["id"] for item in value["evidence"]):
        raise ValueError("APPROVED_PLAN_EVIDENCE_LIMIT_OR_DUPLICATE")
    value["evidence"].append(row)
    value["supplemental_sources"].append(source)
    value["limitations"].append("Shareholder approval does not prove future payout or parent cash capacity")
    value.update(schema_version=VERSION, source_binding=deepcopy(binding),
        implementation_sha256=manifest["implementation_sha256"])
    value["snapshot_fingerprint"] = _hash(_bytes({k: v for k, v in value.items() if k != "snapshot_fingerprint"}))
    if len(_bytes(value).decode("utf-8")) > MAX_CONTEXT_CHARS:
        raise ValueError("APPROVED_PLAN_CONTEXT_OVER_BUDGET")
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            base_sources._bound(root, binding)
        else:
            write_new_bytes(path, _bytes(manifest))
    return value
