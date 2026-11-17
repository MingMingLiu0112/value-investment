"""Historical 600519 Q3 monetary-capital bridge; never infer shares from CNY."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re

import pypdfium2 as pdfium

from .current_capital_h1_ocr_overlay_v2 import read_capital_with_h1_shares
from ...infrastructure.filings.official_halfyear_shares_ocr_v2 import (
    SEALED_OCR_PACKAGE_SHA256, _availability,
)
from ...infrastructure.filings.pdfium_runtime import serialized_pdfium
from ...infrastructure.filings.q3_h1_capital_scope_v1 import SUPPORTED_SYMBOL

REGISTRY = "config/current-capital-q3-h1-bridge-v1.json"
VERSION = "current-capital-q3-h1-bridge-v1"
EXPECTED_MODELS = {Path(name).name: digest for name, digest in SEALED_OCR_PACKAGE_SHA256.items()
                   if name.endswith(".onnx")}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Q3_DUPLICATE_KEY")
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def _registered(root, item, expected_dir=None):
    if not isinstance(item, dict) or set(item) != {"path", "sha256"}:
        raise ValueError("Q3_REGISTRATION_INVALID")
    relative, digest = item["path"], item["sha256"]
    if (not isinstance(relative, str) or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or "\\" in relative or Path(relative).is_absolute()
            or PureWindowsPath(relative).drive or ".." in PureWindowsPath(relative).parts):
        raise ValueError("Q3_REGISTRATION_INVALID")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or (expected_dir is not None and path.parent != expected_dir):
        raise ValueError("Q3_REGISTRATION_INVALID")
    if not path.is_file():
        raise ValueError("Q3_REGISTERED_SOURCE_MISSING")
    if path.stat().st_size > 64 * 1024 * 1024 or _sha(path) != digest:
        raise ValueError("Q3_REGISTERED_SOURCE_HASH_MISMATCH")
    return path


@serialized_pdfium
def _pdf_evidence(path):
    doc = pdfium.PdfDocument(path)
    try:
        if len(doc) < 7:
            raise ValueError("Q3_PAGES_MISSING")
        texts = {}
        pixel_sha = None
        for number in (5, 7):
            page = doc[number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    texts[number] = text_page.get_text_range()
                finally:
                    text_page.close()
                if number == 7:
                    bitmap = page.render(scale=3)
                    try:
                        pixel_sha = hashlib.sha256(bytes(bitmap.buffer)).hexdigest()
                    finally:
                        bitmap.close()
            finally:
                page.close()
        return texts, pixel_sha
    finally:
        doc.close()


def read_q3_h1_capital_bridge(root: Path, as_of: datetime) -> dict:
    """Return source-bound CNY row, H1 shares, and UNKNOWN Q3 share count."""
    root = Path(root).resolve()
    result = {"schema_version": VERSION, "status": "UNASSESSABLE", "symbol": SUPPORTED_SYMBOL,
              "report_period_end": "2026-09-30", "q3_ordinary_shares": "UNKNOWN",
              "h1_ordinary_shares": "UNKNOWN", "h1_to_q3_continuity": "UNKNOWN",
              "current_continuity": "UNPROVEN", "formal_eligibility": False,
              "action": "no_order"}
    try:
        if not isinstance(as_of, datetime) or as_of.utcoffset() is None:
            raise ValueError("Q3_AWARE_AS_OF_REQUIRED")
        registry = root / REGISTRY
        if not registry.is_file():
            raise ValueError("Q3_REGISTRY_MISSING")
        raw = registry.read_bytes()
        if len(raw) > 1024 * 1024:
            raise ValueError("Q3_REGISTRY_TOO_LARGE")
        data = _json(registry)
        if (not isinstance(data, dict) or set(data) != {"schema_version", "action", "symbol",
                "issuer_name", "h1_registry", "q3"} or data["schema_version"] != VERSION
                or data["action"] != "no_order" or data["symbol"] != SUPPORTED_SYMBOL
                or data["issuer_name"] != "贵州茅台酒股份有限公司"):
            raise ValueError("Q3_REGISTRY_INVALID")
        if data["h1_registry"]["path"] != "config/current-capital-h1-ocr-v2.json":
            raise ValueError("Q3_H1_REGISTRATION_INVALID")
        _registered(root, data["h1_registry"], root / "config")
        q3 = data["q3"]
        if (not isinstance(q3, dict) or set(q3) != {"source_url", "available_at",
                "report_period_end", "comparison_period_end", "original", "page_7_image", "page_7_ocr"}
                or q3["report_period_end"] != "2026-09-30"
                or q3["comparison_period_end"] != "2025-12-31"
                or q3["source_url"] != "https://static.cninfo.com.cn/finalpage/2026-10-31/1225649896.PDF"):
            raise ValueError("Q3_REGISTRY_INVALID")
        _availability({"source_url": q3["source_url"],
                       "original_available_at": q3["available_at"]}, "original", as_of)
        original = _registered(root, q3["original"])
        if not q3["original"]["path"].startswith("runtime/"):
            raise ValueError("Q3_REGISTRATION_INVALID")
        image = _registered(root, q3["page_7_image"], original.parent)
        ocr_path = _registered(root, q3["page_7_ocr"], original.parent)
        if (original.name, image.name, ocr_path.name) != ("original.pdf", "page-7.png", "page-7.ocr.json"):
            raise ValueError("Q3_REGISTRATION_INVALID")
        packet = _json(ocr_path)
        texts, pixel_sha = _pdf_evidence(original)
        if (packet.get("schema_version") != "official-quarter-ocr-raw-v1"
                or packet.get("status") != "OCR_REQUIRES_SOURCE_RECONCILIATION"
                or packet.get("action") != "no_order" or packet.get("symbol") != SUPPORTED_SYMBOL
                or packet.get("report_period") != "2026-09-30"
                or packet.get("physical_page") != 7
                or packet.get("original_sha256") != q3["original"]["sha256"]
                or packet.get("image_sha256") != q3["page_7_image"]["sha256"]
                or packet.get("pixel_sha256") != pixel_sha
                or packet.get("render_engine") != "pypdfium2" or packet.get("render_scale") != 3
                or packet.get("ocr_engine") != "rapidocr-3.10.0"
                or packet.get("model_sha256") != EXPECTED_MODELS):
            raise ValueError("Q3_OCR_BINDING_INVALID")
        p5 = re.sub(r"\s+", "", texts[5])
        if ("合并资产负债表2026年9月30日" not in p5
                or "单位：元币种：人民币" not in p5
                or "项目2026年9月30日2025年12月31日" not in p5
                or data["issuer_name"] not in p5):
            raise ValueError("Q3_CURRENCY_UNIT_OR_COLUMNS_INVALID")
        rows = packet.get("rows")
        if not isinstance(rows, list):
            raise ValueError("Q3_OCR_ROWS_INVALID")
        labels = [r for r in rows if r.get("text") == "实收资本（或股本）"
                  and r.get("confidence", 0) >= 0.95]
        if len(labels) != 1:
            raise ValueError("Q3_CAPITAL_LABEL_INVALID")
        label_y = sum(p[1] for p in labels[0]["box"]) / 4
        values = sorted((r for r in rows if r.get("text") in
                         ("1,250,081,601.00", "1,252,270,215.00")
                         and r.get("confidence", 0) >= 0.95
                         and abs(sum(p[1] for p in r["box"]) / 4 - label_y) < 15),
                        key=lambda r: sum(p[0] for p in r["box"]) / 4)
        if len(values) != 2 or [r["text"] for r in values] != [
                "1,250,081,601.00", "1,252,270,215.00"]:
            raise ValueError("Q3_CAPITAL_ROW_INVALID")
        native7 = re.sub(r"\s+", "", texts[7])
        if "1,250,081,601.001,252,270,215.00" not in native7:
            raise ValueError("Q3_NATIVE_NUMERIC_MISMATCH")
        h1 = read_capital_with_h1_shares(root, SUPPORTED_SYMBOL, as_of)["h1_share_observation"]
        if h1["status"] != "VERIFIED":
            raise ValueError("Q3_H1_NOT_VERIFIED:" + h1.get("error_code", h1["status"]))
        if registry.read_bytes() != raw or any(_sha(path) != item["sha256"] for path, item in (
                (original, q3["original"]), (image, q3["page_7_image"]),
                (ocr_path, q3["page_7_ocr"]))):
            raise ValueError("Q3_SOURCE_CHANGED_DURING_READ")
        result.update(status="MONETARY_CAPITAL_VERIFIED_SHARES_UNKNOWN",
                      q3_monetary_capital_cny=str(Decimal(values[0]["text"].replace(",", ""))),
                      q3_comparison_capital_cny=str(Decimal(values[1]["text"].replace(",", ""))),
                      monetary_capital_unit="CNY", monetary_capital_statement="consolidated_balance_sheet",
                      monetary_capital_page=7, statement_header_page=5,
                      q3_share_count_basis="UNKNOWN_NO_ENTITY_BOUND_PAR_VALUE_OR_Q3_SHARE_STRUCTURE",
                      h1_ordinary_shares=h1["ordinary_shares"], h1_report_period_end="2026-06-30",
                      h1_source=h1["source"], q3_source={"source_url": q3["source_url"],
                      "available_at": q3["available_at"], "original_sha256": q3["original"]["sha256"],
                      "image_sha256": q3["page_7_image"]["sha256"],
                      "ocr_sha256": q3["page_7_ocr"]["sha256"]},
                      registry_sha256=hashlib.sha256(raw).hexdigest())
    except (ValueError, OSError, TypeError, KeyError, IndexError) as error:
        result["error_code"] = str(error) if isinstance(error, ValueError) else type(error).__name__
    return result
