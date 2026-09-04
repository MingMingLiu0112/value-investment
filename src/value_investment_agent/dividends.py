"""CNINFO dividend records and transparent TTM payout calculations."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from .models import SourceRecord


SOURCE_NAME = "CNINFO statutory dividend history"
SOURCE_URL = "https://webapi.cninfo.com.cn/#/company"
PARSER_VERSION = "akshare-dividend-v1-cninfo"


def _decimal(value) -> Decimal | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _datetime(value) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc)
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc)
    text = str(value).strip()
    for pattern in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], pattern).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


class CninfoDividendAdapter:
    """Fetch paid cash dividends directly from CNINFO's statutory history."""

    def fetch(self, symbols: list[str]) -> list[SourceRecord]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error

        fetched_at = datetime.now(timezone.utc)
        cutoff = fetched_at - timedelta(days=365)
        records: list[SourceRecord] = []
        for symbol in symbols:
            try:
                frame = ak.stock_dividend_cninfo(symbol=symbol)
            except Exception:
                continue
            if frame.empty:
                continue
            paid: list[tuple[datetime, Decimal, datetime | None, dict]] = []
            for _, row in frame.iterrows():
                paid_at = _datetime(row.get("派息日"))
                ratio = _decimal(row.get("派息比例"))
                if paid_at is None or ratio is None or not cutoff <= paid_at <= fetched_at:
                    continue
                paid.append((paid_at, ratio / Decimal("10"), _datetime(row.get("实施方案公告日期")), row.to_dict()))
            if not paid:
                continue
            paid.sort(key=lambda item: item[0])
            dps_ttm = sum(item[1] for item in paid).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            raw = json.dumps({"code": symbol, "paid_dividends": [item[3] for item in paid]}, ensure_ascii=False, default=str).encode()
            records.append(
                SourceRecord(
                    symbol=symbol,
                    field_name="dps_ttm",
                    period_label=fetched_at.strftime("%Y-%m-%d"),
                    value=dps_ttm,
                    unit="CNY/share",
                    source_name=SOURCE_NAME,
                    source_url=f"{SOURCE_URL}?companyid={symbol}",
                    published_at=max((item[2] for item in paid if item[2] is not None), default=None),
                    fetched_at=fetched_at,
                    parser_version=PARSER_VERSION,
                    raw_payload=raw,
                    point_metadata={
                        "formula": "sum(cash dividend per 10 shares / 10) for paid dividends in trailing 365 days",
                        "payment_dates": [item[0].strftime("%Y-%m-%d") for item in paid],
                        "event_count": len(paid),
                    },
                )
            )
        return records


def build_payout_ratio_records(points: list[dict], symbols: list[str]) -> list[SourceRecord]:
    """Derive payout ratio only when paid DPS TTM and EPS TTM are both present."""
    latest: dict[str, dict[str, dict]] = {symbol: {} for symbol in symbols}
    for point in points:
        if point["symbol"] in latest:
            latest[point["symbol"]][point["field_name"]] = point
    fetched_at = datetime.now(timezone.utc)
    records: list[SourceRecord] = []
    for symbol, values in latest.items():
        dps = _decimal(values.get("dps_ttm", {}).get("value"))
        eps = _decimal(values.get("eps_ttm", {}).get("value"))
        if dps is None or eps is None or eps <= 0:
            continue
        payout = (dps / eps * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        inputs = {
            "dps_ttm": str(dps), "eps_ttm": str(eps), "formula": "DPS_TTM / EPS_TTM * 100",
            "input_source_ids": {field: str(values[field].get("source_id", "")) for field in ("dps_ttm", "eps_ttm")},
        }
        records.append(
            SourceRecord(
                symbol=symbol,
                field_name="payout_ratio",
                period_label=max(values["dps_ttm"]["period_label"], values["eps_ttm"]["period_label"]),
                value=payout,
                unit="percent",
                source_name="Value Investment Agent payout-ratio calculation",
                source_url="internal://value-investment-agent/payout-ratio-v1",
                published_at=None,
                fetched_at=fetched_at,
                parser_version="payout-ratio-v1",
                raw_payload=json.dumps(inputs, sort_keys=True).encode(),
                point_metadata={"calculation": inputs, "review_required": True},
            )
        )
    return records
