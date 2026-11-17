"""New dated candidate contracts; explicit real-root acceptance, no paid calls."""
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import main_valuation_revalidation_v1 as mod
from value_investment_agent.infrastructure.agent_runtime import provider
from test_operating_cash_consumption_v1 import no_io_effects


@pytest.fixture(autouse=True)
def no_paid(monkeypatch):
    def denied(*args,**kwargs):raise AssertionError('No provider/paid/network allowed')
    monkeypatch.setattr(provider.OpenAICompatibleChatProvider,'complete',denied)
    monkeypatch.setattr(provider,'build_opener',denied)


def write(root,path,payload):
    target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    return dict(path=path,sha256=hashlib.sha256(target.read_bytes()).hexdigest())


def register(root,spec):
    ref=write(root,'runtime/TEST_ONLY-main-spec.json',spec)
    write(root,mod.REGISTRY,dict(schema_version='current-operating-research-sources-v1',action='no_order',
        cases={'000568':{'main_revalidation':ref}}))
    return ref


def test_missing_and_invalid_symbol_read_only(tmp_path):
    with no_io_effects():
        result=mod.read_main_valuation_revalidation(root=tmp_path,symbol='000568',now=datetime.now(timezone.utc))
        invalid=mod.read_main_valuation_revalidation(root=tmp_path,symbol='bad',now=datetime.now(timezone.utc))
    assert result['status']=='NOT_STARTED' and invalid['status']=='UNASSESSABLE'
    assert result['formal_eligibility'] is False and result['current_comparable'] is False and result['quantity'] is None


@pytest.mark.parametrize('damage',['hash','version','future','issuer'])
def test_spec_identity_version_time_or_hash_rejected(tmp_path,damage):
    spec=dict(schema_version=mod.VERSION,symbol='000568',action='no_order',
        generated_at='2026-01-01T00:00:00+00:00',implementation_sha256=mod.implementation_fingerprints(),
        implementation_fingerprint_basis=mod.implementation_fingerprint_basis())
    if damage=='version':spec['implementation_sha256']={}
    if damage=='future':spec['generated_at']='2099-01-01T00:00:00+00:00'
    if damage=='issuer':spec['symbol']='600519'
    ref=register(tmp_path,spec)
    if damage=='hash':(tmp_path/ref['path']).write_bytes(b'TEST_ONLY changed')
    with no_io_effects():value=mod.read_main_valuation_revalidation(root=tmp_path,symbol='000568',now=datetime.now(timezone.utc))
    assert value['status']=='UNASSESSABLE' and value['reason']
    assert value['formal_eligibility'] is False and value['action']=='no_order'


@pytest.fixture
def real_case(monkeypatch,tmp_path):
    location=os.environ.get('MAIN_VALUATION_REVALIDATION_REAL_ROOT')
    if location is None:pytest.skip('Real task/spec NOT VALIDATED; set MAIN_VALUATION_REVALIDATION_REAL_ROOT')
    assert location.strip()
    root=Path(location).resolve(strict=True)
    # Integration may provide the final registered spec. Development replay uses
    # a separate test registry, never overwriting Root's shared registry/pointer.
    registry=json.loads((root/mod.REGISTRY).read_bytes())
    ref=registry['cases']['000568'].get('main_revalidation')
    if ref is None:
        path='runtime/main-revalidation-development-20261101/spec.json'
        ref=dict(path=path,sha256=hashlib.sha256((root/path).read_bytes()).hexdigest())
        test_registry=tmp_path/'TEST_ONLY-main-registry.json'
        test_registry.write_text(json.dumps(dict(schema_version='current-operating-research-sources-v1',action='no_order',
            cases={'000568':{'main_revalidation':ref}})),encoding='utf-8')
        monkeypatch.setattr(mod,'REGISTRY',test_registry.relative_to(root).as_posix())
    spec=json.loads(mod.native._raw(root,ref)[1])
    return root,ref,spec


def test_real_complete_quarters_obligation_cash_model_and_price_draft(real_case,monkeypatch):
    root,ref,spec=real_case
    from value_investment_agent.valuation_models import residual_income_path_v4 as model
    from value_investment_agent.domain.decision import value_price_policy as policy
    calculations=[];drafts=[];previews=[]
    actual_calc=model.scenario_calculation
    actual_draft=policy.draft_value_price_policy
    actual_preview=policy.preview_draft_prices
    def calc(*a,**kw):
        value=actual_calc(*a,**kw);calculations.append(value);return value
    def draft(*a,**kw):
        value=actual_draft(*a,**kw);drafts.append(value);return value
    def preview(*a,**kw):
        value=actual_preview(*a,**kw);previews.append(value);return value
    monkeypatch.setattr(model,'scenario_calculation',calc)
    monkeypatch.setattr(policy,'draft_value_price_policy',draft)
    monkeypatch.setattr(policy,'preview_draft_prices',preview)
    private=root/'config/current-research-drafts.json'
    old=private.read_bytes()
    with no_io_effects():result=mod.read_main_valuation_revalidation(root=root,symbol='000568',now=datetime.now(timezone.utc))
    assert result['status']==mod.SUCCESS,result
    assert private.read_bytes()==old
    assert result['formal_eligibility'] is False and result['main_range_adopted'] is False
    assert result['current_comparable'] is False and result['quantity'] is None
    assert result['policy_not_fully_modelled'] is True
    assert result['condition_price'] is None and result['action']=='no_order'
    assert result['period_assembly']['q3_actual']['parent_profit_cny']=='1331795155.20'
    currency=result['reporting_currency_basis']['evidence_refs'][0]
    assert currency['physical_page']==56 and '以人民币为记账本位币' in currency['excerpt']
    assert result['cash_input_basis']['source_status']=='ORIGINAL_PAGES_AND_COMPARATIVE_ROWS_COLD_MATCHED'
    assert len(result['cash_input_basis']['observations'])==16
    assert result['cash_input_basis']['net_maintenance_ex_rou_proxy_cny']=='1147809855.90'
    assert result['cash_input_basis']['wc_ex_payables_proxy_cny']=='1703710753.75'
    assert sum(len(x['rows']) for x in result['annual_ledgers'].values())==30
    for name,ledger in result['annual_ledgers'].items():
        assert ledger['opening_state']['cash_cny']=='23517778984.18'
        assert Decimal(ledger['rows'][0]['commitment_cash_cny'])==Decimal('11013375072.53')
        assert all(Decimal(row['commitment_cash_cny'])==0 for row in ledger['rows'][1:])
        assert Decimal(ledger['terminal']['commitment_cash_cny'])==0
        assert all(Decimal(row['new_operating_profit'])==0 and Decimal(row['new_liquidity_profit'])==0 for row in ledger['rows'])
        schedule=result['parent_obligations']['per_scenario'][name]['settlement_schedule']
        assert schedule['rows'][0]['closing_outstanding_cny']=='0.00'
        assert Decimal(schedule['terminal_outstanding_cny'])==0
        assert all(row['cash_use_breakdown']['classification']=='NONPRODUCTIVE_LIABILITY_SETTLEMENT' for row in ledger['rows'])
        segments=result['period_assembly']['scenarios'][name]['model_years'][0]['segments']
        assert [(s['period_start'],s['period_end']) for s in segments]==[
            ('2026-07-01','2026-09-30'),('2026-10-01','2026-12-31'),('2027-01-01','2027-06-30')]
    assert len(calculations)==3 and all(abs(Decimal(c['dividend_crosscheck_difference_cny']))<=Decimal('.01') for c in calculations)
    assert len(drafts)==len(previews)==1
    assert drafts[0]['basis']['valuation_input_version']==result['input_descriptor_sha256']
    assert drafts[0]['registered'] is False and drafts[0]['rules']==[]
    assert all(value is None for value in previews[0].values())
    assert result['price_policy']['status']=='NOT_PREPARED' and result['price_policy']['draft_prices'] is None
    assert result['dated_research_review_thresholds']['status']=='NOT_PREPARED'
    json.dumps(result,allow_nan=False)


@pytest.mark.parametrize('damage',['failed_status','wrong_id','future_publication','wrong_url','wrong_issuer'])
def test_real_quarter_receipt_metadata_cannot_be_resigned_to_claim_success(real_case,damage):
    root,_,spec=real_case
    packet=json.loads(mod.native._raw(root,spec['bindings']['quarterly_receipt'])[1])
    row=next(r for r in packet['records'] if r['source_id']==spec['quarterly_source_id'])
    row=deepcopy(row)
    if damage=='failed_status':row['status']='FAILED'
    if damage=='wrong_id':row['source_id']='OTHER'
    if damage=='future_publication':row['published_at']='2099-01-01T00:00:00+00:00'
    if damage=='wrong_url':row['url']='https://example.invalid/1225639079.PDF'
    if damage=='wrong_issuer':row['issuer_name']='OTHER'
    actual=dict(symbol='000568',issuer_name='泸州老窖股份有限公司')
    with pytest.raises(ValueError):mod._verify_quarter_receipt(row,spec,actual,datetime.now(timezone.utc),packet)


@pytest.mark.parametrize('damage',['empty_sources','missing_source','duplicate_source','wrong_period','changed_value','missing_page'])
def test_real_da_requires_complete_sources_and_cold_original_rows(real_case,damage):
    root,_,spec=real_case
    packet=json.loads(mod.native._raw(root,spec['bindings']['da_wc'])[1])
    actual=json.loads(mod.native._raw(root,spec['bindings']['native_facts'])[1])
    if damage=='empty_sources':packet['sources']=[]
    if damage=='missing_source':packet['sources'].pop()
    if damage=='duplicate_source':packet['sources'][1]=deepcopy(packet['sources'][0])
    if damage=='wrong_period':packet['sources'][0]['report_period']='2026-12-31'
    if damage=='changed_value':packet['rows'][0]['values'][0]='1.00'
    if damage=='missing_page':packet['original_pages'][packet['sources'][0]['id']]={}
    with no_io_effects(),pytest.raises(ValueError):mod._cold_da(root,packet,actual,datetime.now(timezone.utc))


def test_one_scenario_cash_failure_preserves_other_successful_ledgers(real_case,monkeypatch):
    root,ref,spec=real_case
    actual=mod.compile_operating_profit_cash_path
    calls=[]
    def failed_first(**kwargs):
        calls.append(True)
        if len(calls)==1:raise ValueError('TEST_ONLY_FUNDING_SHORTFALL')
        return actual(**kwargs)
    monkeypatch.setattr(mod,'compile_operating_profit_cash_path',failed_first)
    with no_io_effects():value=mod.read_main_valuation_revalidation(root=root,symbol='000568',now=datetime.now(timezone.utc))
    assert value['status']=='PARTIAL_REVALIDATION_PENDING_ECONOMIC_REVIEW',value
    assert value['scenario_failures']['bear']['reason']=='TEST_ONLY_FUNDING_SHORTFALL'
    assert set(value['annual_ledgers'])=={'base','bull'}
    assert value['valuation'] is None and value['formal_eligibility'] is False


def test_all_python_source_fingerprints_canonical_lf_only(tmp_path):
    from types import SimpleNamespace
    path=tmp_path/'legacy.py'
    module=SimpleNamespace(__file__=str(path),__name__=mod.native.__name__)
    path.write_bytes(b"x=1\r\ny=2\r\n")
    canonical=mod._implementation_source_hash(module)
    path.write_bytes(b"x=1\ny=2\n")
    assert mod._implementation_source_hash(module)==canonical
    path.write_bytes(b"x=3\ny=2\n")
    assert mod._implementation_source_hash(module)!=canonical
    other=SimpleNamespace(__file__=str(path),__name__='TEST_ONLY_OTHER_SOURCE')
    path.write_bytes(b"x=1\r\ny=2\r\n")
    assert mod._implementation_source_hash(other)==canonical
    assert mod.implementation_fingerprint_basis()==dict(
        default='SOURCE_CRLF_TO_LF_SHA256_V1',overrides={})
