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
    parser_version = "akshare-financial-v4-sina-distinct-indicator-scopes"
    _fields = {
        "eps_reported": ("摊薄每股收益(元)", "CNY/share"),
        "bvps": ("每股净资产_调整前(元)", "CNY/share"),
        "roe_simple": ("净资产收益率(%)", "percent"),
        # This is the direct counterpart to the statutory annual-report
        # "weighted average ROE" label. Keep it separate from simple ROE.
        "roe_weighted": ("加权净资产收益率(%)", "percent"),
        "gross_margin": ("销售毛利率(%)", "percent"),
        "provider_sales_net_margin": ("销售净利率(%)", "percent"),
        "main_business_revenue_yoy": ("主营业务收入增长率(%)", "percent"),
        "provider_net_income_yoy": ("净利润增长率(%)", "percent"),
        "debt_ratio": ("资产负债率(%)", "percent"),
        "provider_cashflow_profit_ratio": ("经营现金净流量与净利润的比率(%)", "percent"),
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
            latest_row = frame.loc[frame["_report_at"].idxmax()]
            latest_report_at = latest_row["_report_at"].replace(tzinfo=timezone.utc)
            annual_rows = frame.loc[
                (frame["_report_at"].dt.month == 12) & (frame["_report_at"].dt.day == 31)
            ]
            selected_rows = [latest_row]
            if not annual_rows.empty:
                latest_annual = annual_rows.loc[annual_rows["_report_at"].idxmax()]
                if latest_annual["_report_at"] != latest_row["_report_at"]:
                    selected_rows.append(latest_annual)
            for row in selected_rows:
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
                            point_metadata={
                                'source_line_item': column_name,
                                'point_parser_version': self.parser_version,
                                **({'roe_scope': 'simple'} if field_name == 'roe_simple' else
                                   {'roe_scope': 'weighted_average'} if field_name == 'roe_weighted' else {}),
                            },
                        )
                    )
            # Interim EPS is cumulative. Only emit a true rolling-12-month
            # EPS when the prior annual and matching interim values exist.
            eps_column = self._fields["eps_reported"][0]
            previous_annual = frame.loc[
                (frame["_report_at"].dt.year == latest_report_at.year - 1)
                & (frame["_report_at"].dt.month == 12)
                & (frame["_report_at"].dt.day == 31)
            ]
            previous_matching = frame.loc[
                (frame["_report_at"].dt.year == latest_report_at.year - 1)
                & (frame["_report_at"].dt.month == latest_report_at.month)
                & (frame["_report_at"].dt.day == latest_report_at.day)
            ]
            if not previous_annual.empty and not previous_matching.empty:
                try:
                    ttm_eps = Decimal(str(latest_row[eps_column])) + Decimal(str(previous_annual.iloc[0][eps_column])) - Decimal(str(previous_matching.iloc[0][eps_column]))
                except Exception:
                    ttm_eps = None
                if ttm_eps is not None and ttm_eps > 0:
                    records.append(
                        SourceRecord(
                            symbol=symbol,
                            field_name="eps_ttm",
                            period_label=latest_report_at.strftime("%Y-%m-%d"),
                            value=ttm_eps,
                            unit="CNY/share",
                            source_name=self.source_name,
                            source_url=source_url,
                            published_at=None,
                            fetched_at=fetched_at,
                            parser_version="akshare-financial-v1-sina-ttm",
                            raw_payload=raw,
                            point_metadata={
                                "formula": "current interim EPS + prior annual EPS - prior matching interim EPS",
                                "current_period": latest_report_at.strftime("%Y-%m-%d"),
                            },
                        )
                    )
        missing = set(symbols) - {record.symbol for record in records}
        if missing:
            raise RuntimeError(f"Financial response incomplete: {', '.join(sorted(missing))}")
        return records


class AkshareFinancialAbstractAdapter:
    """Fetch supplemental financial-statement line items from the Sina abstract feed."""

    source_name = "AkShare / Sina financial abstract"
    parser_version = "akshare-financial-v3-sina-abstract-revenue-scope"
    _fields = {
        "total_revenue": ("\u8425\u4e1a\u603b\u6536\u5165", "CNY", None),
        "net_income": ("\u5f52\u6bcd\u51c0\u5229\u6da6", "CNY", None),
        "operating_cash_flow": ("\u7ecf\u8425\u73b0\u91d1\u6d41\u91cf\u51c0\u989d", "CNY", None),
        "fcf_per_share": ("\u6bcf\u80a1\u4f01\u4e1a\u81ea\u7531\u73b0\u91d1\u6d41\u91cf", "CNY/share", None),
        "roic": ("\u6295\u5165\u8d44\u672c\u56de\u62a5\u7387", "percent", None),
        "cash": ("\u8d27\u5e01\u8d44\u91d1", "CNY", None),
    }

    def fetch(self, symbols: list[str], *, report_period: str | None = None) -> list[SourceRecord]:
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
            if report_period is not None:
                requested = datetime.strptime(report_period, '%Y-%m-%d').strftime('%Y%m%d')
                if requested not in period_columns:
                    raise RuntimeError(f'Financial abstract missing requested period: {symbol} {report_period}')
                period = requested
            else:
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
            revenue = metrics.get("\u8425\u4e1a\u6536\u5165")
            operating_cost = metrics.get("\u8425\u4e1a\u6210\u672c")
            if revenue is not None and operating_cost is not None:
                try:
                    revenue_value = Decimal(str(revenue))
                    cost_value = Decimal(str(operating_cost))
                    gross_margin = (revenue_value - cost_value) / revenue_value * Decimal("100")
                except Exception:
                    gross_margin = None
                if gross_margin is not None and revenue_value > 0:
                    records.append(
                        SourceRecord(
                            symbol=symbol,
                            field_name="gross_margin",
                            period_label=report_at.strftime("%Y-%m-%d"),
                            value=gross_margin,
                            unit="percent",
                            source_name=self.source_name,
                            source_url=source_url,
                            published_at=None,
                            fetched_at=fetched_at,
                            parser_version="akshare-financial-v2-sina-abstract-derived",
                            raw_payload=raw,
                            point_metadata={"formula": "(revenue - operating_cost) / revenue"},
                        )
                    )
            debt_items = ("\u77ed\u671f\u501f\u6b3e", "\u4e00\u5e74\u5185\u5230\u671f\u7684\u975e\u6d41\u52a8\u8d1f\u503a", "\u957f\u671f\u501f\u6b3e", "\u5e94\u4ed8\u503a\u5238")
            debt_values: list[Decimal] = []
            for item in debt_items:
                value = metrics.get(item)
                if value is None:
                    continue
                try:
                    debt_values.append(Decimal(str(value)))
                except Exception:
                    continue
            if debt_values:
                records.append(
                    SourceRecord(
                        symbol=symbol,
                        field_name="interest_bearing_debt",
                        period_label=report_at.strftime("%Y-%m-%d"),
                        value=sum(debt_values),
                        unit="CNY",
                        source_name=self.source_name,
                        source_url=source_url,
                        published_at=None,
                        fetched_at=fetched_at,
                        parser_version="akshare-financial-v2-sina-abstract-derived",
                        raw_payload=raw,
                        point_metadata={"formula": "short-term borrowings + current maturities + long-term borrowings + bonds payable"},
                    )
                )
        missing = set(symbols) - {record.symbol for record in records}
        if missing:
            raise RuntimeError(f"Financial abstract response incomplete: {', '.join(sorted(missing))}")
        return records


class SinaFinancialStatementsAdapter:
    """Read selected line items from the provider's detailed financial statements.

    The detailed sheets expose balance-sheet and cash-flow fields omitted from
    the summary feed.  They remain supplemental until a reviewer matches them
    to the archived statutory filing.
    """

    source_name = "AkShare / Sina detailed financial statements"
    parser_version = "akshare-financial-v5-sina-statements-single-cash"
    _exact_balance_items = {
        "cash": "货币资金", "short_term_borrowings": "短期借款",
        "current_portion_long_term_debt": "一年内到期的非流动负债",
        "long_term_borrowings": "长期借款", "bonds_payable": "应付债券",
        "lease_liabilities_noncurrent": "租赁负债",
        "long_term_payables_excluding_special": "长期应付款",
        "special_payables_noncurrent": "专项应付款",
        "total_assets": "资产总计", "total_liabilities": "负债合计",
    }
    _exact_cashflow_items = {"operating_cash_flow": "经营活动产生的现金流量净额"}

    @classmethod
    def _payables_components(cls, row):
        components = {field: cls._value(row, cls._exact_balance_items[field]) for field in
                      ('long_term_payables_excluding_special', 'special_payables_noncurrent')}
        if any(value is None or not value.is_finite() or value < 0 for value in components.values()):
            return None
        return components
    _exact_income_items = {"operating_cost": "营业成本", "revenue": "营业收入",
                           "net_income": "归属于母公司所有者的净利润"}
    _bank_symbols = {"600036", "601288"}
    _debt_fields = ("短期借款", "一年内到期的非流动负债", "长期借款", "应付债券")
    _bank_cash_fields = ("现金及存放中央银行款项", "货币资金")
    _bank_debt_fields = ("向中央银行借款", "同业存入及拆入", "客户存款(吸收存款)", "应付债券", "卖出回购金融资产款")
    _capex_fields = (
        "购建固定资产、无形资产和其他长期资产所支付的现金",
        "购建固定资产、无形资产和其他长期资产支付的现金",
    )

    @staticmethod
    def _value(row, names: tuple[str, ...] | str) -> Decimal | None:
        if isinstance(names, str):
            names = (names,)
        for name in names:
            value = row.get(name)
            if value is None or (isinstance(value, float) and math.isnan(value)):
                continue
            try:
                return Decimal(str(value))
            except Exception:
                continue
        return None

    @staticmethod
    def _report_date(row) -> datetime | None:
        value = row.get("报告日")
        if value is None:
            return None
        text = str(value).strip()
        try:
            return datetime.strptime(text[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def _published_at(row) -> datetime | None:
        value = row.get("公告日期")
        if value is None:
            return None
        text = str(value).strip()
        try:
            return datetime.strptime(text[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    def fetch(self, symbols: list[str], *, report_period: str | None = None) -> list[SourceRecord]:
        try:
            import akshare as ak
        except ImportError as error:
            raise RuntimeError("AkShare is not installed") from error

        fetched_at = datetime.now(timezone.utc)
        records: list[SourceRecord] = []
        for symbol in symbols:
            stock = ("sh" if symbol.startswith("6") else "sz") + symbol
            try:
                balance = ak.stock_financial_report_sina(stock=stock, symbol="资产负债表")
                cashflow = ak.stock_financial_report_sina(stock=stock, symbol="现金流量表")
                income = ak.stock_financial_report_sina(stock=stock, symbol="利润表")
            except Exception:
                if report_period is not None:
                    raise
                # This is a supplemental source. A temporary provider failure
                # must not discard the core price/indicator update.
                continue
            if balance.empty or cashflow.empty:
                if report_period is not None:
                    raise RuntimeError(f'Financial statements missing requested period: {symbol} {report_period}')
                continue
            balance_row = balance.iloc[0]
            if report_period is not None:
                requested = datetime.strptime(report_period, '%Y-%m-%d').date()
                balance_row = next((row for _, row in balance.iterrows()
                                    if (at := self._report_date(row)) and at.date() == requested), None)
                if balance_row is None:
                    raise RuntimeError(f'Financial statements missing requested period: {symbol} {report_period}')
            report_at = self._report_date(balance_row)
            if report_at is None:
                continue
            cashflow_row = next(
                (row for _, row in cashflow.iterrows() if self._report_date(row) == report_at),
                None,
            )
            income_row = next(
                (row for _, row in income.iterrows() if self._report_date(row) == report_at),
                None,
            )
            raw = json.dumps(
                {
                    "code": symbol,
                    "report_date": report_at.strftime("%Y-%m-%d"),
                    "balance": balance_row.to_dict(),
                    "cashflow": cashflow_row.to_dict() if cashflow_row is not None else None,
                    "income": income_row.to_dict() if income_row is not None else None,
                },
                ensure_ascii=False,
                default=str,
            ).encode()
            source_url = (
                "https://vip.stock.finance.sina.com.cn/corp/go.php/"
                f"vFD_FinanceSummary/stockid/{symbol}/displaytype/4.phtml?source=fzb"
            )
            common = {
                "symbol": symbol,
                "period_label": report_at.strftime("%Y-%m-%d"),
                "source_name": self.source_name,
                "source_url": source_url,
                "published_at": self._published_at(balance_row),
                "fetched_at": fetched_at,
                "parser_version": self.parser_version,
                "raw_payload": raw,
            }
            # Retain exact CNY line items only from explicitly consolidated sheets.
            # They are suitable for unattended comparison with the same official-PDF labels.
            annual_rows = [row for _, row in balance.iterrows()
                           if (date := self._report_date(row)) and date.month == 12 and date.day == 31]
            selected_balance_rows = [balance_row]
            if annual_rows and report_period is None:
                annual_row = max(annual_rows, key=lambda row: self._report_date(row))
                if self._report_date(annual_row) != report_at:
                    selected_balance_rows.append(annual_row)
            for selected_balance in selected_balance_rows:
                selected_at = self._report_date(selected_balance)
                statement_type = str(selected_balance.get("类型", "")).strip()
                # Sina omits the type column for some otherwise usable report
                # payloads.  Only reject a row when it explicitly identifies
                # itself as non-consolidated; records without that metadata are
                # still subject to official-source verification downstream.
                if selected_at is None or (statement_type and "合并" not in statement_type):
                    continue
                selected_cashflow = next((row for _, row in cashflow.iterrows() if self._report_date(row) == selected_at), None)
                selected_income = next((row for _, row in income.iterrows() if self._report_date(row) == selected_at), None)
                selected_raw = json.dumps({"code": symbol, "report_date": selected_at.strftime("%Y-%m-%d"),
                                           "balance": selected_balance.to_dict(),
                                           "cashflow": selected_cashflow.to_dict() if selected_cashflow is not None else None,
                                           "income": selected_income.to_dict() if selected_income is not None else None},
                                          ensure_ascii=False, default=str).encode()
                line_common = {**common, "period_label": selected_at.strftime("%Y-%m-%d"),
                               "published_at": self._published_at(selected_balance), "raw_payload": selected_raw}
                statement_scope = "consolidated" if "合并" in statement_type else "unspecified"
                for field_name, label in self._exact_balance_items.items():
                    value = self._value(selected_balance, label)
                    if value is not None:
                        records.append(SourceRecord(field_name=field_name, value=value, unit="CNY",
                                                    point_metadata={"source_line_item": label, "statement_scope": statement_scope}, **line_common))
                payables = self._payables_components(selected_balance)
                if payables is not None:
                    records.append(SourceRecord(field_name='long_term_payables_noncurrent',
                        value=sum(payables.values()), unit='CNY', point_metadata={
                            'statement_scope': statement_scope,
                            'derivation_formula': 'long_term_payables_excluding_special + special_payables_noncurrent',
                            'source_components': {name: str(value) for name, value in payables.items()},
                            'components_same_raw_snapshot': True,
                            'financing_classification': 'not_assessed',
                        }, **line_common))
                if selected_cashflow is not None:
                    for field_name, label in self._exact_cashflow_items.items():
                        value = self._value(selected_cashflow, label)
                        if value is not None:
                            records.append(SourceRecord(field_name=field_name, value=value, unit="CNY",
                                                    point_metadata={"source_line_item": label, "statement_scope": statement_scope}, **line_common))
                if selected_income is not None:
                    income_type = str(selected_income.get('类型', '')).strip()
                    income_scope = 'consolidated' if '合并' in income_type else 'unspecified'
                    for field_name, label in self._exact_income_items.items():
                        if income_type and '合并' not in income_type:
                            continue
                        value = self._value(selected_income, label)
                        if value is not None:
                            records.append(SourceRecord(field_name=field_name, value=value, unit="CNY",
                                                        point_metadata={"source_line_item": label, "statement_scope": income_scope}, **line_common))
            bank = symbol in self._bank_symbols
            cash = self._value(balance_row, self._bank_cash_fields if bank else "货币资金")
            exact_cash_present = not bank and any(
                record.symbol == symbol and record.field_name == 'cash'
                and record.period_label == common['period_label'] and record.unit == 'CNY'
                and record.value == cash and record.raw_payload == raw
                for record in records)
            if cash is not None and not exact_cash_present:
                metadata = {"source_line_item": "现金及存放中央银行款项"} if bank else None
                records.append(SourceRecord(field_name="cash", value=cash / Decimal("100000000"), unit="CNY 100M", point_metadata=metadata, **common))
            debt_fields = self._bank_debt_fields if bank else self._debt_fields
            debt_values = [self._value(balance_row, field) for field in debt_fields]
            debt_values = [value for value in debt_values if value is not None]
            if debt_values:
                formula = (
                    "central bank borrowings + interbank deposits/borrowings + customer deposits + bonds payable + repurchase obligations"
                    if bank else "short-term borrowings + current maturities + long-term borrowings + bonds payable"
                )
                records.append(
                    SourceRecord(
                        field_name="interest_bearing_debt",
                        value=sum(debt_values) / Decimal("100000000"),
                        unit="CNY 100M",
                        point_metadata={"formula": formula},
                        **common,
                    )
                )
            if cashflow_row is None:
                continue
            operating_cashflow = self._value(cashflow_row, "经营活动产生的现金流量净额")
            capex = self._value(cashflow_row, self._capex_fields)
            if not bank and operating_cashflow is not None and capex is not None:
                records.append(
                    SourceRecord(
                        field_name="free_cash_flow",
                        value=(operating_cashflow - abs(capex)) / Decimal("100000000"),
                        unit="CNY 100M",
                        point_metadata={"formula": "operating cash flow - capital expenditure"},
                        **common,
                    )
                )
        return records
