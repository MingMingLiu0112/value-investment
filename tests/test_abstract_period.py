import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from value_investment_agent.adapters import AkshareFinancialAbstractAdapter


def test_requested_annual_period_not_replaced_by_latest_interim(monkeypatch):
    frame = pd.DataFrame([
        ['summary', '\u8425\u4e1a\u603b\u6536\u5165', 123, 456],
        ['summary', '\u5f52\u6bcd\u51c0\u5229\u6da6', 12, 45],
    ], columns=['type','metric','20260630','20251231'])
    monkeypatch.setitem(sys.modules, 'akshare', SimpleNamespace(stock_financial_abstract=lambda **_: frame))
    adapter = AkshareFinancialAbstractAdapter()
    records = adapter.fetch(['000333'], report_period='2025-12-31')
    assert {r.period_label for r in records} == {'2025-12-31'}
    assert next(r.value for r in records if r.field_name == 'total_revenue') == 456
    assert not any(r.field_name == 'revenue' for r in records)
    assert b'20251231' in records[0].raw_payload
    latest = adapter.fetch(['000333'])
    assert {r.period_label for r in latest} == {'2026-06-30'}
    with pytest.raises(RuntimeError, match='missing requested period'):
        adapter.fetch(['000333'], report_period='2024-12-31')


def test_detailed_statements_select_only_requested_prior_year(monkeypatch):
    from value_investment_agent.adapters import SinaFinancialStatementsAdapter
    dates = ['20260630','20251231','20241231']
    frames = {
        '资产负债表': pd.DataFrame([{'报告日':d,'货币资金':100,'类型':'合并'} for d in dates]),
        '现金流量表': pd.DataFrame([{'报告日':d,'经营活动产生的现金流量净额':10} for d in dates]),
        '利润表': pd.DataFrame([{'报告日':d,'营业收入':v,'营业成本':1}
                            for d,v in zip(dates,[60,120,100])]),
    }
    monkeypatch.setitem(sys.modules,'akshare',SimpleNamespace(
        stock_financial_report_sina=lambda stock,symbol: frames[symbol]))
    adapter = SinaFinancialStatementsAdapter()
    records = adapter.fetch(['000333'],report_period='2024-12-31')
    assert records
    assert {r.period_label for r in records} == {'2024-12-31'}
    assert next(r.value for r in records if r.field_name == 'revenue') == 100
    with pytest.raises(RuntimeError,match='missing requested period'):
        adapter.fetch(['000333'],report_period='2023-12-31')


@pytest.mark.parametrize('income_type,has_attributable,expected', [
    ('合并期末', True, 12), ('母公司期末', True, None), ('合并期末', False, None)])
def test_detailed_income_uses_only_attributable_profit(monkeypatch, income_type, has_attributable, expected):
    from value_investment_agent.adapters import SinaFinancialStatementsAdapter
    income = {'报告日': '20260630', '类型': income_type, '净利润': 99}
    if has_attributable:
        income['归属于母公司所有者的净利润'] = 12
    frames = {
        '资产负债表': pd.DataFrame([{'报告日': '20260630', '类型': '合并期末', '货币资金': 100}]),
        '现金流量表': pd.DataFrame([{'报告日': '20260630', '经营活动产生的现金流量净额': 10}]),
        '利润表': pd.DataFrame([income]),
    }
    monkeypatch.setitem(sys.modules, 'akshare', SimpleNamespace(
        stock_financial_report_sina=lambda stock, symbol: frames[symbol]))
    rows = [r for r in SinaFinancialStatementsAdapter().fetch(['000027']) if r.field_name == 'net_income']
    assert [r.value for r in rows] == ([] if expected is None else [expected])
    if rows:
        assert rows[0].point_metadata['statement_scope'] == 'consolidated'
        assert '归属于母公司所有者的净利润' in rows[0].raw_payload.decode()
