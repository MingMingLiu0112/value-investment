"""Replay a retained scan of an annual standalone cash-flow statement."""

from decimal import Decimal
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
import re
import unicodedata

from .pdfium_runtime import serialized_pdfium

_AMOUNT = re.compile(r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\.[0-9]{2}")


def _compact(text):
    return "".join(unicodedata.normalize("NFKC", text).split()).replace("−", "-")


def _selected(rows, label, *, minimum=.95):
    hits = [row for row in rows if _compact(row["text"]) == label]
    if len(hits) != 1 or hits[0]["score"] < minimum:
        raise ValueError("PARENT_CFO_SCAN_ROW_MISSING_DUPLICATE_OR_LOW_CONFIDENCE:" + label)
    return hits[0]["bounds"]


def _rows(entries, width, height):
    if not isinstance(entries, list) or not 1 <= len(entries) <= 240:
        raise ValueError("PARENT_CFO_SCAN_ROW_LIMIT")
    for row in entries:
        if (not isinstance(row, dict) or not isinstance(row.get("text"), str)
                or type(row.get("score")) not in (int, float) or not 0 <= row["score"] <= 1
                or not isinstance(row.get("box"), list) or len(row["box"]) != 4
                or any(not isinstance(p, list) or len(p) != 2 or
                       any(type(v) not in (int, float) or not isfinite(v) for v in p)
                       for p in row["box"])):
            raise ValueError("PARENT_CFO_SCAN_INVALID_GEOMETRY")
        xs, ys = zip(*row["box"])
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
        if not (0 <= left < right <= width and 0 <= top < bottom <= height):
            raise ValueError("PARENT_CFO_SCAN_INVALID_GEOMETRY")
        yield {**row, "bounds": (left, top, right, bottom)}


def read_annual_parent_cfo_columns(entries, *, size, issuer_name, period_end):
    """Require labels and amounts in separate, ordered columns on the actual total row."""
    if not re.fullmatch(r"20[0-9]{2}-12-31", period_end):
        raise ValueError("PARENT_CFO_SCAN_ANNUAL_PERIOD_REQUIRED")
    rows = list(_rows(entries, *size))
    issuer = _selected(rows, _compact(issuer_name))
    period = _selected(rows, period_end[:4] + "年12月31日止年度")
    title = _selected(rows, "母公司现金流量表")
    currency = _selected(rows, "单位:人民币元")
    current = _selected(rows, "本年金额")
    previous = _selected(rows, "上年金额")
    total = _selected(rows, "经营活动产生的现金流量净额", minimum=.98)
    investing = _selected(rows, "二、投资活动产生的现金流量")
    if not (issuer[1] < period[1] < title[1] < currency[1] < current[1]
            < total[1] < investing[1] and current[2] < previous[0]
            and max(current[1], previous[1]) < min(current[3], previous[3])
            and total[2] < current[0]):
        raise ValueError("PARENT_CFO_SCAN_STATEMENT_ORDER_INVALID")

    amounts = []
    for column, other in ((current, previous), (previous, current)):
        matches = []
        for row in rows:
            left, top, right, bottom = row["bounds"]
            value = _compact(row["text"])
            if (max(top, total[1]) < min(bottom, total[3])
                    and max(left, column[0]) < min(right, column[2])
                    and max(left, other[0]) >= min(right, other[2])
                    and _AMOUNT.fullmatch(value)):
                matches.append((row["score"], value))
        if len(matches) != 1 or matches[0][0] < .98:
            raise ValueError("PARENT_CFO_SCAN_AMOUNT_MISSING_DUPLICATE_OR_LOW_CONFIDENCE")
        amounts.append(Decimal(matches[0][1].replace(",", "")))
    return tuple(amounts)


@serialized_pdfium
def _verify_scan_pixels(original, physical_page, image):
    import pypdfium2
    from PIL import Image

    with pypdfium2.PdfDocument(original) as doc:
        if type(physical_page) is not int or not 1 <= physical_page <= len(doc):
            raise ValueError("PARENT_CFO_SCAN_PAGE_INVALID")
        page = doc[physical_page - 1]
        try:
            bitmap = page.render(scale=3)
            try:
                rendered = bitmap.to_pil()
                with Image.open(image) as stored:
                    if stored.size != rendered.size or stored.mode != rendered.mode or stored.tobytes() != rendered.tobytes():
                        raise ValueError("PARENT_CFO_SCAN_IMAGE_NOT_ORIGINAL_RENDER")
                return rendered.size
            finally:
                bitmap.close()
        finally:
            page.close()


def replay_annual_parent_cfo_scan(*, original, original_sha256, image, ocr, ocr_sha256,
                                  physical_page, issuer_name, period_end):
    """Replay independently pinned OCR and PDF artifacts, without giving model admission."""
    original, image, ocr = map(Path, (original, image, ocr))
    original_bytes = original.read_bytes()
    ocr_bytes = ocr.read_bytes()
    image_sha256 = sha256(image.read_bytes()).hexdigest()
    if sha256(original_bytes).hexdigest() != original_sha256 or sha256(ocr_bytes).hexdigest() != ocr_sha256:
        raise ValueError("PARENT_CFO_SCAN_EVIDENCE_HASH_CHANGED")
    packet = json.loads(ocr_bytes)
    if (packet["original_sha256"] != original_sha256 or packet["image_sha256"] != image_sha256
            or packet["page"] != physical_page
            or packet["status"] != "OCR_REQUIRES_VISUAL_VERIFICATION"
            or not packet["ocr_engine"].startswith("rapidocr-")
            or not packet["render_engine"].startswith("pypdfium2-")):
        raise ValueError("PARENT_CFO_SCAN_RECEIPT_BINDING_INVALID")
    size = _verify_scan_pixels(original_bytes, physical_page, image)
    if sha256(image.read_bytes()).hexdigest() != image_sha256:
        raise ValueError("PARENT_CFO_SCAN_IMAGE_CHANGED")
    return read_annual_parent_cfo_columns(packet["rows"], size=size,
                                         issuer_name=issuer_name, period_end=period_end)
