"""D2 source-node and operating-path verification; no valuation or new company compilation."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.application.research import operating_assumption_draft_v1 as mod

CODE=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,1,tzinfo=timezone.utc)


def write(root,path,value):
    target=root/path
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    return dict(path=path,sha256=hashlib.sha256(target.read_bytes()).hexdigest())


@pytest.fixture(autouse=True)
def no_valuation_or_network(monkeypatch):
    import requests
    from value_investment_agent.valuation_models import residual_income_path_v4
    def forbidden(*args,**kwargs):
        raise AssertionError('D2 must not execute valuation, construct candidates or call a network')
    monkeypatch.setattr(mod.neutral,'build_neutral_valuation_proposal',forbidden)
    monkeypatch.setattr(residual_income_path_v4.ResidualIncomeContractDispatcher,'value',forbidden)
    monkeypatch.setattr(requests.sessions.Session,'request',forbidden)


@pytest.fixture
def sample(tmp_path,monkeypatch):
    # Existing checked-in research values, with explicit TEST_ONLY original transport.
    inputs=json.loads((CODE/'config/research-assumptions/600519-joint-capital-cash-path-v4.json').read_bytes())
    policy=json.loads((CODE/'config/research-proposals/600519-joint-capital-cash-path-v4.json').read_bytes())
    refs={}
    for index,ref in enumerate(inputs['source_bindings']):
        target=tmp_path/f'runtime/TEST_ONLY-source-{index}.bin'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(('TEST_ONLY original '+str(index)).encode())
        refs[ref['path']]=dict(path=target.relative_to(tmp_path).as_posix(),sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    def rewrite(node):
        if isinstance(node,dict):
            result={k:rewrite(v) for k,v in node.items()}
            if node.get('path') in refs:
                result.update(refs[node['path']])
            return result
        if isinstance(node,list): return [rewrite(row) for row in node]
        return node
    inputs=rewrite(inputs)
    package=dict(schema_version='m1-valuation-package-v2',symbol='600519',name=inputs['name'],
        research_case=dict(symbol='600519',financial_period=inputs['financial_basis']),
        point_in_time=dict(report_period=inputs['financial_basis'],available_at='2026-10-24T00:00:00+00:00',
                           computed_at='2026-10-24T00:00:00+00:00'),sources=[],
        facts=dict(operating_inputs=dict(start_book_equity='500000000000',ordinary_shares='1000')))
    package['sources']=[dict(id=spec['source_id'],sha256=spec['sha256'],
        local_path=spec['path'],location=spec['source_url'],
        source_available_at='2026-09-10T00:00:00+00:00',retrieved_at='2026-10-23T00:00:00+00:00')
        for spec in inputs['historical_statement_specs']]
    package_ref=write(tmp_path,'runtime/TEST_ONLY-package.json',package)
    inputs['package_binding']=package_ref
    policy['source_package_sha256']=package_ref['sha256']
    a_path='config/research-assumptions/600519-joint-capital-cash-path-v4.json'
    p_path='config/research-proposals/600519-joint-capital-cash-path-v4.json'
    def save():
        assumption_ref=write(tmp_path,a_path,inputs)
        policy['rationale_bindings'][0].update(path=assumption_ref['path'],sha256=assumption_ref['sha256'],available_at=inputs['generated_at'])
        policy_ref=write(tmp_path,p_path,policy)
        return assumption_ref,policy_ref
    save()
    # Only synthetic original extraction is replaced. Source hashes, node replay,
    # existing capital-path compiler and all D2 validations execute normally.
    def replay(**kwargs):
        result=deepcopy(inputs['historical_statement_replay'])
        result['observed_at']=kwargs['now'].isoformat()
        return result
    monkeypatch.setattr(mod.bridge,'research_from_retained_sources',replay)
    return tmp_path,inputs,policy,save


def test_source_node_to_capital_paths_is_read_only_and_unapproved(sample):
    root,inputs,policy,_=sample
    before={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=mod.build_operating_assumption_draft(root=root,symbol='600519',now=NOW)
    assert result['status']=='SOURCE_BOUND_D2_DRAFT'
    assert len(result['branches'])==3 and result['fact_anchors']
    assert result['capital_path_recomputed'] is True and result['valuation_computed'] is False
    for branch in result['branches']:
        assert set(branch['scenarios'])=={'bear','base','bull'}
        assert branch['economic_rationale'] and branch['counter_evidence']
        for name,scenario in branch['scenarios'].items():
            assert scenario['drivers']==inputs['scenarios'][branch['branch_id']][name]['drivers']
            assert len(scenario['operating_capital_path']['rows'])==10
            assert scenario['classification']=='RESEARCH_ASSUMPTION'
    assert result['formal_fact_count']==0 and not result['formal_eligibility']
    assert result['action']=='no_order' and not result['e2_new_company_compilation']
    assert result['unknowns'] and result['invalidation_conditions']
    assert not any(row['field'] in {'tax_rate_assumption','parent_attribution_assumption'} for row in result['unknowns'])
    assert before=={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert mod.build_operating_assumption_draft(root=root,symbol='600519',now=NOW)['input_fingerprint']==result['input_fingerprint']


@pytest.mark.parametrize('damage',['source_hash','future','issuer','period','scenario_mismatch',
    'missing_working_capital','year_bool','missing_counterevidence','historical_amount','parameter_fact'])
def test_bad_source_or_economic_inputs_fail_closed(sample,damage):
    root,inputs,policy,save=sample
    branch=policy['choices'][0]
    if damage=='source_hash':
        (root/inputs['source_bindings'][0]['path']).write_bytes(b'TEST_ONLY changed')
    if damage=='future': inputs['generated_at']='2099-01-01T00:00:00+00:00'
    if damage=='issuer': inputs['symbol']='600887'
    if damage=='period': inputs['financial_basis']='2025-12-31'
    if damage=='scenario_mismatch': inputs['scenarios'][branch['id']]['base']['cost_of_equity']='0.11'
    if damage=='missing_working_capital':
        del inputs['scenarios'][branch['id']]['base']['drivers']['years'][0]['operating_wc_cash_cny']
        del branch['joint_drivers']['base']['years'][0]['operating_wc_cash_cny']
    if damage=='year_bool':
        inputs['scenarios'][branch['id']]['base']['drivers']['years'][0]['year']=True
        branch['joint_drivers']['base']['years'][0]['year']=True
    if damage=='missing_counterevidence': inputs['scenario_explanations'][branch['id']]['counter_evidence']=''
    if damage=='historical_amount':
        inputs['observations']['revenue']['value']='1'
        policy['joint_historical']['revenue']['value']='1'
    if damage=='parameter_fact': inputs['parameter_basis']['classification']='FACT'
    save()
    with pytest.raises(ValueError):
        mod.build_operating_assumption_draft(root=root,symbol='600519',now=NOW)


def test_missing_source_reports_exact_dependency_without_new_case(sample):
    root,inputs,_,_=sample
    missing=inputs['source_bindings'][0]
    (root/missing['path']).unlink()
    result=mod.build_operating_assumption_draft(root=root,symbol='600519',now=NOW)
    assert result['status']=='MISSING_SOURCE'
    assert result['missing_sources']==[{key:missing[key] for key in ('path','sha256')}]
    assert result['branches']==[] and not result['valuation_computed']


def test_explicit_binding_tamper_and_unknown_source_are_not_fallbacks(sample):
    root,_,_,save=sample
    assumption,proposal=save()
    assumption['sha256']='0'*64
    with pytest.raises(ValueError,match='hash mismatch'):
        mod.build_operating_assumption_draft(root=root,symbol='600519',now=NOW,
            assumption_binding=assumption,proposal_binding=proposal)
    missing=mod.build_operating_assumption_draft(root=root,symbol='000333',now=NOW)
    assert missing['status']=='MISSING_SOURCE' and '000333' in missing['missing_sources'][0]['path']


@pytest.mark.parametrize('symbol',['600519','600887'])
def test_real_two_company_originals_and_capital_path_replay(symbol):
    location=os.environ.get('VALUE_OPERATING_ASSUMPTION_REAL_ROOT')
    if not location: pytest.skip('Explicit D2 original-source root required')
    root=Path(location)
    private=root/'config/current-research-drafts.json'
    before=private.read_bytes() if private.exists() else None
    result=mod.build_operating_assumption_draft(root=root,symbol=symbol,now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_BOUND_D2_DRAFT',result.get('missing_sources')
    assert len(result['branches'])==3
    assert result['source_replay_status']=='ORIGINAL_STATEMENTS_RECOMPUTED_AND_MATCHED'
    assert result['fact_anchors'] and result['historical_observations']
    assert result['capital_path_recomputed'] and not result['valuation_computed']
    assert not result['formal_eligibility'] and not result['e2_new_company_compilation']
    for branch in result['branches']:
        for scenario in branch['scenarios'].values():
            assert len(scenario['operating_capital_path']['rows'])==10
            assert scenario['operating_capital_path']['funding_status']=='FUNDED'
    assert all(row['declared']['classification']=='ASSUMPTION'
        for row in result['historical_observations'] if row['field'] in {'opening_cash','cash_floor','opening_distribution_capacity'})
    assert before==(private.read_bytes() if private.exists() else None)


@pytest.mark.parametrize('damage',['deleted_mapping','wrong_mapping','source_available_at','retrieved_at','original_retrieved_at','same_acquisition','publication','spec_future'])
def test_consistently_resigned_history_and_source_clocks_rejected(sample,damage):
    root,inputs,policy,save=sample
    if damage in {'deleted_mapping','wrong_mapping'}:
        inputs['observations']['revenue']['value']='1'
        policy['joint_historical']['revenue']['value']='1'
        if damage=='deleted_mapping': del inputs['observations']['revenue']['statement_field']
        else: inputs['observations']['revenue']['statement_field']='parent_profit'
    else:
        package=json.loads((root/inputs['package_binding']['path']).read_bytes())
        if damage=='publication':
            package['sources'][0]['published_at']='2026-04-18T00:00:00+08:00'
        elif damage=='spec_future':
            inputs['historical_statement_specs'][0]['original_acquired_at']='2099-01-01T00:00:00+00:00'
        elif damage=='same_acquisition':
            package['sources'][0]['original_retrieved_at']='2026-09-11T00:00:00+00:00'
            inputs['historical_statement_specs'][0]['original_acquired_at']='2026-09-10T00:00:00+00:00'
        else: package['sources'][0][damage]='2099-01-01T00:00:00+00:00'
        ref=write(root,inputs['package_binding']['path'],package)
        inputs['package_binding']=ref
        policy['source_package_sha256']=ref['sha256']
    save()
    with pytest.raises(ValueError,match='D2 (required historical|consumed source time|same original acquisition|statement/catalog publication)'):
        mod.load_operating_assumption_draft(root=root,symbol='600519',now=NOW)
