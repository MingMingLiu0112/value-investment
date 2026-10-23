"""Bounded dated Tencent quotes joined to an explicit Sina classification."""
import hashlib
import re
import time as retry_time
from datetime import datetime, time, timezone
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import requests

from ...quote_sessions import CHINA


def bounded_get(fetch, url, *, sleep=None, **kwargs):
    """Retry transient transport/HTTP failures at most three times (1s, 2s)."""
    sleep = sleep or retry_time.sleep
    for attempt in range(3):
        try:
            response = fetch(url, **kwargs)
            response.raise_for_status()
            response.request_attempts = attempt + 1
            return response
        except requests.RequestException as error:
            status = getattr(getattr(error, "response", None), "status_code", None)
            transient = (isinstance(error, (requests.Timeout, requests.ConnectionError))
                         or status in {408, 429, 500, 502, 503, 504})
            if isinstance(error, requests.exceptions.SSLError):
                transient = False
            if not transient or attempt == 2:
                error.request_attempts = attempt + 1
                raise
            if getattr(error, "response", None) is not None:
                error.response.close()
            sleep(2 ** attempt)


def requested_quote_symbols(source_url: str) -> list[str]:
    """Recover the retained Tencent request's bounded, explicit batch."""
    url = urlsplit(source_url)
    if url.scheme not in {"https", "http"} or url.netloc != "qt.gtimg.cn" or url.fragment:
        raise ValueError("Invalid Tencent quote request URL")
    if url.path.startswith("/q=") and not url.query:
        parameters = url.path[1:]
    elif url.path in {"", "/"}:
        parameters = url.query
    else:
        raise ValueError("Missing Tencent quote request batch")
    query = parse_qs(parameters, keep_blank_values=True, strict_parsing=True)
    if set(query) != {"q"} or len(query["q"]) != 1:
        raise ValueError("Ambiguous Tencent quote request batch")
    ids = query["q"][0].split(",")
    if (not 1 <= len(ids) <= 200 or len(set(ids)) != len(ids)
            or any(not re.fullmatch(r"(?:sh6|sz[03])\d{5}", identity) for identity in ids)):
        raise ValueError("Invalid Tencent quote request symbols")
    return [identity[2:] for identity in ids]


def parse_dated_market(raw: bytes, *, symbols: list[str], available_at: datetime,
                       source_url: str) -> tuple[list[dict], list[dict]]:
    """Replay the collector's completed, positive-turnover quote contract."""
    if requested_quote_symbols(source_url) != symbols:
        raise ValueError("Tencent quote request batch mismatch")
    ids = [("sh" if s.startswith("6") else "sz") + s for s in symbols]
    allowed = set(ids)
    text = raw.decode("gb18030")
    parsed, position = {}, 0
    for match in re.finditer(r'v_((?:sh|sz)\d{6})="([^"\r\n]*)";', text):
        if text[position:match.start()].strip() or match[1] in parsed or match[1] not in allowed:
            raise ValueError("Unexpected quote assignment")
        parsed[match[1]] = match[2].split("~")
        position = match.end()
    if text[position:].strip():
        raise ValueError("Unexpected response content")
    rows, failures = [], []
    digest = hashlib.sha256(raw).hexdigest()
    for identity in ids:
        symbol = identity[2:]
        try:
            fields = parsed[identity]
            if len(fields) < 38 or fields[2] != symbol:
                raise ValueError("Quote identity/layout mismatch")
            trade_at = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CHINA)
            if trade_at > available_at or trade_at.time() < time(15):
                raise ValueError("Incomplete or future quote")
            close, previous, volume, amount = (Decimal(fields[k]) for k in (3, 4, 6, 37))
            if not all(n.is_finite() and n > 0 for n in (close, previous, volume, amount)):
                raise ValueError("Invalid or suspended quote")
            rows.append(dict(symbol=symbol, company_name=fields[1], close=str(close),
                change_percent=str((close / previous - 1) * 100), amount_cny=str(amount * 10000),
                trade_date=trade_at.date().isoformat(), quote_at=trade_at.isoformat(),
                available_at=available_at.isoformat(), source_url=source_url, sha256=digest,
                status="DATED_COMPLETED_QUOTE"))
        except (ValueError, KeyError, ArithmeticError) as error:
            failures.append(dict(symbol=symbol, reason=str(error)))
    return rows, failures


def collect_dated_market(symbols: list[str], *, directory, clock=None, session=None) -> tuple[list[dict], list[dict], list[dict]]:
    if not symbols or len(symbols) > 8000 or len(set(symbols)) != len(symbols):
        raise ValueError("Unique bounded market universe required")
    if any(not re.fullmatch(r"[036]\d{5}", s) for s in symbols):
        raise ValueError("Unsupported market symbol")
    clock = clock or (lambda: datetime.now(timezone.utc))
    owned = session is None
    session = session or requests.Session()
    if owned:
        session.trust_env = False
    rows, sources, failures = [], [], []
    try:
        for offset in range(0, len(symbols), 200):
            batch = symbols[offset:offset + 200]
            ids = [("sh" if s.startswith("6") else "sz") + s for s in batch]
            url = "https://qt.gtimg.cn/q=" + ",".join(ids)
            try:
                response = bounded_get(session.get, url, timeout=(10, 20))
                raw = response.content
                if len(raw) > 1_000_000:
                    raise ValueError("Oversized quote response")
                stamp = clock()
                digest = hashlib.sha256(raw).hexdigest()
                target = directory / f"quotes-{offset:05d}.txt"
                with target.open("xb") as stream:
                    stream.write(raw)
                binding = dict(path=target.as_posix(), source_url=response.url, available_at=stamp.isoformat(), sha256=digest,
                               status="ORIGINAL_RETAINED")
                sources.append(binding)
                batch_rows, batch_failures = parse_dated_market(raw, symbols=batch,
                    available_at=stamp, source_url=response.url)
                rows.extend(batch_rows)
                failures.extend(batch_failures)
            except (requests.RequestException, ValueError, OSError) as error:
                failures.extend(dict(symbol=symbol, reason=str(error)) for symbol in batch)
    finally:
        if owned:
            session.close()
    return rows, sources, failures
