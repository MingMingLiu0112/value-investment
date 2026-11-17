"""Bounded raw Sina minute documents; no parsing, storage or admission."""
import base64
from datetime import datetime, timezone
import hashlib
from time import monotonic
from urllib.parse import urlencode

import requests

from .sina_price_case import ENDPOINT, PERIODS


MAX_BYTES = 5 * 1024 * 1024
BAR_COUNT = 8


def collect_intraday_bar_documents(symbol: str, *, session=None, clock=None) -> dict:
    """Fetch one 15m and one 60m document, retaining failures per period.

    Optional session/clock are test seams. No retries or redirects; two requests
    maximum, (5s connect, 10s read) timeout and a bounded streamed body each.
    Raw bytes are preserved even for HTTP errors, invalid payloads or oversize.
    """
    if (not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii()
            or not symbol.isdigit() or not symbol.startswith(("0", "3", "6"))):
        raise ValueError("Supported six-digit SSE/SZSE symbol required")
    clock = clock or (lambda: datetime.now(timezone.utc))
    owned = session is None
    session = session or requests.Session()
    documents = {}
    try:
        for period, scale in PERIODS.items():
            url = ENDPOINT + "?" + urlencode(dict(symbol=("sh" if symbol.startswith("6") else "sz")
                + symbol, scale=scale, ma="no", datalen=str(BAR_COUNT)))
            raw = bytearray()
            document = dict(source_url=url, http_status=None, adjustment="UNADJUSTED")
            response = None
            try:
                started = monotonic()
                response = session.get(url, timeout=(5, 10), stream=True, allow_redirects=False)
                document.update(source_url=response.url, http_status=response.status_code)
                for chunk in response.iter_content(chunk_size=65536):
                    raw.extend(chunk[:MAX_BYTES + 1 - len(raw)])
                    if len(raw) > MAX_BYTES:
                        document["error"] = "RESPONSE_TOO_LARGE"
                        break
                    if monotonic() - started > 15:
                        document["error"] = "RESPONSE_TIME_LIMIT"
                        break
            except requests.RequestException:
                document["error"] = "SOURCE_REQUEST_FAILED"
            finally:
                if response is not None:
                    response.close()
            fetched = clock()
            if not isinstance(fetched, datetime) or fetched.utcoffset() is None:
                raise ValueError("Aware collection clock required")
            document.update(raw_base64=base64.b64encode(raw).decode("ascii"),
                sha256=hashlib.sha256(raw).hexdigest(),
                fetched_at=fetched.astimezone(timezone.utc).isoformat())
            documents[period] = document
        return documents
    finally:
        if owned:
            session.close()
