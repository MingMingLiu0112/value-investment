"""Bounded dated Tencent quotes joined to an explicit Sina classification."""
import hashlib
import re
import time as retry_time
from datetime import datetime, time, timezone
from decimal import Decimal

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
                text = raw.decode("gb18030")
                parsed, position = {}, 0
                for match in re.finditer(r'v_((?:sh|sz)\d{6})="([^"\r\n]*)";', text):
                    if text[position:match.start()].strip() or match[1] in parsed or match[1] not in ids:
                        raise ValueError("Unexpected quote assignment")
                    parsed[match[1]] = match[2].split("~")
                    position = match.end()
                if text[position:].strip():
                    raise ValueError("Unexpected response content")
                for identity in ids:
                    symbol = identity[2:]
                    try:
                        fields = parsed[identity]
                        if len(fields) < 38 or fields[2] != symbol:
                            raise ValueError("Quote identity/layout mismatch")
                        trade_at = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(tzinfo=CHINA)
                        if trade_at > stamp or trade_at.time() < time(15):
                            raise ValueError("Incomplete or future quote")
                        close, previous, volume, amount = (Decimal(fields[k]) for k in (3, 4, 6, 37))
                        if not all(n.is_finite() and n > 0 for n in (close, previous, volume, amount)):
                            raise ValueError("Invalid or suspended quote")
                        rows.append(dict(symbol=symbol, company_name=fields[1], close=str(close),
                            change_percent=str((close / previous - 1) * 100), amount_cny=str(amount * 10000),
                            trade_date=trade_at.date().isoformat(), quote_at=trade_at.isoformat(),
                            available_at=stamp.isoformat(), source_url=response.url, sha256=digest,
                            status="DATED_COMPLETED_QUOTE"))
                    except (ValueError, KeyError, ArithmeticError) as error:
                        failures.append(dict(symbol=symbol, reason=str(error)))
            except (requests.RequestException, ValueError, OSError) as error:
                failures.extend(dict(symbol=symbol, reason=str(error)) for symbol in batch)
    finally:
        if owned:
            session.close()
    return rows, sources, failures
