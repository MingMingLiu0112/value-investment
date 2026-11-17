"""Cold replay of an issuer's approved distribution implementation notice.

The filing proves an approved per-share distribution and scheduled payment. It
does not prove a shareholder's receipt or any future dividend policy.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from .official_pdf import validate_pdf_original
from .pdf_text import extract_pages

VERSION = "official-dividend-implementation-v1"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_implemented_distribution(*, root: Path, receipt_path: Path,
                                    symbol: str, issuer_name: str,
                                    as_of: datetime) -> dict:
    root, receipt_path = Path(root).resolve(), Path(receipt_path).resolve()
    if not receipt_path.is_relative_to(root):
        raise ValueError("DISTRIBUTION_RECEIPT_OUTSIDE_ROOT")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    published, notice_id = receipt.get("published_date"), receipt.get("index_announcement_id")
    if (receipt.get("schema_version") != "research-source-receipt-v1"
            or receipt.get("action") != "no_order" or receipt.get("symbol") != symbol
            or receipt.get("source_host") != "static.cninfo.com.cn"
            or not isinstance(published, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", published)
            or not isinstance(notice_id, str) or not re.fullmatch(r"\d{10}", notice_id)
            or receipt.get("source_url") != f"https://static.cninfo.com.cn/finalpage/{published}/{notice_id}.PDF"
            or type(receipt.get("index_announcement_time_ms")) is not int
            or datetime.fromtimestamp(receipt["index_announcement_time_ms"] / 1000,
                timezone(timedelta(hours=8))).date().isoformat() != published):
        raise ValueError("DISTRIBUTION_RECEIPT_IDENTITY_INVALID")
    available = datetime.fromisoformat(receipt["fetched_at"])
    if as_of.tzinfo is None or available.tzinfo is None or available > as_of:
        raise ValueError("DISTRIBUTION_NOT_AVAILABLE_AS_OF")
    original = (root / receipt["source_path"]).resolve()
    if (not original.is_relative_to(root) or original.parent != receipt_path.parent
            or _hash(original) != receipt.get("source_sha256")
            or original.stat().st_size != receipt.get("source_bytes")):
        raise ValueError("DISTRIBUTION_ORIGINAL_CHANGED")
    validate_pdf_original(original)
    indexes = receipt.get("index_captures")
    if not isinstance(indexes, list) or not indexes:
        raise ValueError("DISTRIBUTION_INDEX_MISSING")
    matches = []
    for pin in indexes:
        path = (root / pin["path"]).resolve()
        if (not path.is_relative_to(root) or path.parent != receipt_path.parent
                or _hash(path) != pin.get("sha256")):
            raise ValueError("DISTRIBUTION_INDEX_CHANGED")
        rows = json.loads(path.read_text(encoding="utf-8")).get("announcements", [])
        matches.extend(row for row in rows
            if row.get("secCode") == symbol and row.get("announcementId") == notice_id
            and row.get("adjunctUrl") == f"finalpage/{published}/{notice_id}.PDF"
            and row.get("announcementTime") == receipt["index_announcement_time_ms"])
    if len(matches) != 1:
        raise ValueError("DISTRIBUTION_OFFICIAL_INDEX_ROW_MISSING_OR_AMBIGUOUS")
    pages = extract_pages(original, limit=2)
    if len(pages) < 2:
        raise ValueError("DISTRIBUTION_PAGES_MISSING")
    first, second = (re.sub(r"\s+", "", page) for page in pages)
    if (issuer_name not in first or f"证券代码：{symbol}" not in first
            or "2025年年度权益分派实施公告" not in first
            or "股东会审议通过" not in first
            or "分派对象" not in second or "分配实施办法" not in second):
        raise ValueError("DISTRIBUTION_ISSUER_OR_APPROVAL_CONTEXT_INVALID")
    headline = re.search(r"A股每股现金红利([0-9]+\.[0-9]+)元", first)
    distribution = re.search(
        r"(?:扣除回购专用账户内的股份)([0-9,]+)股为基数，"
        r"每股派发现金红利([0-9]+\.[0-9]+)元（含税），"
        r"共计派发现金红利([0-9,]+\.[0-9]+)元", second)
    dates = re.findall(r"Ａ股(\d{4}/\d{1,2}/\d{1,2})[－—-]"
                       r"(\d{4}/\d{1,2}/\d{1,2})(\d{4}/\d{1,2}/\d{1,2})", second)
    if not headline or not distribution or len(dates) != 1:
        raise ValueError("DISTRIBUTION_TERMS_OR_DATES_MISSING")
    shares = int(distribution.group(1).replace(",", ""))
    per_share = Decimal(distribution.group(2))
    total = Decimal(distribution.group(3).replace(",", ""))
    if (per_share != Decimal(headline.group(1))
            or (per_share * shares).quantize(Decimal("0.01")) != total
            or not 0 < shares < 100_000_000_000):
        raise ValueError("DISTRIBUTION_ARITHMETIC_OR_HEADLINE_CONFLICT")
    record, ex_date, scheduled_payment = (
        datetime.strptime(value, "%Y/%m/%d").date() for value in dates[0])
    if not record < ex_date or scheduled_payment < ex_date:
        raise ValueError("DISTRIBUTION_DATE_ORDER_INVALID")
    return dict(schema_version=VERSION, action="no_order", symbol=symbol,
        issuer_name=issuer_name, status="APPROVED_IMPLEMENTATION_SCHEDULE_NOT_PERSONAL_RECEIPT",
        report_year=2025, published_date=published, available_at=available.isoformat(),
        shareholder_approval_status="APPROVED_IN_THIS_NOTICE", per_share_cny=str(per_share),
        entitled_shares=shares, scheduled_total_cny=str(total),
        record_date=record.isoformat(), ex_date=ex_date.isoformat(),
        scheduled_payment_date=scheduled_payment.isoformat(),
        source_url=receipt["source_url"], original_sha256=receipt["source_sha256"],
        receipt_sha256=_hash(receipt_path), physical_pages=[1, 2],
        research_limit="Approved historical implementation schedule; not personal receipt or future cash policy.",
        formal_eligibility=False)
