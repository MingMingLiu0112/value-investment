import sys
from types import SimpleNamespace

import pandas as pd

from value_investment_agent.adapters import SinaFinancialStatementsAdapter


def test_cash_keeps_each_report_period_without_display_duplicate(monkeypatch):
    balance = pd.DataFrame([
        {'报告日': '20260630', '类型': '合并报表', '货币资金': 5000000000},
        {'报告日': '20251231', '类型': '合并报表', '货币资金': 4000000000},
    ])
    monkeypatch.setitem(sys.modules, 'akshare', SimpleNamespace(
        stock_financial_report_sina=lambda stock, symbol:
        balance if symbol == '资产负债表' else pd.DataFrame([
            {'报告日': '20260630'}, {'报告日': '20251231'}])))
    records = SinaFinancialStatementsAdapter().fetch(['600519'])
    cash = [r for r in records if r.field_name == 'cash']
    assert len(cash) == 2
    assert {r.period_label: r.value for r in cash} == {
        '2026-06-30': 5000000000, '2025-12-31': 4000000000}
    assert all(r.unit == 'CNY' and r.point_metadata['statement_scope'] == 'consolidated' for r in cash)
