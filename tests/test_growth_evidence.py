from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from value_investment_agent.models import SourceRecord
from value_investment_agent.growth_evidence import build_growth_evidence
from value_investment_agent.growth_evidence import validate_retained_growth
from value_investment_agent.evidence_dependencies import affected_point_ids


def inputs():
    current = SourceRecord('000333','revenue','2025-12-31',Decimal(120),'CNY',
        'AkShare / Sina detailed financial statements','https://example.org/report',None,
        datetime.now(timezone.utc),'test',b'current')
    return current,replace(current,period_label='2024-12-31',value=Decimal(100),raw_payload=b'previous')


def test_growth_retains_both_inputs_without_verification_flag():
    record = build_growth_evidence(*inputs(),'current','previous')
    assert record.value == 20 and record.field_name == 'revenue_yoy'
    assert record.point_metadata['input_data_point_ids'] == ['current','previous']
    assert not record.point_metadata.get('automatic_cross_source_verification')
    assert all(len(p['sha256']) == 64 for p in record.point_metadata['growth_inputs'])


@pytest.mark.parametrize('change',[
    {'period_label':'2023-12-31'}, {'symbol':'600519'}, {'unit':'CNY 100M'},
    {'field_name':'total_revenue'}, {'source_name':'AkShare / Sina financial abstract'},
    {'value':Decimal(0)}, {'value':Decimal('-1')}, {'value':Decimal('NaN')},
    {'point_metadata':{'evidence_quarantine':{'reason':'test'}}},
])
def test_growth_rejects_ambiguous_or_invalid_inputs(change):
    current,previous = inputs()
    with pytest.raises(ValueError):
        build_growth_evidence(current,replace(previous,**change),'current','previous')


def test_quarantine_propagates_from_either_growth_input():
    def point(id, metadata):
        return dict(data_point_id=id,source_id=id,symbol='000333',period_label='2025-12-31',
                    field_name='revenue',metadata=metadata)
    rows = [point('prior',{}),point('growth',{'input_data_point_ids':['current','prior']}),
            point('official',{'secondary_data_point_id':'growth'})]
    assert affected_point_ids(rows,['prior']) == {'prior','growth','official'}


def test_retained_growth_revalidates_both_live_inputs():
    record = build_growth_evidence(*inputs(),'current','previous')
    metadata = record.point_metadata
    rows = [dict(item,validation_status='pending',metadata={}) for item in metadata['growth_inputs']]
    def valid():
        return validate_retained_growth(metadata,rows,'000333','2025-12-31','revenue_yoy',record.value)
    assert valid()
    for key,bad in [('value','99'),('sha256','bad'),('validation_status','failed'),
                    ('validation_status','conflict'),('period_label','2023-12-31'),
                    ('metadata',{'evidence_quarantine':{'reason':'test'}})]:
        original = rows[1][key]
        rows[1][key] = bad
        assert not valid(), key
        rows[1][key] = original
    assert not validate_retained_growth(metadata,rows[:1],'000333','2025-12-31','revenue_yoy',record.value)
@pytest.mark.parametrize('period,excerpt,expected', [
    ('2025-12-31', '2025 年 2024 年 本年比上年增减\n营业收入 120 100 20%', True),
    ('2025-12-31', '2024 年 2023 年 本年比上年增减', False),
    ('2025-06-30', '2025 年 2024 年 本年比上年增减', False),
    ('2025-12-31', '2025 年 2023 年 本年比上年增减', False),
    ('2025-12-31', '营业收入 120 100 20%', False),
    ('2025-12-31', None, False),
    ('2025-12-31', '2025 年 2024 年 本年比上年增减 调整后', False),
    ('2025-12-31', '2025 年 2024 年 本年比上年增减\n2024 年 2023 年 本年比上年增减', False),
])
def test_official_growth_period_binding(period, excerpt, expected):
    from value_investment_agent.growth_evidence import official_growth_period_matches
    assert official_growth_period_matches(excerpt, period) is expected
