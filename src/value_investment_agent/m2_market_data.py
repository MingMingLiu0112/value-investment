"""Read-only market-data adapters for the M2 opportunity funnel.

Every adapter returns raw evidence bytes plus normalized rows.  Network and
provider failures are raised explicitly; the run script is responsible for
recording them as PENDING_EXTERNAL_DATA instead of inventing coverage.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import math
import time
from typing import Any, Iterable

import requests


TENCENT_BOARD_URL = "https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList"
TENCENT_QUOTE_URL = "https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj"
SINA_CLASSIFY_URL = "https://vip.stock.finance.sina.com.cn/mkt/#hs_a"
EASTMONEY_DIVIDEND_URL = "https://data.eastmoney.com/yjfp/"

ADAPTER_VERSION = "m2-market-data-v1"


def _number(value: object, *, field: str = "value") -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _code(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith(("sh", "sz", "bj")) and len(text) >= 8:
        text = text[2:]
    text = text.zfill(6)
    if not text.isdigit() or len(text) != 6:
        raise ValueError(f"Invalid security code from provider: {value}")
    return text


def _raw_json(rows: Iterable[dict[str, Any]], **metadata: Any) -> tuple[bytes, dict[str, Any]]:
    payload = {
        "adapter_version": ADAPTER_VERSION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        **metadata,
        "rows": [
            dict(row) if isinstance(row, dict) else list(row)
            for row in rows
        ],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return raw, payload


def _requests_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def fetch_tencent_board_rank(*, session: requests.Session | None = None) -> tuple[bytes, dict[str, Any]]:
    """Return the full Tencent A-share board snapshot without partial fallback."""
    session = session or _requests_session()
    rows: list[dict[str, Any]] = []
    total: int | None = None
    offset = 0
    for _ in range(40):
        requested_offset = offset
        params = {
            "_appver": "11.17.0",
            "board_code": "aStock",
            "sort_type": "price",
            "direct": "down",
            "offset": str(requested_offset),
            "count": "200",
        }
        response = session.get(TENCENT_BOARD_URL, params=params, timeout=(15, 30))
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, dict) or "rank_list" not in data:
            raise RuntimeError(f"Tencent board response shape changed: {payload.get('msg')}")
        declared_total = int(data.get("total") or 0)
        if declared_total <= 0:
            raise RuntimeError("Tencent board response has no declared total")
        if total is None:
            total = declared_total
        elif total != declared_total:
            raise RuntimeError("Tencent board total changed during pagination")
        page_rows = data.get("rank_list") or []
        returned_offset = data.get("offset")
        if returned_offset is None or int(returned_offset) != requested_offset:
            raise RuntimeError("Tencent board response offset does not match request")
        if not page_rows:
            break
        rows.extend(page_rows)
        if len(rows) > total:
            raise RuntimeError("Tencent board pagination returned too many rows")
        if len(rows) >= total:
            break
        offset += len(page_rows)
    if total is None or len(rows) != total:
        raise RuntimeError(f"Tencent board snapshot incomplete: {len(rows)}/{total}")
    raw, payload = _raw_json(
        rows,
        source_name="AkShare / Tencent all-A market snapshot",
        source_url=TENCENT_QUOTE_URL,
        endpoint=TENCENT_BOARD_URL,
        total=total,
    )
    return raw, payload


def parse_tencent_board(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in payload.get("rows") or []:
        symbol = _code(raw_row.get("code"))
        name = str(raw_row.get("name") or "").strip()
        if not name:
            raise ValueError("Tencent row is missing company name")
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "current_price": _number(raw_row.get("zxj"), field="current_price"),
                "pe_ttm": _number(raw_row.get("pe_ttm"), field="pe_ttm"),
                "pb": _number(raw_row.get("pn"), field="pb"),
                "market_cap": (
                    _number(raw_row.get("zsz"), field="market_cap") * Decimal("100000000")
                    if _number(raw_row.get("zsz"), field="market_cap") is not None
                    else None
                ),
                "stock_type": str(raw_row.get("stock_type") or "").strip(),
                "state": str(raw_row.get("state") or "").strip(),
                "price_yoy_percent": _number(raw_row.get("zdf_y"), field="price_yoy"),
            }
        )
    if not rows:
        raise ValueError("Tencent board payload has no rows")
    return rows


def fetch_sina_industry_quotes() -> tuple[bytes, dict[str, Any]]:
    """Fetch the Sina maintained Shenwan classification and same-session quotes."""
    try:
        from akshare.stock_feature.stock_classify_sina import stock_classify_sina
    except ImportError as error:
        raise RuntimeError("AkShare Sina classification adapter is unavailable") from error
    last_error: Exception | None = None
    frame = None
    for attempt in range(3):
        try:
            frame = stock_classify_sina("申万行业")
            break
        except Exception as error:
            last_error = error
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    if frame is None:
        raise RuntimeError("Sina industry quote adapter failed after retries") from last_error
    if frame is None or getattr(frame, "empty", False):
        raise RuntimeError("Sina industry quote response is empty")
    rows = frame.to_dict("records")
    raw, payload = _raw_json(
        rows,
        source_name="AkShare / Sina Shenwan level-1 industry and quote snapshot",
        source_url=SINA_CLASSIFY_URL,
        classification="申万行业",
    )
    return raw, payload


def parse_sina_industry(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in payload.get("rows") or []:
        rows.append(
            {
                "symbol": _code(raw_row.get("code")),
                "name": str(raw_row.get("name") or "").strip(),
                "industry": str(raw_row.get("class") or "").strip() or None,
                "current_price": _number(raw_row.get("trade"), field="current_price"),
                "pe_ttm": _number(raw_row.get("per"), field="pe_ttm"),
                "pb": _number(raw_row.get("pb"), field="pb"),
                "market_cap": (
                    _number(raw_row.get("mktcap"), field="market_cap") * Decimal("10000")
                    if _number(raw_row.get("mktcap"), field="market_cap") is not None
                    else None
                ),
                "ticktime": str(raw_row.get("ticktime") or "").strip(),
            }
        )
    if not rows:
        raise ValueError("Sina industry payload has no rows")
    return rows


def fetch_eastmoney_dividends(fiscal_year: int = 2025) -> tuple[bytes, dict[str, Any]]:
    try:
        import akshare as ak
    except ImportError as error:
        raise RuntimeError("AkShare is unavailable for the dividend adapter") from error
    frame = ak.stock_fhps_em(date=f"{fiscal_year}1231")
    if frame is None or getattr(frame, "empty", False):
        raise RuntimeError("Eastmoney dividend response is empty")
    rows = frame.values.tolist()
    raw, payload = _raw_json(
        rows,
        source_name="AkShare / Eastmoney annual cash dividend plan snapshot",
        source_url=EASTMONEY_DIVIDEND_URL,
        fiscal_year=str(fiscal_year),
    )
    return raw, payload


def parse_eastmoney_dividends(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_row in payload.get("rows") or []:
        if isinstance(raw_row, dict):
            values = [str(raw_row.get(index) or "") for index in range(18)]
        else:
            values = [str(value) if value is not None else "" for value in raw_row]
            values.extend("" for _ in range(max(0, 18 - len(values))))
        symbol = _code(values[0])
        name = values[1].strip()
        cash_per_ten = _number(values[5], field="cash_per_ten")
        yield_ratio = _number(values[6], field="declared_yield")
        if not name:
            raise ValueError("Eastmoney dividend row is missing company name")
        rows.append(
            {
                "symbol": symbol,
                "name": name,
                "cash_dps": (
                    cash_per_ten / Decimal("10") if cash_per_ten is not None else None
                ),
                "declared_yield": yield_ratio,
                "declaration_date": values[13] or None,
                "record_date": values[14] or None,
                "ex_dividend_date": values[15] or None,
                "status": values[16] or None,
                "update_date": values[17] or None,
                "fiscal_year": str(payload.get("fiscal_year") or ""),
            }
        )
    if not rows:
        raise ValueError("Eastmoney dividend payload has no rows")
    return rows
