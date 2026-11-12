"""Cold replay of CNINFO dividend implementation from four unmodified captures.

The public date is reconstructed conservatively; strict replay availability
also includes the actual index and PDF capture times. No personal receipt or
future distribution follows from an issuer implementation notice.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from pathlib import Path
import re

from .disclosure_availability import indexed_disclosure_availability
from .official_pdf import validate_pdf_original
from .pdf_text import extract_pages

VERSION = "official-dividend-split-receipt-v2"
SEARCH_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
COLLECTOR = "value_investment_agent.disclosures.download_disclosure_pdf"


def _read(root: Path, path: Path) -> tuple[Path, bytes]:
    path = Path(path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("SPLIT_SOURCE_OUTSIDE_OR_MISSING")
    return path, path.read_bytes()


def _json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("SPLIT_RECEIPT_JSON_INVALID") from error
    if not isinstance(value, dict):
        raise ValueError("SPLIT_RECEIPT_JSON_INVALID")
    return value


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("SPLIT_CAPTURE_TIME_INVALID") from error
    if parsed.tzinfo is None:
        raise ValueError("SPLIT_CAPTURE_TIME_INVALID")
    return parsed


def _date(value: str):
    return datetime.strptime(value, "%Y/%m/%d").date()


def replay_split_dividend_implementation(*, root: Path, index_response_path: Path,
        index_receipt_path: Path, pdf_path: Path, pdf_receipt_path: Path,
        symbol: str, issuer_name: str, as_of: datetime) -> dict:
    root = Path(root).resolve()
    paths_and_bytes = [_read(root, path) for path in (
        index_response_path, index_receipt_path, pdf_path, pdf_receipt_path)]
    (index_path, index_raw), (ir_path, ir_raw), (original, pdf_raw), (pr_path, pr_raw) = paths_and_bytes
    if len({path.parent for path, _ in paths_and_bytes}) != 1:
        raise ValueError("SPLIT_CAPTURE_DIRECTORY_MISMATCH")
    index, index_receipt, pdf_receipt = map(_json, (index_raw, ir_raw, pr_raw))
    meta, recorded = index_receipt.get("metadata"), index_receipt.get("announcement")
    if not isinstance(meta, dict) or not isinstance(recorded, dict):
        raise ValueError("SPLIT_INDEX_RECEIPT_INVALID")
    request = meta.get("request")
    if (meta.get("url") != SEARCH_URL or meta.get("method") != "POST"
            or meta.get("body_representation") != "RECEIVED_RESPONSE_CONTENT_NOT_RESERIALIZED_JSON"
            or meta.get("sha256") != sha256(index_raw).hexdigest()
            or meta.get("size_bytes") != len(index_raw)
            or not isinstance(request, dict) or request.get("stock") != f"{symbol},gssh0{symbol}"
            or request.get("column") != "sse" or request.get("pageNum") != "1"
            or request.get("searchkey") != "" or request.get("category") != ""
            or request.get("seDate", "").count("~") != 1):
        raise ValueError("SPLIT_INDEX_HASH_OR_REQUEST_INVALID")
    index_time = _time(meta.get("acquired_at"))
    rows = [row for row in index.get("announcements", [])
            if str(row.get("announcementId")) == str(recorded.get("announcementId"))]
    if len(rows) != 1 or rows[0] != recorded or recorded.get("secCode") != symbol \
            or recorded.get("orgId") != f"gssh0{symbol}":
        raise ValueError("SPLIT_INDEX_IDENTITY_INVALID")
    notice_id = str(recorded["announcementId"])
    if not re.fullmatch(r"\d{10}", notice_id):
        raise ValueError("SPLIT_INDEX_IDENTITY_INVALID")
    url = f"https://static.cninfo.com.cn/{recorded.get('adjunctUrl', '').lstrip('/')}"
    if (pdf_receipt.get("method") != "GET" or pdf_receipt.get("url") != url
            or pdf_receipt.get("collector") != COLLECTOR
            or pdf_receipt.get("sha256") != sha256(pdf_raw).hexdigest()
            or pdf_receipt.get("size_bytes") != len(pdf_raw)):
        raise ValueError("SPLIT_PDF_HASH_OR_RECEIPT_INVALID")
    pdf_time = _time(pdf_receipt.get("acquired_at"))
    try:
        available = indexed_disclosure_availability(
            {"url": SEARCH_URL, "announcements": rows}, symbol=symbol,
            source_id=f"cninfo:{notice_id}", source_url=url)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("SPLIT_INDEX_AVAILABILITY_INVALID") from error
    if (request["seDate"] != f"{available['disclosure_date']}~{available['disclosure_date']}"
            or index_receipt.get("availability") != available
            or index_time > pdf_time):
        raise ValueError("SPLIT_AVAILABILITY_OR_CAPTURE_ORDER_INVALID")
    strict_available = max(_time(available["available_from"]), index_time, pdf_time)
    if as_of.tzinfo is None or as_of < strict_available:
        raise ValueError("SPLIT_NOT_AVAILABLE_AS_OF")
    validate_pdf_original(original)
    pages = extract_pages(original, limit=3)
    if len(pages) < 2:
        raise ValueError("SPLIT_PDF_PAGES_MISSING")
    first, second = (re.sub(r"\s+", "", page) for page in pages[:2])
    if issuer_name not in first or f"证券代码：{symbol}" not in first \
            or "股东大会审议通过" not in first or "分派对象" not in first \
            or "登记在册" not in second:
        raise ValueError("SPLIT_PDF_ISSUER_OR_APPROVAL_INVALID")
    title = re.search(r"(20\d{2})年(中期|年度)权益分派实施公告", first)
    period = re.search(r"发放年度：(20\d{2})年(中期|年度)", first)
    if not title or not period or title.groups() != period.groups():
        raise ValueError("SPLIT_REPORT_PERIOD_INVALID")
    report_year, kind = title.groups()
    if (report_year, kind) not in {("2024", "中期"), ("2024", "年度"), ("2025", "中期")}:
        raise ValueError("SPLIT_REPORT_PERIOD_UNSUPPORTED")
    headline = re.search(r"A股每股现金红利([\d.]+)元", first)
    if kind == "中期":
        match = re.search(r"方案实施前的公司总股本([\d,]+)股为基数，"
            r"每股派发现金红利([\d.]+)元（含税），共计派发现金红利([\d,]+\.\d+)元", second)
    else:
        match = re.search(r"截至本公告日.*?总股本扣除回购专用证券账户内的股份数为([\d,]+)股"
            r".*?每股派发现金红利([\d.]+)元（含税），共计派发现金红利([\d,]+\.\d+)元", second)
    if not headline or not match:
        raise ValueError("SPLIT_IMPLEMENTED_TERMS_MISSING")
    shares = int(match.group(1).replace(",", ""))
    per_share, total = Decimal(match.group(2)), Decimal(match.group(3).replace(",", ""))
    if (per_share != Decimal(headline.group(1)) or not 0 < shares < 100_000_000_000
            or (per_share * shares).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != total):
        raise ValueError("SPLIT_IMPLEMENTED_AMOUNT_INVALID")
    dates = re.findall(r"Ａ股(\d{4}/\d{1,2}/\d{1,2})[－—-]"
                       r"(\d{4}/\d{1,2}/\d{1,2})(\d{4}/\d{1,2}/\d{1,2})", first)
    if len(dates) != 1:
        raise ValueError("SPLIT_PAYMENT_DATES_MISSING")
    record_date, ex_date, payment_date = map(_date, dates[0])
    if not record_date < ex_date or payment_date < ex_date:
        raise ValueError("SPLIT_PAYMENT_DATE_ORDER_INVALID")
    return {"schema_version": VERSION, "action": "no_order", "symbol": symbol,
        "status": "HISTORICAL_IMPLEMENTATION_SCHEDULE_NOT_PERSONAL_RECEIPT",
        "report_period": f"FY{report_year}_" + ("interim" if kind == "中期" else "final"),
        "published_date": available["disclosure_date"],
        "conservative_public_available_at": available["available_from"],
        "available_at": strict_available.isoformat(), "historical_capture_proven": False,
        "record_date": record_date.isoformat(), "ex_date": ex_date.isoformat(),
        "scheduled_payment_date": payment_date.isoformat(), "implemented_shares": shares,
        "per_share_cny": str(per_share), "implemented_total_cny": str(total),
        "source_url": url, "announcement_id": notice_id,
        "pdf_sha256": sha256(pdf_raw).hexdigest(), "index_response_sha256": sha256(index_raw).hexdigest(),
        "index_receipt_sha256": sha256(ir_raw).hexdigest(), "pdf_receipt_sha256": sha256(pr_raw).hexdigest(),
        "physical_pages": [1, 2], "formal_eligibility": False}
