"""Fail-closed extraction of a dividend *proposal* from a sealed official PDF.

OCR is used only for PDF fonts whose Chinese text layer is undecodable. The
number-bearing lines are independently checked against the original PDF's
numeric text layer and the share-count arithmetic. A proposal is not payment,
parent cash access, or a forecast payout policy.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from .official_pdf import validate_pdf_original
from .pdf_text import extract_pages

VERSION = "official-dividend-notice-ocr-v1"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ocr_page(path: Path, *, source_sha256: str, page: int) -> tuple[str, str]:
    packet = json.loads(path.read_text(encoding="utf-8"))
    image = path.with_name(f"page-{page}.png")
    if (packet.get("engine") != "rapidocr-3.10.0"
            or packet.get("original_sha256") != source_sha256
            or packet.get("image_sha256") != _digest(image)
            or packet.get("physical_page") != page
            or packet.get("status") != "OCR_REQUIRES_VISUAL_VERIFICATION"):
        raise ValueError("DIVIDEND_OCR_SOURCE_BINDING_INVALID")
    rows = packet.get("rows")
    if not isinstance(rows, list) or not rows or any(
            not isinstance(row, dict) or set(row) != {"text", "confidence"}
            or not isinstance(row["text"], str) or not row["text"]
            or type(row["confidence"]) not in (float, int)
            or not 0.80 <= row["confidence"] <= 1.0 for row in rows):
        raise ValueError("DIVIDEND_OCR_LOW_CONFIDENCE_OR_INVALID")
    if page == 2:
        approval = next((i for i, row in enumerate(rows)
                         if "本次分配方案尚需提交公司股东会审议" in row["text"]), None)
        if approval is None or any(row["confidence"] < 0.90 for row in rows[:approval + 1]):
            raise ValueError("DIVIDEND_PROPOSAL_OCR_LOW_CONFIDENCE")
    return "".join(row["text"] for row in rows).replace(" ", ""), _digest(path)


def replay_proposed_dividend(*, root: Path, receipt_path: Path,
                             symbol: str, issuer_name: str, as_of: datetime) -> dict:
    """Read only a pre-sealed CNINFO notice and return a source-bound proposal."""
    root = root.resolve()
    receipt_path = receipt_path.resolve()
    if not receipt_path.is_relative_to(root):
        raise ValueError("DIVIDEND_RECEIPT_OUTSIDE_ROOT")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    published = receipt.get("published_date", "")
    notice_id = receipt.get("index_announcement_id")
    expected_url = (f"https://static.cninfo.com.cn/finalpage/{published}/{notice_id}.PDF")
    if (receipt.get("schema_version") != "research-source-receipt-v1"
            or receipt.get("action") != "no_order"
            or receipt.get("symbol") != symbol
            or receipt.get("source_host") != "static.cninfo.com.cn"
            or not re.fullmatch(r"\d{10}", str(notice_id))
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published)
            or receipt.get("source_url") != expected_url
            or type(receipt.get("index_announcement_time_ms")) is not int
            or datetime.fromtimestamp(receipt["index_announcement_time_ms"] / 1000,
                                      timezone(timedelta(hours=8))).date().isoformat() != published):
        raise ValueError("DIVIDEND_RECEIPT_IDENTITY_INVALID")
    available_at = datetime.fromisoformat(receipt["fetched_at"])
    if as_of.tzinfo is None or available_at.tzinfo is None or available_at > as_of:
        raise ValueError("DIVIDEND_SOURCE_NOT_AVAILABLE_AS_OF")
    original = (root / receipt["source_path"]).resolve()
    if not original.is_relative_to(root) or original.parent != receipt_path.parent:
        raise ValueError("DIVIDEND_ORIGINAL_OUTSIDE_RECEIPT")
    if _digest(original) != receipt["source_sha256"]:
        raise ValueError("DIVIDEND_ORIGINAL_HASH_CHANGED")
    if original.stat().st_size != receipt.get("source_bytes"):
        raise ValueError("DIVIDEND_ORIGINAL_SIZE_CHANGED")
    validate_pdf_original(original)
    index_records = receipt.get("index_captures")
    if not isinstance(index_records, list) or not index_records:
        raise ValueError("DIVIDEND_INDEX_CAPTURE_MISSING")
    matching_index_rows = []
    for index in index_records:
        path = (root / index["path"]).resolve()
        if not path.is_relative_to(root) or path.parent != receipt_path.parent or _digest(path) != index["sha256"]:
            raise ValueError("DIVIDEND_INDEX_HASH_CHANGED")
        payload = json.loads(path.read_text(encoding="utf-8"))
        matching_index_rows.extend(row for row in payload.get("announcements", [])
            if row.get("secCode") == symbol and row.get("announcementId") == notice_id
            and row.get("adjunctUrl") == f"finalpage/{published}/{notice_id}.PDF"
            and row.get("announcementTime") == receipt["index_announcement_time_ms"])
    if len(matching_index_rows) != 1:
        raise ValueError("DIVIDEND_OFFICIAL_INDEX_ROW_MISSING_OR_AMBIGUOUS")
    pages = extract_pages(original, limit=2)
    if len(pages) < 2 or symbol not in pages[0]:
        raise ValueError("DIVIDEND_PDF_SECURITY_CODE_INVALID")
    first, first_hash = _ocr_page(receipt_path.with_name("page-1.ocr.json"),
                                  source_sha256=receipt["source_sha256"], page=1)
    second, second_hash = _ocr_page(receipt_path.with_name("page-2.ocr.json"),
                                    source_sha256=receipt["source_sha256"], page=2)
    if issuer_name not in first or symbol not in first:
        raise ValueError("DIVIDEND_OCR_ISSUER_INVALID")
    proposal = re.search(r"2025年年度利润分配拟向全体股东每股派发现金红利([0-9.]+)元", second)
    counts = re.search(r"总股本为([0-9,]+)股，回购专用账户内的股份数为([0-9,]+)股，"
                       r"总股本扣除回购专用账户内的股份数为([0-9,]+)股，"
                       r"以此计算合计拟派发现金红利([0-9,.]+)元", second)
    if not proposal or not counts or "本次分配方案尚需提交公司股东会审议" not in second:
        raise ValueError("DIVIDEND_PROPOSAL_CONTEXT_NOT_RECOGNIZED")
    per_share = Decimal(proposal.group(1))
    total_shares, repurchase_shares, entitled_shares = (int(x.replace(",", "")) for x in counts.groups()[:3])
    total_cash = Decimal(counts.group(4).replace(",", ""))
    numeric_text = re.sub(r"\s+", "", "".join(pages))
    if (total_shares - repurchase_shares != entitled_shares
            or (per_share * entitled_shares).quantize(Decimal("0.01")) != total_cash
            or any(value not in numeric_text for value in
                   (proposal.group(1), *counts.groups()))):
        raise ValueError("DIVIDEND_PROPOSAL_NUMERIC_RECONCILIATION_FAILED")
    return dict(schema_version=VERSION, action="no_order", symbol=symbol,
                issuer_name=issuer_name, status="OFFICIAL_PROPOSAL_NOT_PAYMENT_OR_POLICY",
                report_year=2025, published_date=receipt["published_date"],
                available_at=available_at.isoformat(), per_share_cny=str(per_share),
                entitled_shares=entitled_shares, proposed_total_cny=str(total_cash),
                shareholder_approval_status="PENDING_IN_THIS_NOTICE",
                original_sha256=receipt["source_sha256"],
                receipt_sha256=_digest(receipt_path), ocr_page_sha256=[first_hash, second_hash],
                source_url=receipt["source_url"], physical_page=2,
                research_limit="Proposal only; does not prove payment, future payout, parent cash availability, maintenance, WC, or commitments.",
                formal_eligibility=False)
