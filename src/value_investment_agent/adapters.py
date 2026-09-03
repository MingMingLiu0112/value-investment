from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from decimal import Decimal

from .models import SourceRecord


class AksharePriceAdapter:
    """Fetch only tracked symbols, avoiding the provider's full-market endpoint."""

    source_name = "AkShare / Sina public historical quotes"
    source_url = "https://akshare.akfamily.xyz/data/stock/stock.html"
    parser_version = "akshare-price-v3-sina-history"

    def fetch(self, symbols: list[str]) -> list[SourceRecord]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error

        fetched_at = datetime.now(timezone.utc)
        records: list[SourceRecord] = []
        for symbol in symbols:
            exchange_symbol = ("sh" if symbol.startswith("6") else "sz") + symbol
            frame = ak.stock_zh_a_daily(symbol=exchange_symbol, adjust="")
            if frame.empty or "close" not in frame.columns:
                continue
            row = frame.iloc[-1]
            value = row["close"]
            if value is None or str(value).strip() in {"-", "nan"}:
                continue
            raw = json.dumps({"code": symbol, "price": str(value), "row": row.to_dict()}, ensure_ascii=False, default=str).encode()
            records.append(SourceRecord(symbol=symbol, field_name="current_price", period_label=fetched_at.strftime("%Y-%m-%d %H:%M"), value=Decimal(str(value)), unit="CNY/share", source_name=self.source_name, source_url=self.source_url, published_at=None, fetched_at=fetched_at, parser_version=self.parser_version, raw_payload=raw))
        missing = set(symbols) - {record.symbol for record in records}
        if missing:
            raise RuntimeError(f"Price response incomplete: {', '.join(sorted(missing))}")
        return records


class SinaFinancialAdapter:
    """Fetch audited-style financial indicators as supplemental, review-required data."""

    source_name = "AkShare / Sina financial indicators"
    parser_version = "akshare-financial-v1-sina"
    _fields = {
        "eps_ttm": ("摊薄每股收益(元)", "CNY/share"),
        "bvps": ("每股净资产_调整前(元)", "CNY/share"),
        "roe": ("净资产收益率(%)", "percent"),
        "gross_margin": ("销售毛利率(%)", "percent"),
        "net_margin": ("销售净利率(%)", "percent"),
        "revenue_yoy": ("主营业务收入增长率(%)", "percent"),
        "net_income_yoy": ("净利润增长率(%)", "percent"),
        "debt_ratio": ("资产负债率(%)", "percent"),
        "operating_cash_flow_to_net_income": ("经营现金净流量与净利润的比率(%)", "percent"),
    }

    def fetch(self, symbols: list[str]) -> list[SourceRecord]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error

        fetched_at = datetime.now(timezone.utc)
        records: list[SourceRecord] = []
        for symbol in symbols:
            frame = ak.stock_financial_analysis_indicator(symbol=symbol, start_year="2024")
            if frame.empty or "日期" not in frame.columns:
                raise RuntimeError(f"Financial response incomplete: {symbol}")
            frame["_report_at"] = frame["日期"].map(lambda value: datetime.fromisoformat(str(value)))
            row = frame.loc[frame["_report_at"].idxmax()]
            report_at = row["_report_at"].replace(tzinfo=timezone.utc)
            raw = json.dumps(
                {"code": symbol, "report_date": str(row["日期"]), "row": row.to_dict()},
                ensure_ascii=False,
                default=str,
            ).encode()
            source_url = (
                "https://money.finance.sina.com.cn/corp/go.php/"
                f"vFD_FinancialGuideLine/stockid/{symbol}/ctrl/{report_at.year}/displaytype/4.phtml"
            )
            for field_name, (column_name, unit) in self._fields.items():
                value = row.get(column_name)
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    continue
                try:
                    decimal_value = Decimal(str(value))
                except Exception:
                    continue
                records.append(
                    SourceRecord(
                        symbol=symbol,
                        field_name=field_name,
                        period_label=report_at.strftime("%Y-%m-%d"),
                        value=decimal_value,
                        unit=unit,
                        source_name=self.source_name,
                        source_url=source_url,
                        # The provider exposes the report period, not a verified disclosure timestamp.
                        published_at=None,
                        fetched_at=fetched_at,
                        parser_version=self.parser_version,
                        raw_payload=raw,
                    )
                )
        missing = set(symbols) - {record.symbol for record in records}
        if missing:
            raise RuntimeError(f"Financial response incomplete: {', '.join(sorted(missing))}")
        return records


class AkshareFinancialAbstractAdapter:
    """Fetch supplemental financial-statement line items from the Sina abstract feed."""

    source_name = "AkShare / Sina financial abstract"
    parser_version = "akshare-financial-v2-sina-abstract"
    _fields = {
        "revenue": ("\u8425\u4e1a\u603b\u6536\u5165", "CNY 100M", Decimal("100000000")),
        "net_income": ("\u5f52\u6bcd\u51c0\u5229\u6da6", "CNY 100M", Decimal("100000000")),
        "operating_cash_flow": ("\u7ecf\u8425\u73b0\u91d1\u6d41\u91cf\u51c0\u989d", "CNY 100M", Decimal("100000000")),
        "fcf_per_share": ("\u6bcf\u80a1\u4f01\u4e1a\u81ea\u7531\u73b0\u91d1\u6d41\u91cf", "CNY/share", None),
        "roic": ("\u6295\u5165\u8d44\u672c\u56de\u62a5\u7387", "percent", None),
    }

    def fetch(self, symbols: list[str]) -> list[SourceRecord]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error

        fetched_at = datetime.now(timezone.utc)
        records: list[SourceRecord] = []
        for symbol in symbols:
            frame = ak.stock_financial_abstract(symbol=symbol)
            if frame.empty or len(frame.columns) < 3:
                raise RuntimeError(f"Financial abstract response incomplete: {symbol}")
            period_columns = [str(column) for column in frame.columns[2:] if str(column).isdigit()]
            if not period_columns:
                raise RuntimeError(f"Financial abstract has no report period: {symbol}")
            period = max(period_columns)
            metrics = {
                str(row.iloc[1]): row[period]
                for _, row in frame.iterrows()
                if len(row) > 1
            }
            raw = json.dumps(
                {"code": symbol, "report_date": period, "metrics": metrics},
                ensure_ascii=False,
                default=str,
            ).encode()
            report_at = datetime.strptime(period, "%Y%m%d").replace(tzinfo=timezone.utc)
            source_url = (
                "https://vip.stock.finance.sina.com.cn/corp/go.php/"
                f"vFD_FinancialGuideLine/stockid/{symbol}/ctrl/{report_at.year}/displaytype/4.phtml"
            )
            for field_name, (metric_name, unit, divisor) in self._fields.items():
                value = metrics.get(metric_name)
                if value is None or (isinstance(value, float) and math.isnan(value)):
                    continue
                try:
                    decimal_value = Decimal(str(value))
                except Exception:
                    continue
                if divisor:
                    decimal_value /= divisor
                records.append(
                    SourceRecord(
                        symbol=symbol,
                        field_name=field_name,
                        period_label=report_at.strftime("%Y-%m-%d"),
                        value=decimal_value,
                        unit=unit,
                        source_name=self.source_name,
                        source_url=source_url,
                        published_at=None,
                        fetched_at=fetched_at,
                        parser_version=self.parser_version,
                        raw_payload=raw,
                    )
                )
        missing = set(symbols) - {record.symbol for record in records}
        if missing:
            raise RuntimeError(f"Financial abstract response incomplete: {', '.join(sorted(missing))}")
        return records
