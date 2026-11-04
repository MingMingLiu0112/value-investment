"""Cash projection isolation; real replay is opt-in and never mocked acceptance."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import json
import os
from pathlib import Path

import pytest

from web_api.test_live_operating_research_api import api,reviewed_result,BASE
from test_web_agent_research import state
from test_operating_cash_consumption_v1 import no_io_effects
from value_investment_agent.application.research import operating_cash_consumption_v1 as consumer
from value_investment_agent.application.research import operating_cash_followup_v1 as followup
from value_investment_agent.infrastructure.agent_runtime import provider


@pytest.fixture(autouse=True)
def forbid_paid_transport(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('No real provider/network allowed')
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider,'complete',denied)
    monkeypatch.setattr(provider,'build_opener',denied)


@pytest.mark.parametrize('cash_status',['PARTIAL','UNASSESSABLE'])
def test_public_cash_projection_failure_keeps_succeeded_d2_read_only(api,monkeypatch,cash_status):
    client,_,data,root=api
    task=reviewed_result()
    data.rows=[task]
    original=deepcopy(task)
    calls=[]
    cash=dict(status=cash_status,reason='TEST_ONLY cash input missing',action='no_order',
        formal_eligibility=False,annual_followup={'status':'UNASSESSABLE','reason':'TEST_ONLY'})
    def fake_consumer(**kwargs):
        calls.append(kwargs)
        assert kwargs['task']==original
        return deepcopy(cash)
    monkeypatch.setattr(consumer,'read_operating_cash_consumption',fake_consumer)
    before=state(root)
    for _ in range(2):
        response=client.get(BASE+'/companies/600519')
        body=response.json()
        assert response.status_code==200 and response.headers['cache-control']=='no-store'
        assert body['status']=='SUCCEEDED' and body['cash_consumption']==cash
        assert body['research_draft']==task['research_draft']
        assert body['independent_review']==task['independent_review']
        assert body['formal_eligibility'] is False and body['action']=='no_order'
    assert len(calls)==2 and data.rows==[original]
    assert not data.provider_calls and state(root)==before
    assert all(call[0]=='list' for call in data.calls)


@pytest.mark.parametrize('failure',[ValueError('TEST_ONLY source hash mismatch'),
    OSError('TEST_ONLY missing original'),KeyError('TEST_ONLY required mapping')])
def test_source_exception_is_cash_unassessable_not_erased_operating_success(api,monkeypatch,failure):
    client,_,data,root=api
    task=reviewed_result()
    data.rows=[task]
    def bad_source(**kwargs):raise failure
    monkeypatch.setattr(consumer,'read_operating_cash_consumption',bad_source)
    before=state(root)
    body=client.get(BASE+'/companies/600519').json()
    assert body['status']=='SUCCEEDED' and body['research_draft']==task['research_draft']
    assert body['cash_consumption']['status']=='UNASSESSABLE'
    assert body['cash_consumption']['reason']=='CASH_SOURCE_OR_MAPPING_NOT_VERIFIED'
    assert body['cash_consumption']['formal_eligibility'] is False
    assert body['formal_eligibility'] is False and body['main_range_adopted'] is False
    assert body['condition_price'] is None and body['personal_quantity'] is None
    assert not data.provider_calls and state(root)==before


def test_public_projection_exposes_parent_cash_followup_without_promoting_it(api,monkeypatch):
    client,_,data,root=api
    task=reviewed_result()
    data.rows=[task]
    expected=dict(status="SOURCE_BOUND_PARENT_CASH_OBSERVATIONS_READY_FOR_POLICY",
        action="no_order", formal_eligibility=False, valuation=None, condition_price=None,
        current_blockers=[{"code":"TEST_ONLY_POLICY_REQUIRED"}])
    monkeypatch.setattr(followup,"read_registered_operating_cash_followup",
        lambda **kwargs: deepcopy(expected))
    before=state(root)
    body=client.get(BASE+"/companies/600519").json()
    assert body["status"]=="SUCCEEDED"
    assert body["parent_cash_followup"]==expected
    assert body["formal_eligibility"] is False and body["condition_price"] is None
    assert not data.provider_calls and state(root)==before


def load_real_case(root,now):
    from value_investment_agent.application.research.agent_review.operating_task_v2 import LiveOperatingTaskService
    registry=json.loads((root/'config/current-operating-research-sources-v1.json').read_bytes())
    ref=registry['cases']['000568']['cash_followup']
    spec=consumer._bound_json(root,ref)
    ids=[part for part in Path(spec['task_state_binding']['path']).parts if part.startswith('rt-')]
    assert len(ids)==1,'Followup must explicitly bind one task'
    service=LiveOperatingTaskService(root)
    task_spec,task_state,binding=service._load(ids[0],recover=False)
    assert binding==spec['task_state_binding'],'Registered task head changed; new supplement required'
    task=service._view(task_spec,task_state,binding,now)
    assert task['status']=='SUCCEEDED' and task['scope']=='LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED'
    assert task['symbol']=='000568' and task.get('operating_driver_bridge')
    return task,spec,service


def real_root():
    location=os.environ.get('OPERATING_SOURCES_REAL_ROOT')
    if location is None:pytest.skip('Real task/spec NOT RUN; set OPERATING_SOURCES_REAL_ROOT')
    assert location.strip(),'Explicit real root must not be empty'
    return Path(location).resolve(strict=True)


def test_real_task_new_spec_recomputes_30_cash_rows_and_shared_model_without_writes(monkeypatch):
    from value_investment_agent.valuation_models import residual_income_path_v4 as model
    root=real_root()
    now=datetime.now(timezone.utc)
    model_inputs=[]
    calculations=[]
    actual_value=model.ResidualIncomePathValuationModel.value
    actual_calculation=model.scenario_calculation
    def counted_value(self,facts,case):
        model_inputs.append(deepcopy(facts.scenario_inputs))
        return actual_value(self,facts,case)
    def counted_calculation(*args,**kwargs):
        result=actual_calculation(*args,**kwargs)
        calculations.append(deepcopy(result))
        return result
    # Spies only: all source parsing, arithmetic and model admission execute unchanged.
    monkeypatch.setattr(model.ResidualIncomePathValuationModel,'value',counted_value)
    monkeypatch.setattr(model,'scenario_calculation',counted_calculation)
    with no_io_effects():
        task,spec,service=load_real_case(root,now)
        before=deepcopy(task)
        result=consumer.read_operating_cash_consumption(root=root,task=task,now=now)
        assert service._load(task['task_id'],recover=False)[2]==task['record_binding']
    assert task==before
    annual=result['annual_followup']
    assert annual['status']=='CONDITIONAL_STRESS_CONSUMED',annual
    assert result['status']=='CONDITIONAL_EARNINGS_CASH_VALUATION_CONSUMED'
    assert set(annual['annual_ledgers'])=={'bear','base','bull'}
    assert sum(len(ledger['rows']) for ledger in annual['annual_ledgers'].values())==30
    assert len(model_inputs)>=2,'Both old policy replay and new shared model must execute'
    assert model_inputs[-1]!=model_inputs[0],'New forecast inputs must not reuse old model inputs'
    for name,ledger in annual['annual_ledgers'].items():
        assert len(ledger['rows'])==10
        assert model_inputs[-1][name].forecast_roes==tuple(Decimal(row['forecast_roe']) for row in ledger['rows'])
        assert all(abs(Decimal(row['clean_surplus_residual']))<=Decimal('1e-20') for row in ledger['rows'])
        assert all(abs(Decimal(row['capital_identity_residual']))<=Decimal('1e-20') for row in ledger['rows'])
    assert len(calculations)>=6,'Three old and three new scenarios must be genuinely computed'
    for calc in calculations[-3:]:
        assert abs(Decimal(calc['dividend_crosscheck_difference_cny']))<=Decimal('.01')
        assert abs(Decimal(calc['conditional_equity_value_cny'])-Decimal(calc['dividend_crosscheck_equity_value_cny']))<=Decimal('.01')
    assert [c['conditional_equity_value_cny'] for c in calculations[-3:]]!=[c['conditional_equity_value_cny'] for c in calculations[:3]]
    assert annual['research_case']['research_version']=='operating-cash-followup-spec-v1'
    assert spec['task_state_binding'] in annual['sources']
    assert annual['scope']=='UNADOPTED_ROLLING_STRESS_NOT_CURRENT_MAIN_VALUE'
    assert annual['formal_eligibility'] is False and annual['main_range_adopted'] is False
    assert annual['condition_price'] is None and annual['personal_quantity'] is None
    assert annual['price_policy']['draft_prices'] is None and annual['price_policy']['rules']==[]
    assert annual['price_policy']['policy_contract']=='value-price-policy-draft-v1'
    assert annual['price_policy']['preparation_status'] in {'CURRENT_PUBLIC_RESEARCH_BASIS_UNAVAILABLE','BLOCKED'}
    assert set(annual['price_policy']['diagnostic_preview_prices'].values())=={None}
    assert result['formal_eligibility'] is False and result['condition_price'] is None
    assert result['action']==annual['action']=='no_order'


def test_real_consumer_rejects_misbound_spec_and_bad_source_without_changing_task():
    root=real_root()
    now=datetime.now(timezone.utc)
    with no_io_effects():
        task,spec,service=load_real_case(root,now)
        before=deepcopy(task)
        for change in ({'symbol':'600519'}, {'task_state_binding':{'path':'runtime/TEST_ONLY','sha256':'0'*64}},
                       {'transport':'TEST_ONLY_unknown'}):
            with pytest.raises(ValueError,match='CASH_FOLLOWUP_SPEC_OR_TASK_VERSION_MISMATCH'):
                consumer.consume_annual_followup(root=root,spec={**spec,**change},task=task,context={},now=now)
        bad=deepcopy(task)
        bad['source_binding']['sha256']='0'*64
        with pytest.raises(ValueError):consumer.read_operating_cash_consumption(root=root,task=bad,now=now)
        assert task==before and service._load(task['task_id'],recover=False)[2]==task['record_binding']

def test_real_bound_task_and_source_reject_in_memory_financial_substitution():
    from value_investment_agent.application.research.agent_review.operating_sources_v1 import build_operating_source_context
    root=real_root()
    now=datetime.now(timezone.utc)
    with no_io_effects():
        task,spec,service=load_real_case(root,now)
        context=build_operating_source_context(root=root,symbol=task["symbol"],
            now=datetime.fromisoformat(task["research_as_of"]),binding=task["source_binding"])
        bad_context=deepcopy(context)
        target=next(r for r in bad_context["evidence"] if r.get("field")=="parent_profit" and r.get("period")=="2026-06-30")
        target["value"]=str(Decimal(target["value"])+Decimal("100000000"))
        # Retaining the old context fingerprint and all on-disk hashes must not wash changed values.
        with pytest.raises(ValueError,match="CONTEXT_MEMORY_DIFFERS_FROM_COLD_SOURCE"):
            consumer.consume_annual_followup(root=root,spec=spec,task=task,context=bad_context,now=now)
        bad_task=deepcopy(task)
        bad_task["operating_driver_bridge"]["paths"]["base"]["extrema"]["margin_lower"]["pretax_profit_cny"]="999999999999"
        with pytest.raises(ValueError,match="TASK_MEMORY_DIFFERS_FROM_COLD_STATE"):
            consumer.consume_annual_followup(root=root,spec=spec,task=bad_task,context=context,now=now)
        assert service._load(task["task_id"],recover=False)[2]==task["record_binding"]
