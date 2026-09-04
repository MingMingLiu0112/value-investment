"""First-party CNINFO filing discovery and archival.

CNINFO is an approved statutory disclosure host. This module stores complete
PDF originals with hashes; it intentionally does not treat PDF text extraction
as a verified financial fact.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .universe import UNIVERSE


SEARCH_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE_URL = "https://static.cninfo.com.cn/"
SOURCE_NAME = "CNINFO statutory disclosure"
USER_AGENT = "Mozilla/5.0 ValueInvestmentAgent/1.0"
SYMBOL_NAMES = {symbol: name for symbol, name, *_ in UNIVERSE}


def _cninfo_security_id(symbol: str) -> tuple[str, str]:
    if symbol.startswith("6"):
        return "sse", f"gssh0{symbol}"
    if symbol.startswith(("0", "3")):
        return "szse", f"gssz0{symbol}"
    # Beijing Exchange issuers are resolved by company name before this
    # fallback is used. CNINFO's organization IDs are not derivable from code.
    return "bse", f"gssz0{symbol}"


def _discover_security_id(symbol: str, column: str, fallback: str, issuer_name: str | None = None) -> str:
    """Resolve CNINFO's issuer-specific internal ID without guessing prefixes."""
    if not issuer_name:
        return fallback
    payload = _request_json({
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext", "column": column,
        "stock": "", "searchkey": issuer_name, "secid": "", "plate": "",
        "category": "", "trade": "", "seDate": "", "sortName": "", "sortType": "",
        "isHLtitle": "true",
    })
    for item in payload.get("announcements") or []:
        if str(item.get("secCode", "")) == symbol and item.get("orgId"):
            return str(item["orgId"])
    return fallback


def _request_json(data: dict[str, str]) -> dict:
    request = Request(
        SEARCH_URL,
        data=urlencode(data).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


REPORT_CATEGORIES = {
    "annual": "category_ndbg_szsh",
    "interim": "category_bndbg_szsh",
    "first_quarter": "category_yjdbg_szsh",
    "third_quarter": "category_yjdbg_szsh",
}

# A statutory filing is primary evidence, but only annual reports are required
# to be audited. The label never overstates a report's assurance level.
REPORT_ASSURANCE = {
    "annual": "statutory_annual_report_audit_required",
    "interim": "statutory_interim_report_unaudited_or_reviewed",
    "first_quarter": "statutory_quarterly_report_unaudited",
    "third_quarter": "statutory_quarterly_report_unaudited",
}


def _report_kind(title: str) -> str | None:
    if "摘要" in title or "英文" in title:
        return None
    if "第一季度报告" in title:
        return "first_quarter"
    if "第三季度报告" in title:
        return "third_quarter"
    if "半年度报告" in title:
        return "interim"
    if "年度报告" in title:
        return "annual"
    return None


def _report_period(title: str, report_kind: str) -> str | None:
    match = re.search(r"(20\d{2})年", title)
    if not match:
        return None
    month_day = {
        "annual": "12-31",
        "interim": "06-30",
        "first_quarter": "03-31",
        "third_quarter": "09-30",
    }[report_kind]
    return f"{match.group(1)}-{month_day}"


def search_latest_reports(symbol: str, issuer_name: str | None = None) -> list[dict]:
    """Return the latest full report of each statutory reporting type."""
    column, fallback_id = _cninfo_security_id(symbol)
    security_id = _discover_security_id(symbol, column, fallback_id, issuer_name or SYMBOL_NAMES.get(symbol))
    base = {
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext", "column": column,
        "stock": f"{symbol},{security_id}", "searchkey": "", "secid": "", "plate": "",
        "trade": "", "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    # Searching individual statutory-report categories avoids a frequent issuer's
    # routine notices pushing the actual report beyond the first result page.
    selected: list[dict] = []
    queried_categories: set[str] = set()
    for category in dict.fromkeys(REPORT_CATEGORIES.values()):
        # First- and third-quarter reports share CNINFO's quarterly category.
        # Query it once, then select the newest report for each quarter.
        if category in queried_categories:
            continue
        queried_categories.add(category)
        payload = _request_json({**base, "category": category})
        selected_kinds = {
            _report_kind(str(item.get("announcementTitle", "")))
            for item in selected
        }
        for item in payload.get("announcements") or []:
            actual_kind = _report_kind(str(item.get("announcementTitle", "")))
            if actual_kind in REPORT_CATEGORIES and actual_kind not in selected_kinds and item.get("adjunctUrl"):
                selected.append(item)
                selected_kinds.add(actual_kind)
    return selected


def _download(url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    temporary = target.with_suffix(f"{target.suffix}.part")
    try:
        with urlopen(request, timeout=90) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        temporary.replace(target)
        return digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_complete_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size <= 4:
        return False
    with path.open("rb") as handle:
        return handle.read(4) == b"%PDF"


def collect_latest_reports(
    symbols: list[str], evidence_directory: Path, issuer_names: dict[str, str] | None = None,
) -> list[dict]:
    """Download the latest statutory report originals, sequentially."""
    records: list[dict] = []
    for symbol in symbols:
        for announcement in search_latest_reports(symbol, (issuer_names or {}).get(symbol)):
            title = str(announcement["announcementTitle"])
            kind = _report_kind(title)
            if kind is None:
                continue
            period = _report_period(title, kind)
            if period is None:
                continue
            source_url = PDF_BASE_URL + str(announcement["adjunctUrl"]).lstrip("/")
            target = evidence_directory / symbol / f"{period}-{kind}.pdf"
            # A prior interrupted transfer must never be trusted as evidence.
            sha256 = _sha256_file(target) if _is_complete_pdf(target) else _download(source_url, target)
            timestamp = datetime.fromtimestamp(int(announcement["announcementTime"]) / 1000, tz=timezone.utc)
            records.append({
                "disclosure_id": uuid.uuid4(), "symbol": symbol, "report_period": period,
                "report_kind": kind, "title": title, "source_name": SOURCE_NAME,
                "source_url": source_url, "published_at": timestamp, "sha256": sha256,
                "local_path": str(target), "fetched_at": datetime.now(timezone.utc),
                "report_assurance": REPORT_ASSURANCE[kind],
            })
    return records
