"""Discover exact FY/H1 originals using the existing CNINFO/PDF adapters.

Acquisition is not financial admission or a reconstruction of historical PIT.
"""
from datetime import date, datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import time

import requests

from ... import disclosures
from .official_pdf import download_official_pdf, validate_pdf_original
from .pdf_text import extract_pages


VERSION = "official-report-acquisition-v1"
CHINA = timezone(timedelta(hours=8))
# Company-information tables can follow several pages of contents (e.g. p9).
IDENTITY_PAGE_LIMIT = 12
RETRY_WAIT_BUDGET_SECONDS = 5.0


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, payload):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=True, indent=2, allow_nan=False)


def _retry_plan(error, *, attempt, remaining, captured=False):
    """Retry-After is a lower bound; never shorten it to fit the wait budget."""
    now = datetime.now(timezone.utc)
    response = error.response if isinstance(error, requests.HTTPError) else None
    status = response.status_code if response is not None else None
    retryable = isinstance(error, (requests.Timeout, requests.ConnectionError)) or (
        status is not None and (status == 429 or 500 <= status <= 599))
    result = dict(http_status=status, retry_after=None, retry_after_seconds=None,
                  reopen_at=None, wait_seconds=0.0, retry_status="NOT_RETRYABLE")
    if not retryable:
        return result
    raw = response.headers.get("Retry-After") if response is not None else None
    delay = 1.0
    if raw is not None:
        # Do not persist unbounded or control-character-bearing server input.
        if (not isinstance(raw, str) or len(raw) > 128
                or any(ord(char) < 32 or ord(char) > 126 for char in raw)):
            result["retry_status"] = "INVALID_RETRY_AFTER"
            return result
        result["retry_after"] = raw
        try:
            if re.fullmatch(r"[0-9]{1,10}", raw):
                delay = float(int(raw))
            else:
                stamp = parsedate_to_datetime(raw)
                if stamp.utcoffset() != timedelta(0) or format_datetime(stamp, usegmt=True) != raw:
                    raise ValueError("Noncanonical HTTP date")
                delay = max(0.0, (stamp - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            result["retry_status"] = "INVALID_RETRY_AFTER"
            return result
    result.update(retry_after_seconds=delay, reopen_at=(now + timedelta(seconds=delay)).isoformat())
    if captured:
        result["retry_status"] = "RAW_RESPONSE_ALREADY_CAPTURED"
    elif attempt >= 2:
        result["retry_status"] = "ATTEMPTS_EXHAUSTED"
    elif delay > remaining:
        result["retry_status"] = "WAIT_BUDGET_EXCEEDED"
    else:
        result.update(retry_status="RETRY_SCHEDULED", wait_seconds=delay)
    return result


def _discover(query, *, symbol, issuer_name, period, kind, today):
    column, fallback = disclosures._cninfo_security_id(symbol)
    org = disclosures._discover_security_id(symbol, column, fallback,
                                            issuer_name, request_json=query)
    base = dict(pageNum="1", pageSize="30", tabName="fulltext", column=column,
                stock=f"{symbol},{org}", searchkey="", secid="", plate="",
                category=disclosures.REPORT_CATEGORIES[kind], trade="",
                seDate=f"{(date.fromisoformat(period) + timedelta(days=1)).isoformat()}~{today.isoformat()}",
                sortName="", sortType="", isHLtitle="false")
    rows, total = [], None
    for page in range(1, 5):
        payload = query(dict(base, pageNum=str(page)))
        count = payload.get("totalAnnouncement")
        if type(count) is not int or not 0 <= count <= 120 or (total is not None and count != total):
            raise ValueError("Official report pagination total invalid or changed")
        total = count
        items = payload.get("announcements") or []
        if not isinstance(items, list) or (not items and len(rows) < total):
            raise ValueError("Official report pagination incomplete")
        rows.extend(items)
        if len({str(row.get('announcementId')) for row in rows}) != len(rows) or len(rows) > total:
            raise ValueError("Official report pagination duplicate or overflow")
        if len(rows) == total:
            break
    if len(rows) != total:
        raise ValueError("Official report pagination budget exhausted")
    return _select(rows, symbol=symbol, period=period, kind=kind, today=today)


def _select(rows, *, symbol, period, kind, today):
    candidates = []
    for row in rows:
        if row.get("secCode") != symbol:
            raise ValueError("Official index issuer mismatch")
        title = re.sub(r"<[^>]*>", "", str(row.get("announcementTitle", "")))
        if (disclosures._report_kind(title) != kind
                or disclosures._report_period(title, kind) != period):
            continue
        notice = str(row.get("announcementId", ""))
        path = row.get("adjunctUrl", "")
        match = re.fullmatch(r"finalpage/(20\d{2}-\d{2}-\d{2})/([0-9]+)\.PDF", path)
        epoch = row.get("announcementTime")
        if not match or match[2] != notice or type(epoch) is not int or epoch <= 0:
            raise ValueError("Official report index identity invalid")
        published = datetime.fromtimestamp(epoch / 1000, CHINA).date()
        if published.isoformat() != match[1] or not date.fromisoformat(period) < published <= today:
            raise ValueError("Official report publication date invalid")
        candidates.append((row, published))
    if len(candidates) != 1:
        raise ValueError("Official full report missing or ambiguous; review corrections")
    return candidates[0]


def _verify_cover(pages, *, symbol, issuer_name, period, kind):
    text = "\n".join(pages)
    codes = set()
    for labelled in re.findall(r"(?:公司|证券|股票)代码\s*[:：]?\s*([0-9]{6})(?!\d)", text):
        codes.add(labelled)
    compact = re.sub(r"\s+", "", text)
    report = "年度报告" if kind == "annual" else "半年度报告"
    if (codes != {symbol} or re.sub(r"\s+", "", issuer_name) not in compact
            or period[:4] + "年" + report not in compact
            or any(word in compact for word in ("报告摘要", "英文版"))):
        raise ValueError("Official PDF issuer or reporting-period cover mismatch")


def acquire_official_report(*, root: Path, symbol: str, issuer_name: str,
                            period: str, output_dir: Path,
                            allow_network: bool = False) -> dict:
    """No URL/descriptor input required. Return a retained-source descriptor.

    One exact period per call, at most 4 category pages plus issuer resolution.
    Missing/ambiguous originals fail closed; all acquired bytes stay in runtime.
    """
    if allow_network is not True:
        raise ValueError("Official acquisition requires explicit network permission")
    if (not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}", symbol)
            or not isinstance(issuer_name, str) or not issuer_name.strip()):
        raise ValueError("Official acquisition requires exact issuer identity")
    day = date.fromisoformat(period)
    if day.isoformat() != period or period[4:] not in ("-12-31", "-06-30"):
        raise ValueError("Only exact annual or semiannual report periods are supported")
    started = datetime.now(timezone.utc)
    today = started.astimezone(CHINA).date()
    if day >= today:
        raise ValueError("Reporting period has not completed")
    kind = "annual" if day.month == 12 else "interim"
    root = root.resolve()
    output = (root / output_dir).resolve()
    if not output.is_relative_to(root / "runtime"):
        raise ValueError("Official acquisition output must be inside project runtime")
    if output.exists():
        raise FileExistsError("Official acquisition needs a fresh archive directory")
    output.mkdir(parents=True)
    bindings = []
    attempts = []
    remaining_wait = RETRY_WAIT_BUDGET_SECONDS

    def retry(error, *, kind, attempt, captured=False):
        nonlocal remaining_wait
        plan = _retry_plan(error, attempt=attempt, remaining=remaining_wait, captured=captured)
        attempts.append(dict(kind=kind, attempt=attempt, status="FAILED",
                             error_type=type(error).__name__, **plan))
        if plan["retry_status"] != "RETRY_SCHEDULED":
            return False
        remaining_wait -= plan["wait_seconds"]
        time.sleep(plan["wait_seconds"])
        return True

    def query(parameters):
        captured = []

        def capture(body, metadata):
            if (not isinstance(body, bytes) or not body
                    or metadata.get("sha256") != hashlib.sha256(body).hexdigest()
                    or metadata.get("request") != parameters
                    or metadata.get("url") != disclosures.SEARCH_URL):
                raise ValueError("Official index raw-response binding mismatch")
            acquired = datetime.fromisoformat(metadata["acquired_at"])
            if acquired.utcoffset() is None or not started <= acquired <= datetime.now(timezone.utc):
                raise ValueError("Official index acquisition clock invalid")
            path = output / f"index-{len(bindings) + 1}.json"
            with path.open("xb") as handle:
                handle.write(body)
            ref = dict(path=path.relative_to(root).as_posix(), sha256=_hash(path),
                       metadata=metadata)
            bindings.append(ref)
            captured.append(body)

        for attempt in range(1, 3):
            try:
                payload = disclosures._request_json(parameters, raw_response_sink=capture)
                attempts.append(dict(kind="INDEX", attempt=attempt, status="RECEIVED"))
                break
            except Exception as error:
                if not retry(error, kind="INDEX", attempt=attempt, captured=bool(captured)):
                    raise
        if len(captured) != 1 or json.loads(captured[0]) != payload:
            raise ValueError("Official index missing raw response")
        return payload

    try:
        row, published = _discover(query, symbol=symbol, issuer_name=issuer_name,
                                   period=period, kind=kind, today=today)
        url = disclosures.PDF_BASE_URL + row["adjunctUrl"]
        if shutil.disk_usage(output).free < 2 * 1024**3 + 32 * 1024**2:
            raise OSError("Preserve 2 GiB reserve before official download")
        for attempt in range(1, 3):
            pdf = output / ("original.pdf" if attempt == 1 else "original-retry-2.pdf")
            try:
                digest = download_official_pdf(url, pdf)
                attempts.append(dict(kind="PDF", attempt=attempt, status="RECEIVED"))
                break
            except Exception as error:
                if not retry(error, kind="PDF", attempt=attempt):
                    raise
        acquired = datetime.now(timezone.utc)
        _verify_cover(extract_pages(pdf, limit=IDENTITY_PAGE_LIMIT), symbol=symbol,
                      issuer_name=issuer_name, period=period, kind=kind)
        source = dict(symbol=symbol, period=period, path=pdf.relative_to(root).as_posix(),
                      sha256=digest, source_url=url, available_at=acquired.isoformat())
        result = dict(schema_version=VERSION, status="ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED",
                      source=source, source_id="cninfo:" + str(row["announcementId"]),
                      report_kind=kind, published_date=published.isoformat(),
                      publication_precision="DATE_ONLY", fetched_at=acquired.isoformat(),
                      historical_available_at=None, strict_historical_pit=False,
                      index_bindings=bindings, request_attempts=attempts,
                      formal_eligibility=False, action="no_order",
                      started_at=started.isoformat(), completed_at=datetime.now(timezone.utc).isoformat())
        if _hash(pdf) != digest or any(_hash(root / ref["path"]) != ref["sha256"] for ref in bindings):
            raise ValueError("Official acquisition source drift")
        _write(output / "receipt.json", result)
        return result
    except Exception as error:
        _write(output / "failure.json", dict(schema_version=VERSION, status="FAILED",
               error=type(error).__name__ + ":" + str(error), index_bindings=bindings,
               request_attempts=attempts,
               completed_at=datetime.now(timezone.utc).isoformat(), action="no_order"))
        raise


def load_retained_official_report(*, root: Path, receipt_binding: dict,
                                 symbol: str, issuer_name: str, period: str) -> dict:
    """Read-only, exact-bound reuse; no network or new freshness/PIT claims.

    The caller must retain and pin the receipt. No directory search, automatic
    fallback, historical restamping, or assumption that no newer report exists.
    """
    root = root.resolve()
    closure = []

    def bound(ref):
        path = (root / ref["path"]).resolve()
        digest = ref["sha256"]
        if (not path.is_relative_to(root / "runtime")
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or _hash(path) != digest):
            raise ValueError("Retained official evidence binding invalid")
        closure.append((path, digest))
        return path

    packet = json.loads(bound(receipt_binding).read_bytes())
    source = packet["source"]
    if (packet.get("schema_version") != VERSION
            or packet.get("status") != "ORIGINAL_ACQUIRED_NOT_FACT_ADMITTED"
            or packet.get("action") != "no_order" or packet.get("formal_eligibility") is not False
            or packet.get("strict_historical_pit") is not False
            or packet.get("historical_available_at") is not None
            or source.get("symbol") != symbol or source.get("period") != period
            or period[4:] not in ("-12-31", "-06-30")
            or not isinstance(issuer_name, str) or not issuer_name.strip()):
        raise ValueError("Retained official receipt identity or assurance invalid")
    kind = "annual" if period[4:] == "-12-31" else "interim"
    started, fetched, completed = (datetime.fromisoformat(packet[key])
                                   for key in ("started_at", "fetched_at", "completed_at"))
    if (any(clock.utcoffset() is None for clock in (started, fetched, completed))
            or not started <= fetched <= completed <= datetime.now(timezone.utc)
            or source.get("available_at") != packet["fetched_at"]
            or packet.get("publication_precision") != "DATE_ONLY"
            or packet.get("report_kind") != kind):
        raise ValueError("Retained official receipt clock invalid")
    refs = packet["index_bindings"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 7:
        raise ValueError("Retained official raw index budget invalid")
    position = 0

    def query(parameters):
        nonlocal position
        if position >= len(refs):
            raise ValueError("Retained official index incomplete")
        ref = refs[position]
        position += 1
        metadata = ref["metadata"]
        acquired = datetime.fromisoformat(metadata["acquired_at"])
        if (metadata.get("request") != parameters
                or metadata.get("url") != disclosures.SEARCH_URL
                or metadata.get("sha256") != ref["sha256"]
                or acquired.utcoffset() is None or not started <= acquired <= fetched):
            raise ValueError("Retained official index request or clock invalid")
        return json.loads(bound(ref).read_bytes())

    row, published = _discover(query, symbol=symbol, issuer_name=issuer_name,
        period=period, kind=kind, today=started.astimezone(CHINA).date())
    if (position != len(refs) or packet.get("source_id") != "cninfo:" + str(row["announcementId"])
            or source.get("source_url") != disclosures.PDF_BASE_URL + row["adjunctUrl"]
            or packet.get("published_date") != published.isoformat()):
        raise ValueError("Retained official discovery differs from receipt")
    pdf = bound(source)
    validate_pdf_original(pdf)
    _verify_cover(extract_pages(pdf, limit=IDENTITY_PAGE_LIMIT), symbol=symbol, issuer_name=issuer_name,
                  period=period, kind=kind)
    if any(_hash(path) != digest for path, digest in closure):
        raise ValueError("Retained official evidence changed during reuse")
    return packet
