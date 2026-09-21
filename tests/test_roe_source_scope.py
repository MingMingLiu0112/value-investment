from value_investment_agent.adapters import SinaFinancialAdapter
from value_investment_agent.candidate_review import AUTOMATIC_FIELD_MAP
from value_investment_agent.financial_quality import GENERAL_FIELDS
from decimal import Decimal
import sys
from types import SimpleNamespace
import pandas as pd


def test_simple_and_weighted_roe_cannot_share_storage_key():
    fields = SinaFinancialAdapter._fields
    assert 'roe' not in fields
    assert fields['roe_simple'][0] != fields['roe_weighted'][0]
    assert AUTOMATIC_FIELD_MAP['roe'] == 'roe_weighted'


def test_simple_roe_is_not_a_scoring_requirement():
    assert 'roe_simple' not in GENERAL_FIELDS
    assert 'roe' in GENERAL_FIELDS


def test_fetch_retains_distinct_values_and_point_provenance(monkeypatch):
    fields = SinaFinancialAdapter._fields
    frame = pd.DataFrame([{'日期': '2025-12-31',
        fields['roe_simple'][0]: '7.73', fields['roe_weighted'][0]: '8.4'}])
    monkeypatch.setitem(sys.modules, 'akshare', SimpleNamespace(
        stock_financial_analysis_indicator=lambda **kwargs: frame.copy()))
    records = {r.field_name: r for r in SinaFinancialAdapter().fetch(['000001'])}
    assert set(records) == {'roe_simple', 'roe_weighted'}
    assert records['roe_simple'].value == Decimal('7.73')
    assert records['roe_weighted'].value == Decimal('8.4')
    for field, scope in [('roe_simple', 'simple'), ('roe_weighted', 'weighted_average')]:
        record = records[field]
        assert record.point_metadata['source_line_item'] == fields[field][0]
        assert record.point_metadata['point_parser_version'] == record.parser_version
        assert record.point_metadata['roe_scope'] == scope
        assert record.period_label == '2025-12-31'
