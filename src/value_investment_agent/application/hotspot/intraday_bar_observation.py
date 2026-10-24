"""Read-only retained Sina completed-bar bridge; single-provider observation only."""
import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
from urllib.parse import parse_qs, urlparse

from .intraday_conditions import CHINA, _session, _stamp
from ...infrastructure.hotspot.sina_price_case import ENDPOINT, PERIODS, parse_klines


SCHEMA = "retained-intraday-bar-observation-v1"
BLOCKERS = ("INTRADAY_SINGLE_PROVIDER", "SINGLE_PROVIDER_NO_B1_CLOSE_CROSSCHECK",
            "EVENT_AND_RISK_GATES_NOT_PROVEN", "CORPORATE_ACTION_REVIEW_NOT_PROVEN")


def project_intraday_bar_observation(document: dict, *, symbol: str, period: str,
        now: datetime, max_age: timedelta, max_bar_age: timedelta | None = None) -> dict:
    """Replay retained raw_base64/sha256/source_url/fetched_at/http_status.

    The bar's exchange-local end is source_at (a conservative price clock),
    never the receipt time. No collection, files, levels or strategy changes.
    URL/hash binding detects local mismatch; it does not attest server identity
    or prove that acquisition metadata cannot have been deliberately forged.
    """
    if (not isinstance(now, datetime) or now.utcoffset() is None
            or not isinstance(max_age, timedelta) or max_age <= timedelta(0)
            or (max_bar_age is not None and (not isinstance(max_bar_age, timedelta)
                or max_bar_age <= timedelta(0)))):
        raise ValueError("Aware server clock and positive max_age required")
    bar_age = max_age if max_bar_age is None else max_bar_age
    if (not isinstance(symbol, str) or len(symbol) != 6 or not symbol.isascii()
            or not symbol.isdigit() or not symbol.startswith(("0", "3", "6"))
            or period not in PERIODS):
        raise ValueError("Supported six-digit symbol and 15m/60m period required")
    now = now.astimezone(timezone.utc)
    venue = "SSE" if symbol.startswith("6") else "SZSE"
    result = {"schema_version": SCHEMA, "symbol": symbol, "period": period,
        "status": "STALE_OR_UNAVAILABLE", "reason": "RETAINED_BAR_INVALID", "observation": None,
        "source_scope": "SINGLE_PROVIDER_COMPLETED_BAR_OBSERVATION", "blockers": list(BLOCKERS),
        "action": "no_order", "eligibility": False, "formal_eligibility": False,
        "admitted": False, "b1_eligible": False}
    try:
        if not _session(venue, now):
            result["reason"] = "OUTSIDE_EXCHANGE_SESSION"
            return result
        url = document["source_url"]
        parsed, endpoint = urlparse(url), urlparse(ENDPOINT)
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
        market_symbol = ("sh" if venue == "SSE" else "sz") + symbol
        if (parsed.scheme != endpoint.scheme or parsed.netloc != endpoint.netloc
                or parsed.path != endpoint.path or parsed.fragment or parsed.params
                or set(query) - {"symbol", "scale", "ma", "datalen"}
                or query.get("symbol") != [market_symbol] or query.get("scale") != [PERIODS[period]]
                or query.get("ma") != ["no"]
                or ("datalen" in query and (len(query["datalen"]) != 1
                    or not query["datalen"][0].isascii() or not query["datalen"][0].isdigit()
                    or not 1 <= int(query["datalen"][0]) <= 2500))):
            result["reason"] = "SOURCE_URL_IDENTITY_MISMATCH"
            return result
        if (document.get("error") or document.get("adjustment", "UNADJUSTED") != "UNADJUSTED"
                or type(document["http_status"]) is not int or document["http_status"] != 200):
            return result
        fetched = _stamp(document["fetched_at"])
        if (fetched > now or now - fetched > max_age
                or fetched.astimezone(CHINA).date() != now.astimezone(CHINA).date()
                or not _session(venue, fetched)):
            result["reason"] = "STALE_OR_CONFLICTING_RECEIPT_CLOCK"
            return result
        encoded = document["raw_base64"]
        if not isinstance(encoded, str) or len(encoded) > 7 * 1024 * 1024:
            return result
        raw = base64.b64decode(encoded, validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if not raw or len(raw) > 5 * 1024 * 1024 or digest != document["sha256"]:
            result["reason"] = "RAW_BAR_HASH_MISMATCH"
            return result
        result["reason"] = "UNCOMPLETED_OR_INVALID_BAR"
        bars = parse_klines(raw, period=period, as_of=now.astimezone(CHINA).date(),
                            completed_through=fetched)
        bar = bars[-1]
        end = datetime.fromisoformat(bar["time"]).replace(tzinfo=CHINA).astimezone(timezone.utc)
        if not end <= fetched <= now or now - end > bar_age:
            result["reason"] = "STALE_COMPLETED_BAR"
            return result
        opening, high, low, close = (Decimal(bar[key]) for key in ("open", "high", "low", "close"))
        if (low <= 0 or not low <= opening <= high or not low <= close <= high
                or Decimal(bar["volume"]) <= 0 or Decimal(bar["amount"]) <= 0):
            result["reason"] = "INVALID_OR_NONTRADING_BAR"
            return result
        ref = {"id": "sina-bar-" + hashlib.sha256(
            (url + "\n" + fetched.isoformat() + "\n" + digest).encode()).hexdigest(),
            "provider": "sina", "source_url": url, "sha256": digest,
            "source_at": end.isoformat(), "received_at": fetched.isoformat()}
        observation = {"symbol": symbol, "source_id": "sina", "source_url": url,
            "source_at": end.isoformat(), "received_at": fetched.isoformat(),
            "price": bar["close"], "quality": "VERIFIED", "suspended": False,
            "input_kind": "COMPLETED_BAR", "period": period, "bar_end": end.isoformat(),
            "bar_start": (end - timedelta(minutes=int(PERIODS[period]))).isoformat(),
            "open": bar["open"], "high": bar["high"], "low": bar["low"],
            "close": bar["close"], "volume": bar["volume"], "amount": bar["amount"],
            "adjustment_basis": "UNADJUSTED", "raw_sha256": digest,
            "completed": True, "bar": dict(bar), "evidence_refs": [ref],
            "verified_at": now.isoformat(), "blockers": list(BLOCKERS),
            "action": "no_order", "eligibility": False, "formal_eligibility": False,
            "admitted": False, "b1_eligible": False}
        result.update(status="COMPLETED_BAR_VERIFIED", reason="SINGLE_PROVIDER_COMPLETED_BAR_ONLY",
                      observation=observation)
        return result
    except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError, UnicodeError):
        return result
