from copy import deepcopy
import pytest
from value_investment_agent.evidence_quarantine import quarantine_metadata


def test_quarantine_preserves_original_and_withdraws_verification():
    point = {'validation_status':'verified','metadata':{'automatic_cross_source_verification':True,
             'input_facts':{'revenue':{'value':'123'}}}}
    original = deepcopy(point)
    result = quarantine_metadata(point,'run-1')
    assert point == original
    assert result['automatic_cross_source_verification'] is False
    audit = result['evidence_quarantine']
    assert audit['previous_validation_status'] == 'verified'
    assert audit['previous_metadata'] == original['metadata']
    assert quarantine_metadata({'validation_status':'failed','metadata':result},'run-2') == result


def test_unrelated_quarantine_not_overwritten():
    with pytest.raises(ValueError,match='unrelated'):
        quarantine_metadata({'validation_status':'failed','metadata':{
            'evidence_quarantine':{'reason':'different'}}},'run')


def test_quarantine_overrides_stale_verified_flags_in_all_calculation_gates():
    from value_investment_agent.quality import accepted_verification
    from value_investment_agent.financial_quality import _accepted
    from value_investment_agent.derived_financials import build_verified_derivations
    metadata = {'automatic_cross_source_verification':True,
                'evidence_quarantine':{'reason':'total_revenue_used_as_operating_revenue'}}
    revenue = {'symbol':'000333','field_name':'revenue','value':'100','unit':'CNY',
               'period_label':'2025-12-31','validation_status':'verified','metadata':metadata}
    cost = dict(revenue,field_name='operating_cost',value='60',
                metadata={'automatic_cross_source_verification':True})
    assert not accepted_verification(revenue)
    assert not _accepted(revenue)
    assert build_verified_derivations([revenue,cost],['000333']) == []
