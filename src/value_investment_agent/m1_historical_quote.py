"""Dual-source historical-close evidence for M1 current-session quotes.

Unlike the live quote-session gate, this adapter accepts two independently
retained daily-bar responses whose bar date is the most recent completed venue
session.  It never treats an intraday provider price as a verified close.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE, QuoteSnapshot


SCHEMA_VERSION = "m1-dual-source-historical-close-v1"
TOLERANCE = Decimal("0.01")


def _decimal(value: object, field: str) -> Decimal:
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field} must be positive and finite")
    return number


def _validate_ohlc(open_value: Decimal, high: Decimal, low: Decimal, close: Decimal) -> None:
    if not low <= min(open_value, close) <= max(open_value, close) <= high:
        raise ValueError("Daily bar violates OHLC bounds")


def tencent_daily_bar(raw: bytes, symbol: str, target_date: date) -> dict[str, str]:
    """Parse one Tencent unadjusted daily bar from retained raw bytes."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Tencent historical response is not valid JSON") from error
    key = (
        ("sz" if symbol.startswith(("0", "3")) else "sh" if symbol.startswith("6") else "bj")
        + symbol
    )
    rows = payload["data"][key]["day"]
    target = target_date.isoformat()
    matches = [row for row in rows if str(row[0]) == target]
    if len(matches) != 1:
        raise ValueError(f"Tencent response has no unique bar for {target}")
    row = matches[0]
    opening = _decimal(row[1], "Tencent open")
    close = _decimal(row[2], "Tencent close")
    high = _decimal(row[3], "Tencent high")
    low = _decimal(row[4], "Tencent low")
    volume = _decimal(row[5], "Tencent volume")
    _validate_ohlc(opening, high, low, close)
    return {
        "date": target,
        "open": str(opening),
        "close": str(close),
        "high": str(high),
        "low": str(low),
        "volume": str(volume),
    }


def sohu_daily_bar(raw: bytes, symbol: str, target_date: date) -> dict[str, str]:
    """Parse one Sohu unadjusted daily bar from retained raw bytes."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Sohu historical response is not valid JSON") from error
    rows = payload[0]["hq"] if isinstance(payload, list) else payload["hq"]
    target = target_date.isoformat()
    matches = [
        row
        for row in rows
        if str(row[0]) == target
    ]
    if len(matches) != 1:
        raise ValueError(f"Sohu response has no unique bar for {target}")
    fields = matches[0]
    opening = _decimal(fields[1], "Sohu open")
    close = _decimal(fields[2], "Sohu close")
    high = _decimal(fields[6], "Sohu high")
    low = _decimal(fields[5], "Sohu low")
    volume = _decimal(fields[7], "Sohu volume")
    _validate_ohlc(opening, high, low, close)
    return {
        "date": target,
        "open": str(opening),
        "close": str(close),
        "high": str(high),
        "low": str(low),
        "volume": str(volume),
    }


def latest_completed_szse_session(raw: bytes) -> tuple[date, date]:
    """Return (latest completed session, calendar now-date)."""
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("SZSE calendar response is not valid JSON") from error
    now_date = str(payload.get("nowdate") or "")
    if not now_date:
        raise ValueError("SZSE calendar response has no nowdate")
    trading_dates = sorted(
        date.fromisoformat(str(row["jyrq"]))
        for row in payload["data"]
        if str(row.get("jybz")) == "1"
    )
    previous = [day for day in trading_dates if day < date.fromisoformat(now_date)]
    if not previous:
        raise ValueError("SZSE calendar has no completed session")
    return previous[-1], date.fromisoformat(now_date)


def szse_calendar_day(raw: bytes, target_date: date) -> dict[str, str]:
    """Verify that a date is an official SZSE trading day."""
    latest, now_date = latest_completed_szse_session(raw)
    if target_date != latest:
        raise ValueError("Target date is not the latest completed SZSE session")
    target = target_date.isoformat()
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("SZSE calendar response is not valid JSON") from error
    rows = [row for row in payload["data"] if str(row.get("jyrq")) == target]
    if len(rows) != 1 or str(rows[0].get("jybz")) != "1":
        raise ValueError(f"SZSE calendar does not mark {target} as a trading day")
    return {"target_date": target, "calendar_now_date": now_date.isoformat()}


def _document(raw_path: Path, expected_sha256: str) -> bytes:
    if not raw_path.is_file():
        raise FileNotFoundError(f"Historical quote document missing: {raw_path}")
    raw = raw_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
        raise ValueError(f"Historical quote document hash changed: {raw_path}")
    return raw


def quote_snapshot_from_historical_close_manifest(
    manifest_path: Path,
    root: Path,
    *,
    expected_sha256: str | None = None,
) -> QuoteSnapshot:
    """Restore a verified QuoteSnapshot from a retained dual-source manifest."""
    manifest_path = manifest_path.resolve()
    root = root.resolve()
    if not manifest_path.is_relative_to(root):
        raise ValueError("Historical close manifest escapes project root")
    raw = manifest_path.read_bytes()
    if expected_sha256 is not None:
        if hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
            raise ValueError("Historical close manifest hash changed")
    payload: Mapping[str, Any] = json.loads(raw)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported historical close manifest schema")
    if payload.get("action") != "no_order":
        raise ValueError("Historical close manifest must remain no_order")
    symbol = str(payload.get("symbol") or "")
    target_date = date.fromisoformat(str(payload.get("quote_date")))

    tencent_payload = payload["provider_documents"]["tencent"]
    sohu_payload = payload["provider_documents"]["sohu"]
    calendar_payload = payload["provider_documents"]["szse_calendar"]
    tencent_raw = _document(
        root / tencent_payload["path"],
        str(tencent_payload["sha256"]),
    )
    sohu_raw = _document(
        root / sohu_payload["path"],
        str(sohu_payload["sha256"]),
    )
    calendar_raw = _document(
        root / calendar_payload["path"],
        str(calendar_payload["sha256"]),
    )

    tencent = tencent_daily_bar(tencent_raw, symbol, target_date)
    sohu = sohu_daily_bar(sohu_raw, symbol, target_date)
    calendar = szse_calendar_day(calendar_raw, target_date)
    tencent_close = Decimal(tencent["close"])
    sohu_close = Decimal(sohu["close"])
    if abs(tencent_close - sohu_close) > TOLERANCE:
        raise ValueError(
            "Tencent and Sohu historical closes differ by more than "
            f"{TOLERANCE}"
        )
    if tencent_close != Decimal(str(payload.get("verified_close"))):
        raise ValueError("Verified close does not match the retained Tencent bar")

    manifest_rel = manifest_path.relative_to(root).as_posix()
    evidence_refs: list[dict[str, Any]] = [
        {
            "id": f"m1_{symbol}_{target_date.isoformat()}_historical_close",
            "kind": "m1_dual_source_historical_close",
            "path": manifest_rel,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "tencent_close": tencent["close"],
            "sohu_close": sohu["close"],
            "venue_session": calendar["target_date"],
        }
    ]
    for provider, payload_item in (
        ("tencent", tencent_payload),
        ("sohu", sohu_payload),
        ("szse_calendar", calendar_payload),
    ):
        evidence_refs.append(
            {
                "id": f"m1_{symbol}_{target_date.isoformat()}_{provider}",
                "kind": "quote_provider_document",
                "provider": provider,
                "path": str(payload_item["path"]),
                "sha256": str(payload_item["sha256"]),
                "source_url": str(payload_item["source_url"]),
                "fetched_at": str(payload_item["fetched_at"]),
            }
        )
    return QuoteSnapshot(
        symbol=symbol,
        quote_date=target_date,
        current_price=tencent_close,
        status=QUOTE_STATUS_VERIFIED_CLOSE,
        evidence_refs=evidence_refs,
        blockers=[],
    )
