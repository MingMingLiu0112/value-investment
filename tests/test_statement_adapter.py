from __future__ import annotations

import sys
from types import SimpleNamespace

from value_investment_agent.adapters import SinaFinancialStatementsAdapter


class Row(dict):
    def to_dict(self):
        return dict(self)


class ILoc:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, index):
        return self.rows[index]


class Frame:
    empty = False

    def __init__(self, rows):
        self.rows = rows
        self.iloc = ILoc(rows)

    def iterrows(self):
        return enumerate(self.rows)


def test_detailed_statements_supply_cash_debt_and_free_cash_flow(monkeypatch) -> None:
    balance = Frame([
        Row({
            "报告日": "20260630", "公告日期": "20260815", "货币资金": 5_000_000_000,
            "短期借款": 100_000_000, "一年内到期的非流动负债": 200_000_000,
            "长期借款": 300_000_000, "应付债券": 400_000_000,
        })
    ])
    cashflow = Frame([
        Row({
            "报告日": "20260630", "经营活动产生的现金流量净额": 2_000_000_000,
            "购建固定资产、无形资产和其他长期资产所支付的现金": 600_000_000,
        })
    ])

    def report(stock: str, symbol: str):
        return balance if symbol == "资产负债表" else cashflow

    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(stock_financial_report_sina=report))
    records = SinaFinancialStatementsAdapter().fetch(["600519"])
    values = {record.field_name: record.value for record in records}

    assert values["cash"] == 50
    assert values["interest_bearing_debt"] == 10
    assert values["free_cash_flow"] == 14
    assert next(record for record in records if record.field_name == "free_cash_flow").point_metadata == {
        "formula": "operating cash flow - capital expenditure"
    }


def test_bank_uses_liquidity_and_funding_specific_line_items(monkeypatch) -> None:
    balance = Frame([
        Row({
            "报告日": "20260630", "公告日期": "20260815", "现金及存放中央银行款项": 500_000_000,
            "向中央银行借款": 100_000_000, "同业存入及拆入": 200_000_000,
            "客户存款(吸收存款)": 300_000_000, "应付债券": 400_000_000,
            "卖出回购金融资产款": 500_000_000,
        })
    ])
    cashflow = Frame([Row({"报告日": "20260630"})])

    def report(stock: str, symbol: str):
        return balance if symbol == "资产负债表" else cashflow

    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(stock_financial_report_sina=report))
    records = SinaFinancialStatementsAdapter().fetch(["600036"])
    values = {record.field_name: record.value for record in records}

    assert values["cash"] == 5
    assert values["interest_bearing_debt"] == 15
    assert "free_cash_flow" not in values
    assert next(record for record in records if record.field_name == "cash").point_metadata == {
        "source_line_item": "现金及存放中央银行款项"
    }
