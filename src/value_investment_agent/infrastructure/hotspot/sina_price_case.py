"""Source-bound Sina OHLCV capture for a historical hotspot case."""

from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo

import requests

from value_investment_agent.domain.hotspot.price_action_plan import calculate_price_levels
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent.domain.execution.exchange_calendar import is_exchange_session
from value_investment_agent.m1_historical_quote import quote_snapshot_from_historical_close_manifest

ENDPOINT = "https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData"
PERIODS = {"60m": "60", "15m": "15"}
BLOCKERS = ["SINGLE_PROVIDER_NO_B1_CLOSE_CROSSCHECK",
            "EVENT_AND_RISK_GATES_NOT_PROVEN", "HISTORICAL_NOT_CURRENT",
            "CORPORATE_ACTION_REVIEW_NOT_PROVEN"]
CROSSCHECK_BLOCKERS = ["INTRADAY_SINGLE_PROVIDER", "EVENT_AND_RISK_GATES_NOT_PROVEN",
                       "HISTORICAL_NOT_CURRENT", "CORPORATE_ACTION_REVIEW_NOT_PROVEN"]


def _source_url_valid(url: str, *, symbol: str, scale: str) -> bool:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    market_symbol = ("sz" if symbol.startswith(("0", "3")) else "sh") + symbol
    return (parsed.scheme == "https" and parsed.hostname == "quotes.sina.cn"
            and parsed.path.endswith("/CN_MarketDataService.getKLineData")
            and query.get("symbol") == [market_symbol]
            and query.get("scale") == [scale]
            and query.get("ma") == ["no"])


def parse_klines(raw: bytes, *, period: str, as_of: date,
                 completed_through: datetime | None = None) -> list[dict]:
    """Historical full-close parsing by default; explicit cutoff opts into bars.

    The intraday mode rejects uncompleted/off-grid rows rather than silently
    falling back to a prior bar. It does not establish source provenance.
    """
    if period not in PERIODS:
        raise ValueError("Unsupported period")
    if completed_through is not None:
        if (not isinstance(completed_through, datetime) or completed_through.utcoffset() is None
                or type(as_of) is not date):
            raise ValueError("Aware completed-through clock and date-only as_of required")
        completed_through = completed_through.astimezone(ZoneInfo("Asia/Shanghai"))
        if completed_through.date() != as_of or not is_exchange_session("SSE", as_of):
            raise ValueError("Completed-through date must be a covered exchange session")
    text = raw.decode("utf-8")
    opening = text.find("=([")
    closing = text.rfind("]);")
    if opening < 0 or closing < opening:
        raise ValueError("Provider JSONP wrapper invalid")
    rows = json.loads(text[opening + 2:closing + 1])
    if not isinstance(rows, list) or len(rows) > 2500:
        raise ValueError("Provider did not return kline rows")
    result = []
    for row in rows:
        stamp = datetime.fromisoformat(row["day"])
        if completed_through is not None:
            if (stamp.utcoffset() is not None or stamp.microsecond
                    or stamp.strftime("%H:%M:%S") not in SESSION_TIMES[period]
                    or not is_exchange_session("SSE", stamp.date())):
                raise ValueError("Uncompleted, future or off-grid provider bar")
            if stamp.replace(tzinfo=ZoneInfo("Asia/Shanghai")) > completed_through:
                if stamp.date() != as_of:
                    raise ValueError("Future-dated provider bar")
                # The live endpoint appends the current partial bar. Exclude it
                # from the completed set rather than rejecting every prior bar.
                continue
        if stamp.date() > as_of or (stamp.date() == as_of and stamp.time() > time(15)):
            continue
        if stamp.time() < time(9, 30) or stamp.time() > time(15):
            continue
        bar = {"time": stamp.isoformat(sep=" ")}
        for field in ("open", "high", "low", "close", "volume", "amount"):
            value = Decimal(str(row[field]))
            if not value.is_finite() or value < 0:
                raise ValueError("Invalid provider bar")
            bar[field] = str(value)
        result.append(bar)
    if not result or result[-1]["time"][:10] != as_of.isoformat():
        raise ValueError("No bars at requested date")
    if completed_through is None and result[-1]["time"][11:16] != "15:00":
        raise ValueError("Requested session has no completed final bar")
    if [bar["time"] for bar in result] != sorted({bar["time"] for bar in result}):
        raise ValueError("Duplicate or unordered provider bars")
    return result


def daily_from_intraday(bars: list[dict]) -> list[dict]:
    days: dict[str, list[dict]] = {}
    for bar in bars:
        days.setdefault(bar["time"][:10], []).append(bar)
    result = []
    for day, rows in days.items():
        # A full A-share session has four 60-minute bars and ends at 15:00.
        if len(rows) != 4 or rows[-1]["time"][11:16] != "15:00":
            continue
        result.append({
            "time": day, "open": rows[0]["open"], "close": rows[-1]["close"],
            "high": str(max(Decimal(row["high"]) for row in rows)),
            "low": str(min(Decimal(row["low"]) for row in rows)),
            "volume": str(sum(Decimal(row["volume"]) for row in rows)),
            "amount": str(sum(Decimal(row["amount"]) for row in rows)),
        })
    return result


def collect_historical_case(*, root: Path, symbol: str, as_of: date, fetch=None) -> dict:
    """Publish a complete immutable historical observation or nothing."""
    if not (len(symbol) == 6 and symbol.isdigit()
            and symbol.startswith(("0", "3", "6"))):
        raise ValueError("Supported SSE/SZSE six-digit symbol required")
    if as_of >= datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("Only completed historical dates are accepted")
    destination = root / "runtime" / "hotspot-price-cases" / f"{symbol}-{as_of.isoformat()}"
    if destination.exists():
        raise FileExistsError(destination)
    stage = root / ".tmp" / "hotspot-price-cases" / uuid4().hex
    stage.mkdir(parents=True)
    sources = {}
    bars_by_period = {}
    levels = {}
    session = requests.Session()
    fetch = fetch or session.get
    try:
        market_symbol = ("sz" if symbol.startswith(("0", "3")) else "sh") + symbol
        for period, scale in PERIODS.items():
            response = fetch(ENDPOINT, params=dict(symbol=market_symbol, scale=scale,
                                                  ma="no", datalen="1970"), timeout=15)
            response.raise_for_status()
            if not _source_url_valid(response.url, symbol=symbol, scale=scale):
                raise ValueError("Provider URL does not bind requested symbol")
            raw = response.content
            if not raw or len(raw) > 5 * 1024 * 1024:
                raise ValueError("Provider response empty or oversized")
            bars = parse_klines(raw, period=period, as_of=as_of)
            if len(bars) < 6:
                raise ValueError(f"Insufficient {period} bars")
            levels[period] = calculate_price_levels(bars, period=period)
            name = f"sina-{period}.jsonp"
            (stage / name).write_bytes(raw)
            sources[period] = {
                "path": (destination / name).relative_to(root).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_url": response.url,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "adjustment": "UNADJUSTED",
                "scope": "SINGLE_PROVIDER_HISTORICAL_OBSERVATION",
            }
            bars_by_period[period] = bars
        daily = daily_from_intraday(bars_by_period["60m"])
        if len(daily) < 6 or daily[-1]["time"] != as_of.isoformat():
            raise ValueError("Insufficient complete derived daily bars")
        if daily[-1]["close"] != bars_by_period["15m"][-1]["close"]:
            raise ValueError("Intraday source close conflict")
        bars_by_period["daily"] = daily
        levels["daily"] = calculate_price_levels(daily, period="daily")
        sources["daily"] = {**sources["60m"],
                            "scope": "DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE"}
        result = {
            "schema_version": "hotspot-historical-price-case-v1",
            "symbol": symbol, "strategy": "HOTSPOT_SATELLITE",
            "market_trade_date": as_of.isoformat(),
            "current_reference_price": daily[-1]["close"],
            "levels": levels, "bars": bars_by_period, "source_bindings": sources,
            "signal_state": "HISTORICAL_OBSERVATION_NOT_ADMITTED",
            "blockers": BLOCKERS,
            "action": "no_order",
        }
        (stage / "case.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        destination.parent.mkdir(parents=True, exist_ok=True)
        stage.rename(destination)
        return result
    finally:
        session.close()


def load_historical_case(*, root: Path, symbol: str, as_of: date) -> dict:
    """Re-verify every original and every level before Web presentation."""
    if not (len(symbol) == 6 and symbol.isdigit()
            and symbol.startswith(("0", "3", "6"))):
        raise ValueError("Invalid symbol")
    directory = root / "runtime" / "hotspot-price-cases" / f"{symbol}-{as_of.isoformat()}"
    case = json.loads((directory / "case.json").read_text(encoding="utf-8"))
    if (case.get("schema_version") != "hotspot-historical-price-case-v1"
            or case.get("symbol") != symbol or case.get("market_trade_date") != as_of.isoformat()
            or case.get("action") != "no_order"
            or case.get("signal_state") != "HISTORICAL_OBSERVATION_NOT_ADMITTED"
            or case.get("strategy") != "HOTSPOT_SATELLITE"
            or case.get("blockers") != BLOCKERS):
        raise ValueError("Historical case contract mismatch")
    bars = {}
    for period in PERIODS:
        source = case["source_bindings"][period]
        expected = directory / f"sina-{period}.jsonp"
        if source["path"] != expected.relative_to(root).as_posix():
            raise ValueError("Historical source path mismatch")
        if (source.get("adjustment") != "UNADJUSTED"
                or not _source_url_valid(source.get("source_url", ""),
                                         symbol=symbol, scale=PERIODS[period])):
            raise ValueError("Historical source identity mismatch")
        fetched = datetime.fromisoformat(source["fetched_at"])
        closed = datetime.combine(as_of, time(15), tzinfo=ZoneInfo("Asia/Shanghai"))
        if (fetched.utcoffset() is None or fetched <= closed
                or fetched > datetime.now(timezone.utc)):
            raise ValueError("Historical source availability invalid")
        raw = expected.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("Historical source hash mismatch")
        bars[period] = parse_klines(raw, period=period, as_of=as_of)
    bars["daily"] = daily_from_intraday(bars["60m"])
    daily_source = case["source_bindings"]["daily"]
    if (daily_source["path"] != case["source_bindings"]["60m"]["path"]
            or daily_source["sha256"] != case["source_bindings"]["60m"]["sha256"]
            or daily_source["scope"] != "DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE"):
        raise ValueError("Derived daily source identity mismatch")
    if bars["daily"][-1]["close"] != bars["15m"][-1]["close"]:
        raise ValueError("Historical close conflict")
    levels = {period: calculate_price_levels(period_bars, period=period)
              for period, period_bars in bars.items()}
    if (case.get("bars") != bars or case.get("levels") != levels
            or case.get("current_reference_price") != bars["daily"][-1]["close"]):
        raise ValueError("Historical case calculation mismatch")
    binding_path = directory / "close-crosscheck.json"
    if binding_path.is_file():
        binding = json.loads(binding_path.read_text(encoding="utf-8"))
        path = root / binding["manifest_path"]
        snapshot = quote_snapshot_from_historical_close_manifest(
            path, root, expected_sha256=binding["manifest_sha256"])
        if (snapshot.symbol != symbol or snapshot.quote_date != as_of
                or snapshot.current_price != Decimal(bars["daily"][-1]["close"])
                or snapshot.status != "verified_close"):
            raise ValueError("Cross-source close differs from intraday case")
        case["close_crosscheck"] = {
            "status": "VERIFIED_HISTORICAL_CLOSE",
            "price": str(snapshot.current_price),
            "manifest_path": binding["manifest_path"],
            "manifest_sha256": binding["manifest_sha256"],
            "evidence_refs": snapshot.evidence_refs,
        }
        case["blockers"] = CROSSCHECK_BLOCKERS
    case["bar_timezone"] = "Asia/Shanghai"
    return case


def bind_historical_close(*, root: Path, symbol: str, as_of: date,
                          manifest_path: Path) -> dict:
    """Append a verified M1 close; the minute originals and case never change."""
    case = load_historical_case(root=root, symbol=symbol, as_of=as_of)
    if "close_crosscheck" in case:
        raise FileExistsError("Historical close already bound")
    path = manifest_path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Close manifest outside project")
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    snapshot = quote_snapshot_from_historical_close_manifest(path, root, expected_sha256=sha)
    if (snapshot.symbol != symbol or snapshot.quote_date != as_of
            or snapshot.current_price != Decimal(case["current_reference_price"])):
        raise ValueError("Close manifest does not match historical intraday case")
    binding = {"manifest_path": path.relative_to(root.resolve()).as_posix(),
               "manifest_sha256": sha}
    target = root / "runtime" / "hotspot-price-cases" / f"{symbol}-{as_of.isoformat()}" / "close-crosscheck.json"
    with target.open("x", encoding="utf-8") as stream:
        json.dump(binding, stream, ensure_ascii=False, indent=2)
    return load_historical_case(root=root, symbol=symbol, as_of=as_of)["close_crosscheck"]
