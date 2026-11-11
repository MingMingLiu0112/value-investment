"""TEST_ONLY source substitutes; optional retained originals are a separate test."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import pytest

from value_investment_agent.application.research import fiscal_earnings_research as service

NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

@pytest.fixture
def retained(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    name = 'config/research-assumptions/600887-fiscal-earnings-v1.json'
    policy = json.loads((root/name).read_bytes())
    annual = json.loads((root/policy['annual_policy_binding']['path']).read_bytes())
    spec = json.loads((root/service.SPEC).read_bytes())
    spec['companies'] = {'600887':spec['companies']['600887']}
    for i,row in enumerate(spec['companies']['600887']):
        target = tmp_path/f'runtime/TEST_ONLY-{i}.pdf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'%PDF-TEST_ONLY-NOT-OFFICIAL-'+str(i).encode())
        row['path'],row['sha256'] = target.relative_to(tmp_path).as_posix(),sha256(target.read_bytes()).hexdigest()
        annual['official_sources'][row['source_id']] = row['sha256']
    write(tmp_path/policy['annual_policy_binding']['path'],annual)
    policy['annual_policy_binding']['sha256'] = sha256((tmp_path/policy['annual_policy_binding']['path']).read_bytes()).hexdigest()
    policy['accounting_comparability']['source_sha256'] = deepcopy(annual['official_sources'])
    write(tmp_path/name,policy)
    write(tmp_path/service.SPEC,spec)
    for ref in service._IMPLEMENTATIONS:
        target = tmp_path/ref['path']; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((root/ref['path']).read_bytes())
    def lines(revenue, cost, pbt, tax, nci):
        return dict(operating_revenue=str(revenue), **{k:str(cost) for k in ('cost_of_sales','taxes_surcharges','selling','administration','research')},
            profit_before_tax=str(pbt),income_tax=str(tax),minority_profit=str(nci),parent_profit=str(pbt-tax-nci),asset_impairment='-10')
    values = {'FY2025':lines(1000,100,300,50,-10), 'FY2024':lines(900,90,250,40,-5),
        'H12026':lines(500,50,120,25,-5),'H12025':lines(400,40,100,20,-5)}
    statements = [dict(periods=p, rows={k:dict(values=[values[y][k] for y in p]) for k in service.HISTORICAL_FIELDS})
        for p in (['FY2025','FY2024'],['H12026','H12025'])]
    parsed = dict(symbol='600887', original_statements=statements, source_bindings=spec['companies']['600887'])
    monkeypatch.setattr(service,'research_from_retained_sources',lambda **_:deepcopy(parsed))
    pages = {}
    for row in spec['companies']['600887']:
        result = ['TEST_ONLY']*220
        for evidence in policy['accounting_comparability']['evidence']:
            if evidence['source_id']==row['source_id']:
                result[evidence['physical_page']-1]=evidence['expected_excerpt']
        pages[row['path']] = result
    monkeypatch.setattr(service,'extract_pages',lambda p:deepcopy(pages[p.relative_to(tmp_path).as_posix()]))
    return tmp_path,policy,spec,pages,parsed

def test_dated_research_retains_h1_and_uses_scenario_specific_stubs_readonly(retained):
    root,_,_,_,_=retained
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=service.load_fiscal_earnings_research(root=root,symbol='600887',now=NOW)
    assert result['status']=='SOURCE_BOUND_FISCAL_RESEARCH_NOT_APPROVED'
    assert result['currency']=='CNY' and result['scope']=='consolidated'
    assert result['historical_h2_2025']['lines']['parent_profit']=='175'
    for name,row in result['scenarios'].items():
        assert row['fy2026']['classification']=='MIXED_ACTUAL_H1_AND_RESEARCH_H2'
        assert row['rows'][0]['year']==2027 and row['rows'][-1]['year']==2031
        assert row['fy2026']['lines']['parent_profit'] != row['stub']['lines']['parent_profit']
    assert result['dividend_capacity_cny'] is result['normalized_parent_profit_cny'] is None
    assert result['formal_eligibility'] is result['economic_approval'] is False
    assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}

@pytest.mark.parametrize('fault',['future','naive','issuer','original','implementation','inherited','excerpt','page','basis','perimeter','short','countercase','source_url'])
def test_bad_fiscal_sources_never_keep_values(retained,fault):
    root,policy,spec,pages,parsed=retained
    now=NOW
    if fault=='future': policy['generated_at']='2027-01-01T00:00:00Z'
    elif fault=='naive': now=now.replace(tzinfo=None)
    elif fault=='issuer': parsed['symbol']='000001'
    elif fault=='original': (root/spec['companies']['600887'][0]['path']).write_bytes(b'changed')
    elif fault=='implementation': (root/service._IMPLEMENTATIONS[0]['path']).write_bytes(b'changed')
    elif fault=='inherited': (root/policy['annual_policy_binding']['path']).write_bytes(b'changed')
    elif fault=='excerpt': pages[spec['companies']['600887'][0]['path']][57]='TEST_ONLY_NO_EVIDENCE'
    elif fault=='page': policy['accounting_comparability']['evidence'][0]['physical_page']=999
    elif fault=='basis': policy['accounting_comparability']['source_sha256']={}
    elif fault=='perimeter': policy['accounting_comparability']['perimeter']='CONSTANT_PERIMETER'
    elif fault=='short': policy['stub_scenarios'].pop('bear')
    elif fault=='countercase': policy['counter_evidence']=[]
    elif fault=='source_url':
        spec['companies']['600887'][0]['source_url']='https://static.cninfo.com.cn/finalpage/2026-04-30/999999.PDF'
        write(root/service.SPEC,spec)
    write(root/'config/research-assumptions/600887-fiscal-earnings-v1.json',policy)
    result=service.load_fiscal_earnings_research(root=root,symbol='600887',now=now)
    assert result['status']=='SOURCE_OR_FISCAL_ASSUMPTION_REVALIDATION_FAILED'
    assert result['scenarios']=={} and result['formal_eligibility'] is False

def test_final_drift_recheck(retained,monkeypatch):
    root,_,spec,_,_=retained
    original=service.build_fiscal_industrial_earnings_paths
    def changed(**kwargs):
        result=original(**kwargs)
        (root/spec['companies']['600887'][0]['path']).write_bytes(b'TEST_ONLY_CHANGED_DURING_CALC')
        return result
    monkeypatch.setattr(service,'build_fiscal_industrial_earnings_paths',changed)
    result=service.load_fiscal_earnings_research(root=root,symbol='600887',now=NOW)
    assert result['scenarios']=={} and result['status']=='SOURCE_OR_FISCAL_ASSUMPTION_REVALIDATION_FAILED'

def test_no_policy_is_not_new_research(tmp_path):
    assert service.load_fiscal_earnings_research(root=tmp_path,symbol='000001',now=NOW) is None

@pytest.mark.parametrize('target',['policy','spec'])
def test_parsed_bytes_are_the_same_bytes_that_are_fingerprinted(retained,monkeypatch,target):
    root,_,_,_,_=retained
    path=root/('config/research-assumptions/600887-fiscal-earnings-v1.json' if target=='policy' else service.SPEC)
    original=Path.read_bytes
    changed=json.loads(original(path))
    if target=='policy': changed['stub_scenarios']['base']['revenue_growth']='0.50'
    else: changed['common_fields']=[]
    alternative=json.dumps(changed).encode()
    count=0
    def read(p):
        nonlocal count
        if p==path:
            count+=1
            if count==1: return alternative
        return original(p)
    monkeypatch.setattr(Path,'read_bytes',read)
    result=service.load_fiscal_earnings_research(root=root,symbol='600887',now=NOW)
    assert result['status']=='SOURCE_OR_FISCAL_ASSUMPTION_REVALIDATION_FAILED'
    assert result['scenarios']=={}

def test_actual_retained_originals():
    location=os.environ.get('FISCAL_EARNINGS_REPLAY_ROOT')
    if not location: pytest.skip('Opt-in actual retained public originals')
    result=service.load_fiscal_earnings_research(root=Path(location),symbol='600887',now=NOW)
    assert result['status']=='SOURCE_BOUND_FISCAL_RESEARCH_NOT_APPROVED'
    assert result['historical_h2_2025']['lines']['operating_revenue']=='53859484567.37'
    assert result['scenarios']['base']['fy2026']['lines']['parent_profit']=='9487874147.8467674720'
    assert result['scenarios']['base']['rows'][0]['parent_profit_cny']=='10782465082.469105781160'
    assert result['accounting_comparability']['perimeter']=='AS_REPORTED_NOT_CONSTANT_PERIMETER'
