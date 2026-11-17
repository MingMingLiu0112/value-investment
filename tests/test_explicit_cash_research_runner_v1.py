"""TEST_ONLY inputs; real shared cash compiler/model, never real-source approval."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import json

import pytest

from test_first_research_input_v1 import first,run as compile_test_template,NOW
from test_operating_profit_cash_path_v1 import inputs as cash_inputs
from test_operating_cash_consumption_v1 import no_io_effects
from value_investment_agent.application.research import explicit_cash_research_runner_v1 as mod
from value_investment_agent.domain.valuation.operating_profit_cash_path_v1 import compile_operating_profit_cash_path
from value_investment_agent.valuation_models import residual_income_path_v4 as model


@pytest.fixture
def case(first,cash_inputs):
    root,*_=first
    compile_test_template(first)
    package=json.loads((root/'runtime/compiled/package.json').read_bytes())
    raw=deepcopy(cash_inputs)
    raw['opening_state']['as_of']=package['point_in_time']['valuation_date']
    for i,row in enumerate(raw['annual_rows'],1):
        row.update(period_start=f'{2025+i}-07-01',period_end=f'{2026+i}-06-30',period_basis='ROLLING_FULL_YEAR')
    compiled={name:compile_operating_profit_cash_path(**{**raw,'cost_of_equity':cost})
        for name,cost in [('bear','0.10'),('base','0.09'),('bull','0.08')]}
    refs=[dict(id=s['id'],path=s['local_path'],sha256=s['sha256']) for s in package['sources']]
    return dict(root=root,template_package=package,compiled_scenarios=compiled,
        source_catalog=deepcopy(package['sources']),evidence_refs=refs,
        version_metadata=dict(run_id='TEST_ONLY-quarterly-new',generated_at=NOW.isoformat(),
            rationale='TEST_ONLY explicitly compiled annual hypotheses',countercase='TEST_ONLY funding may fail'),
        assumption_metadata=dict(basis='TEST_ONLY_NOT_ECONOMIC_APPROVAL',rationale='TEST_ONLY explicit inputs',
            confidence='low',sensitivity='high'),now=NOW)


def test_new_descriptor_real_service_and_shared_v4_model_read_only(case,monkeypatch):
    calls=[]
    actual=model.ResidualIncomePathValuationModel.value
    def value(self,facts,research_case):
        calls.append((facts,research_case))
        return actual(self,facts,research_case)
    monkeypatch.setattr(model.ResidualIncomePathValuationModel,'value',value)
    before=deepcopy(case)
    with no_io_effects():result=mod.run_explicit_cash_research(**case)
    assert len(calls)==1 and case==before
    descriptor=result['descriptor']
    assert descriptor.descriptor_version==mod.VERSION
    assert descriptor.research_case.research_version==mod.VERSION
    assert descriptor.run_id!=case['template_package']['run_id']
    assert result['input_descriptor_sha256']==descriptor.input_sha256
    assert len(descriptor.assumptions.assumptions)==23 and len(descriptor.assumption_bindings)==69
    assert sum(len(v['rows']) for v in result['annual_ledgers'].values())==30
    assert result['outcome'].valuation is not None
    assert result['outcome'].valuation.status=='conditional_research_only'
    for name,compiled in case['compiled_scenarios'].items():
        assert descriptor.facts.scenario_inputs[name]==compiled['typed_scenario']
        calculation=model.scenario_calculation(descriptor.facts,compiled['typed_scenario'])
        assert abs(Decimal(calculation['dividend_crosscheck_difference_cny']))<=Decimal('.01')
    for binding in descriptor.assumption_bindings:
        assert list(binding.evidence_refs)==case['evidence_refs']
    assert result['action']=='no_order' and result['formal_eligibility'] is False
    assert result['main_range_adopted'] is False and result['condition_price'] is None
    assert result['personal_quantity'] is None and descriptor.distribution_result is None
    assert descriptor.quote is None and descriptor.valuation_approval is None
    assert result['package']['schema_version']=='m1-valuation-package-v2'
    assert result['package']['dependencies']['model_version']==model.MODEL_VERSION
    assert 'human_research_approval' not in result['package']
    assert 'EXPLICIT_CASH_INPUTS_NOT_ADOPTED_MAIN_RANGE' in descriptor.research_case.blockers


@pytest.mark.parametrize('damage',['roe','retention','missing_year','bool_year','opening_book',
    'opening_shares','opening_date','terminal','missing_scenario','new_identity','future',
    'ref_hash','duplicate_id','source_bytes','source_future'])
def test_mismatched_compilation_or_source_rejected_before_model(case,monkeypatch,damage):
    row=case['compiled_scenarios']['base']
    if damage=='roe':row['rows'][0]['forecast_roe']=Decimal('0.21')
    if damage=='retention':row['rows'][0]['retention']=Decimal('0.1')
    if damage=='missing_year':row['rows'].pop()
    if damage=='bool_year':row['rows'][0]['year']=True
    if damage=='opening_book':row['opening_state']['book_equity_cny']='101'
    if damage=='opening_shares':row['opening_state']['ordinary_shares']='11'
    if damage=='opening_date':row['opening_state']['as_of']='2026-09-30'
    if damage=='terminal':row['terminal_economic_contract']=None
    if damage=='missing_scenario':case['compiled_scenarios'].pop('bull')
    if damage=='new_identity':case['version_metadata']['run_id']=case['template_package']['run_id']
    if damage=='future':case['version_metadata']['generated_at']='2099-01-01T00:00:00+00:00'
    if damage=='ref_hash':case['evidence_refs'][0]['sha256']='0'*64
    if damage=='duplicate_id':case['source_catalog'].append(deepcopy(case['source_catalog'][0]))
    if damage=='source_bytes':(case['root']/case['source_catalog'][0]['local_path']).write_bytes(b'TEST_ONLY tampered')
    if damage=='source_future':case['source_catalog'][0]['source_available_at']='2099-01-01T00:00:00+00:00'
    def forbidden(*args,**kwargs):raise AssertionError('Invalid runner input must not reach model')
    monkeypatch.setattr(model.ResidualIncomePathValuationModel,'value',forbidden)
    with no_io_effects(),pytest.raises(ValueError):mod.run_explicit_cash_research(**case)


def test_changed_inputs_get_new_fingerprint_and_old_approvals_are_not_carried(case):
    # Deliberately invalid old market/approval payloads must not be interpreted.
    case['template_package']['quote']={'TEST_ONLY_STALE_PRICE':True}
    case['template_package']['human_research_approval']={'TEST_ONLY_STALE_APPROVAL':True}
    with no_io_effects():first_result=mod.run_explicit_cash_research(**case)
    case['assumption_metadata']['rationale']='TEST_ONLY revised explicit economic basis'
    with no_io_effects():second_result=mod.run_explicit_cash_research(**case)
    assert first_result['input_descriptor_sha256']!=second_result['input_descriptor_sha256']
    assert first_result['descriptor'].quote is None and second_result['descriptor'].valuation_approval is None
    assert first_result['outcome'].valuation.status=='conditional_research_only'
