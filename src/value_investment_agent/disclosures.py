"""First-party CNINFO filing discovery and archival.

CNINFO is an approved statutory disclosure host. This module stores complete
PDF originals with hashes; it intentionally does not treat PDF text extraction
as a verified financial fact.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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
    # CNINFO's announcement API returns empty results for the UI label "bse".
    # An unrestricted column plus exact stock/org ID supports Beijing issuers.
    return "", f"gssz0{symbol}"


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
    # Broker names frequently match sponsorship notices from other issuers.
    # Annual filings provide a bounded second lookup, still requiring exact code.
    payload = _request_json({
        'pageNum': '1', 'pageSize': '30', 'tabName': 'fulltext', 'column': '',
        'stock': '', 'searchkey': issuer_name, 'secid': '', 'plate': '',
        'category': 'category_ndbg_szsh', 'trade': '', 'seDate': '',
        'sortName': '', 'sortType': '', 'isHLtitle': 'false',
    })
    for item in payload.get('announcements') or []:
        if str(item.get('secCode', '')) == symbol and item.get('orgId'):
            return str(item['orgId'])
    # Market display names may contain XD/XR prefixes or CDR suffixes absent
    # from the official issuer name. Resolve by exact code before guessing IDs.
    payload = _request_json({
        'pageNum': '1', 'pageSize': '30', 'tabName': 'fulltext', 'column': '',
        'stock': '', 'searchkey': symbol, 'secid': '', 'plate': '',
        'category': '', 'trade': '', 'seDate': '', 'sortName': '',
        'sortType': '', 'isHLtitle': 'false',
    })
    ids = {str(item['orgId']) for item in payload.get('announcements') or []
           if str(item.get('secCode', '')) == symbol and item.get('orgId')}
    if len(ids) == 1:
        return ids.pop()
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
    "third_quarter": "category_sjdbg_szsh",
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
    # An exchange distribution prefix can label a genuine attached report.
    title = re.sub(r'^(?:[^《》]*?H\s*股公告|境内同步披露公告)\s*[-:：－]\s*', '', title, count=1, flags=re.I)
    if any(word in title for word in ('公告', '披露日期', '披露时间', '预约披露', '取消披露')):
        return None
    if "摘要" in title or "英文" in title:
        return None
    if "第一季度报告" in title:
        return "first_quarter"
    if "第三季度报告" in title:
        return "third_quarter"
    if "半年度报告" in title:
        return "interim"
    if "年度报告" in title or re.search(r'年报(?:[（(].*[）)])?$', title):
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


def _annual_period_from_cover(text: str, symbol: str) -> str | None:
    code = re.search(r'(?:公司|证券|股票)代码\s*[:：]\s*([^\r\n]+)', text)
    if not code or symbol not in re.findall(r'(?<!\d)\d{6}(?!\d)', code[1]):
        return None
    if '摘要' in text or '英文版' in text:
        return None
    years = set(re.findall(r'(20\d{2})\s*年\s*年度报告', text))
    return next(iter(years)) + '-12-31' if len(years) == 1 else None


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
        # First- and third-quarter reports have distinct CNINFO categories.
        if category in queried_categories:
            continue
        queried_categories.add(category)
        payload = _request_json({**base, "category": category})
        selected_kinds = {
            _report_kind(str(item.get("announcementTitle", "")))
            for item in selected
        }
        announcements = payload.get("announcements") or []
        if category == REPORT_CATEGORIES['annual']:
            summary_periods = [_report_period(str(item.get('announcementTitle', '')), 'annual') or ''
                               for item in announcements
                               if '摘要' in str(item.get('announcementTitle', ''))
                               and '半年度' not in str(item.get('announcementTitle', ''))]
            full_periods = [_report_period(str(item.get('announcementTitle', '')), 'annual') or ''
                            for item in announcements
                            if _report_kind(str(item.get('announcementTitle', ''))) == 'annual']
            if max(summary_periods, default='') > max(full_periods, default=''):
                fallback = _request_json({**base, 'category': '', 'searchkey': '年度报告',
                                          'isHLtitle': 'false'})
                # Broader search includes opinions and supervisory reports.
                # Require the issuer code and a full-report title ending.
                known_urls = {item.get('adjunctUrl') for item in announcements}
                for item in fallback.get('announcements') or []:
                    title = str(item.get('announcementTitle', ''))
                    if (str(item.get('secCode', '')) == symbol
                        and item.get('adjunctUrl') and item['adjunctUrl'] not in known_urls
                        and re.search(r'20\d{2}\s*年(?:年度|度)报告(?:全文)?'
                                      r'(?:[（(](?:修订版|修订稿|更新版|更正版|印刷版)[）)])?$', title)):
                        announcements.append(item)
                        known_urls.add(item['adjunctUrl'])
        # Prefer the mainland full report, then the newest reporting period and
        # publication. A later H-share notice must not displace the A-share PDF.
        def report_rank(item):
            title = str(item.get('announcementTitle',''))
            kind = _report_kind(title)
            period = _report_period(title,kind) if kind else ''
            return (period or '',not bool(re.search(r'H\s*股|港股|境外',title,re.I)),int(item.get('announcementTime',0)))
        for item in sorted(announcements,key=report_rank,reverse=True):
            actual_kind = _report_kind(str(item.get("announcementTitle", "")))
            if actual_kind in REPORT_CATEGORIES and actual_kind not in selected_kinds and item.get("adjunctUrl"):
                selected.append(item)
                selected_kinds.add(actual_kind)
        # A newer abbreviated title has no sortable fiscal period until its
        # PDF cover is read. Retain one alongside the dated fallback.
        undated = [item for item in announcements
                   if item.get('secCode') == symbol and item.get('adjunctUrl')
                   and _report_kind(str(item.get('announcementTitle', ''))) == 'annual'
                   and _report_period(str(item.get('announcementTitle', '')), 'annual') is None]
        if undated:
            newest = max(undated, key=lambda item: int(item.get('announcementTime', 0)))
            dated_times = [int(item.get('announcementTime', 0)) for item in selected
                           if _report_kind(str(item.get('announcementTitle', ''))) == 'annual'
                           and _report_period(str(item.get('announcementTitle', '')), 'annual')]
            if newest not in selected and (not dated_times or
                    int(newest.get('announcementTime', 0)) > max(dated_times)):
                selected.append(newest)
    return selected


def _download(url: str, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    minimum_free = 2 * 1024**3
    if shutil.disk_usage(target.parent).free < minimum_free:
        raise OSError('Low disk: preserve 2 GiB for database; postpone new PDF download')
    request = Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    temporary = target.with_suffix(f"{target.suffix}.part")
    try:
        with urlopen(request, timeout=90) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                if shutil.disk_usage(target.parent).free - len(chunk) < minimum_free:
                    raise OSError('Low disk during PDF download; preserve database reserve')
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
            if period is None and kind != 'annual':
                continue
            source_url = PDF_BASE_URL + str(announcement["adjunctUrl"]).lstrip("/")
            # URL-specific archives never bind an old PDF to a revised notice.
            source_key = hashlib.sha256(source_url.encode('utf-8')).hexdigest()
            target = evidence_directory / symbol / f"{period or 'undated'}-{kind}-{source_key}.pdf"
            # A prior interrupted transfer must never be trusted as evidence.
            sha256 = _sha256_file(target) if _is_complete_pdf(target) else _download(source_url, target)
            if period is None:
                from .pdf_text import extract_pages
                cover = extract_pages(target, limit=1)
                period = _annual_period_from_cover(cover[0] if cover else '', symbol)
                if period is None:
                    raise ValueError(f'Cannot bind annual PDF cover to issuer and period: {symbol} {source_url}')
            timestamp = datetime.fromtimestamp(int(announcement["announcementTime"]) / 1000, tz=timezone.utc)
            records.append({
                "disclosure_id": uuid.uuid4(), "symbol": symbol, "report_period": period,
                "report_kind": kind, "title": title, "source_name": SOURCE_NAME,
                "source_url": source_url, "published_at": timestamp, "sha256": sha256,
                "local_path": str(target), "fetched_at": datetime.now(timezone.utc),
                "report_assurance": REPORT_ASSURANCE[kind],
            })
    return records
