import sys
from types import SimpleNamespace
from decimal import Decimal
import pandas as pd
from value_investment_agent.adapters import SinaFinancialAdapter


def test_ambiguous_provider_indicators_do_not_overwrite_canonical_fields(monkeypatch):
    fields = SinaFinancialAdapter._fields
    raw = {'日期':'2025-12-31'}
    supplemental = ['provider_sales_net_margin','main_business_revenue_yoy',
                    'provider_net_income_yoy','provider_cashflow_profit_ratio']
    for field in supplemental:
        raw[fields[field][0]] = '1.1982'
    monkeypatch.setitem(sys.modules,'akshare',SimpleNamespace(
        stock_financial_analysis_indicator=lambda **kwargs: pd.DataFrame([raw])))
    records = SinaFinancialAdapter().fetch(['000333'])
    assert {r.field_name for r in records} == set(supplemental)
    assert not {'net_margin','revenue_yoy','net_income_yoy','operating_cash_flow_to_net_income'} & set(fields)
    for record in records:
        assert record.value == Decimal('1.1982')
        assert record.unit == 'percent'
        assert record.point_metadata['source_line_item'] == fields[record.field_name][0]
