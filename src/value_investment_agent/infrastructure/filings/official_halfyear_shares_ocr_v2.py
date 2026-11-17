"""Read-only, source-bound half-year share quantity observation."""
import hashlib
from importlib.metadata import version
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

import pypdfium2 as pdfium

from .pdfium_runtime import serialized_pdfium

VERSION = "official-halfyear-shares-ocr-v2"
SEALED_OCR_PACKAGE_SHA256 = {
    "rapidocr-3.10.0.dist-info/METADATA": "71ff919d40d466dffa8736865649c985d28055e96e9c7eb7a5f09fa1b548ec54",
    "rapidocr/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
    "rapidocr/models/PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "rapidocr/models/PP-OCRv6_rec_small.onnx": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
}


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fail(code):
    raise ValueError(code)


@serialized_pdfium
def _read_pdfium_pages(path, pages, renders=()):
    """Keep each native document and its cleanup inside the shared lock."""
    doc = pdfium.PdfDocument(path)
    texts, raw_hashes = {}, {}
    try:
        for number in pages:
            page = doc[number - 1]
            try:
                text_page = page.get_textpage()
                try:
                    texts[number] = text_page.get_text_range()
                finally:
                    text_page.close()
                if number in renders:
                    bitmap = page.render(scale=3)
                    try:
                        raw_hashes[number] = hashlib.sha256(bytes(bitmap.buffer)).hexdigest()
                    finally:
                        bitmap.close()
            finally:
                page.close()
    finally:
        doc.close()
    return texts, raw_hashes


def _pdfium_evidence(original, notice):
    """Read native text and rendered page pixels from both bound originals."""
    native, images = _read_pdfium_pages(original, (1, 22, 23), (22, 23))
    cross, _ = _read_pdfium_pages(notice, (1, 2, 3))
    return native, images, cross


def _availability(manifest, prefix, as_of):
    url = manifest["source_url" if prefix == "original" else "cross_notice_url"]
    raw = manifest.get(f"{prefix}_available_at")
    try:
        disclosed = date.fromisoformat(url.split("/finalpage/")[1].split("/")[0])
        available = datetime.fromisoformat(raw)
        if available.tzinfo is None or available.utcoffset() is None:
            raise ValueError
        # Date-only CNINFO evidence permits availability from the next
        # calendar day, never a guessed intra-day publication instant.
        local = available.astimezone(timezone(timedelta(hours=8)))
        if (local.date() != disclosed + timedelta(days=1)
                or local.time().replace(tzinfo=None) != datetime.min.time()):
            raise ValueError
    except (TypeError, AttributeError, IndexError, ValueError):
        _fail("H1_SOURCE_AVAILABILITY_INVALID")
    if available.astimezone(timezone.utc) > as_of.astimezone(timezone.utc):
        _fail("H1_SOURCE_NOT_AVAILABLE_AS_OF")
    return available


def replay_halfyear_shares(*, root: Path, symbol: str, issuer_name: str,
                           report_year: int, expected_original_sha256: str,
                           as_of: datetime) -> dict:
    """Replay sealed PDF/OCR evidence; no network, account, or order access."""
    root = Path(root).resolve()
    manifest_path = root / "source-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    notice_date = manifest.get("cross_notice_url", "").split("/finalpage/")[-1].split("/")[0]
    original, notice = root / "original.pdf", root / "cross-notice.pdf"
    if (manifest.get("schema_version") != "official-halfyear-shares-source-v2"
            or not re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d{10}\.PDF", manifest.get("source_url", ""))
            or not re.fullmatch(r"https://static\.cninfo\.com\.cn/finalpage/\d{4}-\d{2}-\d{2}/\d{10}\.PDF", manifest.get("cross_notice_url", ""))
            or manifest.get("original_sha256") != expected_original_sha256
            or _sha(original) != expected_original_sha256
            or _sha(notice) != manifest.get("cross_notice_sha256")):
        _fail("H1_SOURCE_BINDING_INVALID")
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        _fail("H1_AS_OF_INVALID")
    original_available = _availability(manifest, "original", as_of)
    cross_available = _availability(manifest, "cross_notice", as_of)
    try:
        native, render_hashes, cross = _pdfium_evidence(original, notice)
    except (IndexError, ValueError) as error:
        raise ValueError("H1_PAGES_MISSING") from error
    if symbol not in native[1] or issuer_name not in native[1] or f"{report_year} 年半年度报告" not in native[1]:
        _fail("H1_ISSUER_OR_PERIOD_INVALID")
    ocr = {}
    ocr_hashes = {}
    for page in (22, 23):
        image, artifact = root / f"page-{page}.png", root / f"page-{page}.ocr.json"
        packet = json.loads(artifact.read_text(encoding="utf-8"))
        rows = packet.get("rows")
        if (packet.get("schema_version") != "official-halfyear-shares-ocr-artifact-v2"
                or packet.get("engine") != "rapidocr-3.10.0"
                or packet.get("package_sha256") != SEALED_OCR_PACKAGE_SHA256
                or packet.get("status") != "OCR_REQUIRES_VISUAL_VERIFICATION"
                or packet.get("render_engine") != "pypdfium2"
                or packet.get("render_version") != version("pypdfium2")
                or packet.get("render_scale") != 3
                or packet.get("render_raw_sha256") != render_hashes[page]
                or packet.get("physical_page") != page
                or packet.get("source_url") != manifest["source_url"]
                or packet.get("original_sha256") != expected_original_sha256
                or packet.get("image_sha256") != _sha(image)
                or not isinstance(rows, list) or not rows
                or any(not isinstance(r, dict) or set(r) != {"text", "confidence"}
                       or not isinstance(r["text"], str) or not r["text"]
                       or type(r["confidence"]) not in (int, float)
                       or r["confidence"] < 0.75 or r["confidence"] > 1 for r in rows)
                or any(r["confidence"] < 0.90 for r in rows
                       if (page == 22 and ("三、股份总" in r["text"]
                           or re.fullmatch(r"-?[\d,]+", r["text"])))
                       or (page == 23 and ("完成注销" in r["text"]
                           or re.search(r"回购股份[\d,]+股", r["text"]))))):
            _fail("H1_OCR_BINDING_INVALID")
        ocr[page] = "".join(row["text"] for row in rows).replace(" ", "")
        ocr_hashes[page] = _sha(artifact)
    heading = issuer_name + str(report_year) + "年半年度报告"
    if any(heading not in ocr[p] for p in (22, 23)) or "单位：股" not in ocr[22]:
        _fail("H1_OCR_CONTEXT_INVALID")
    table = re.search(r"三、股份总(.*?)数2、股份变动情况说明", ocr[22])
    if not table:
        _fail("H1_SHARE_TOTAL_ROW_MISSING")
    nums = re.findall(r"-?\d{1,3}(?:,\d{3})+", table.group(1))
    if len(nums) != 4 or nums[1] != nums[2] or not nums[1].startswith("-"):
        _fail("H1_SHARE_TOTAL_ROW_AMBIGUOUS")
    before, cancelled, after = int(nums[0].replace(",", "")), -int(nums[1].replace(",", "")), int(nums[3].replace(",", ""))
    narrative = re.search(r"完成注销.*?股份总数由([\d,]+)股减少至([\d,]+)股", ocr[23])
    if (not narrative or narrative.groups() != (nums[0], nums[3])
            or f"回购股份{cancelled:,}股" not in ocr[23]
            or f"{int(notice_date[:4])}年{int(notice_date[5:7])}月{int(notice_date[8:10])}日披露" not in ocr[23]
            or before - cancelled != after):
        _fail("H1_OCR_RECONCILIATION_FAILED")
    n22, n23 = (re.sub(r"\s+", "", native[p]) for p in (22, 23))
    if (f"三、股份总数{nums[0]}100{nums[1]}{nums[2]}{nums[3]}" not in n22
            or f"完成注销，公司股份总数由{nums[0]}股减少至{nums[3]}股" not in n23
            or f"回购股份{cancelled:,}股" not in n23):
        _fail("H1_NATIVE_NUMERIC_MISMATCH")
    cross_text = re.sub(r"\s+", "", "".join(cross.values()))
    if (symbol not in cross_text or issuer_name not in cross_text
            or f"实际回购股数{cancelled:,}股" not in cross_text
            or all(f"{before:,}" not in p for p in cross.values())
            or all(f"{after:,}" not in p for p in cross.values())):
        _fail("H1_CROSS_NOTICE_MISMATCH")
    return {"schema_version": VERSION, "symbol": symbol, "issuer_name": issuer_name,
            "report_period_end": f"{report_year}-06-30", "ordinary_shares": after,
            "shares_before": before, "cancelled_shares": cancelled,
            "cancellation_evidence": "H1_P23_COMPLETED", "physical_pages": [22, 23],
            "source_url": manifest["source_url"], "original_sha256": expected_original_sha256,
            "original_available_at": original_available.isoformat(),
            "manifest_sha256": _sha(manifest_path), "ocr_artifact_sha256": ocr_hashes,
            "cross_notice_url": manifest["cross_notice_url"],
            "cross_notice_sha256": manifest["cross_notice_sha256"],
            "cross_notice_available_at": cross_available.isoformat(),
            "current_continuity": "UNPROVEN", "formal_eligibility": False,
            "action": "no_order"}
