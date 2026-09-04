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
    return ("sse", f"gssh0{symbol}") if symbol.startswith("6") else ("szse", f"gssz0{symbol}")


def _discover_security_id(symbol: str, column: str, fallback: str) -> str:
    """Resolve CNINFO's issuer-specific internal ID without guessing prefixes."""
    payload = _request_json({
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext", "column": column,
        "stock": "", "searchkey": SYMBOL_NAMES[symbol], "secid": "", "plate": "",
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


def _report_kind(title: str) -> str | None:
    if "半年度报告" in title and "摘要" not in title and "英文" not in title:
        return "interim"
    if "年度报告" in title and "摘要" not in title and "英文" not in title:
        return "annual"
    return None


def _report_period(title: str, report_kind: str) -> str | None:
    match = re.search(r"(20\d{2})年", title)
    if not match:
        return None
    return f"{match.group(1)}-12-31" if report_kind == "annual" else f"{match.group(1)}-06-30"


def search_latest_reports(symbol: str) -> list[dict]:
    """Return one latest full annual and interim report for an A-share code."""
    column, fallback_id = _cninfo_security_id(symbol)
    security_id = _discover_security_id(symbol, column, fallback_id)
    base = {
        "pageNum": "1", "pageSize": "30", "tabName": "fulltext", "column": column,
        "stock": f"{symbol},{security_id}", "searchkey": "", "secid": "", "plate": "",
        "trade": "", "seDate": "", "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    # Searching individual statutory-report categories avoids a frequent issuer's
    # routine notices pushing the actual report beyond the first result page.
    selected: list[dict] = []
    for expected_kind, category in (("annual", "category_ndbg_szsh"), ("interim", "category_bndbg_szsh")):
        payload = _request_json({**base, "category": category})
        for item in payload.get("announcements") or []:
            if _report_kind(str(item.get("announcementTitle", ""))) == expected_kind and item.get("adjunctUrl"):
                selected.append(item)
                break
    return selected


def _download(url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    with urlopen(request, timeout=90) as response, target.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            digest.update(chunk)
            output.write(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def collect_latest_reports(symbols: list[str], evidence_directory: Path) -> list[dict]:
    """Download only latest full annual/interim originals, sequentially."""
    records: list[dict] = []
    for symbol in symbols:
        for announcement in search_latest_reports(symbol):
            title = str(announcement["announcementTitle"])
            kind = _report_kind(title)
            if kind is None:
                continue
            period = _report_period(title, kind)
            if period is None:
                continue
            source_url = PDF_BASE_URL + str(announcement["adjunctUrl"]).lstrip("/")
            target = evidence_directory / symbol / f"{period}-{kind}.pdf"
            sha256 = _sha256_file(target) if target.is_file() else _download(source_url, target)
            timestamp = datetime.fromtimestamp(int(announcement["announcementTime"]) / 1000, tz=timezone.utc)
            records.append({
                "disclosure_id": uuid.uuid4(), "symbol": symbol, "report_period": period,
                "report_kind": kind, "title": title, "source_name": SOURCE_NAME,
                "source_url": source_url, "published_at": timestamp, "sha256": sha256,
                "local_path": str(target), "fetched_at": datetime.now(timezone.utc),
            })
    return records
