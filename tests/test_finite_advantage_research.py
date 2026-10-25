"""Synthetic application contracts; retained-original validation is opt-in."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from value_investment_agent.application.research import finite_advantage_research as research


@pytest.fixture
def inputs():
    root = Path(__file__).resolve().parents[1]
    policy = json.loads((root/'config/research-assumptions/600519-finite-advantage-cash-v1.json').read_bytes())
    ledger = dict(history=dict(scope='standalone parent, NOT consolidated free cash', unit='CNY',
        ttm=dict(cash_end='80', parent_retained_profit_end='100'),
        known_uncalled_fund_commitment=dict(amount_cny='0')),
        plan=dict(horizon=5, incremental_parent_cash_yield='0.01', explicit_retention='0.10', ke='0.10'),
        cases=dict(TIMING_DELAY={name:dict(blockers=[], cash_floor='10', project_budget='0',
            annual_rows=[dict(year=y, legacy_profit_before_new_cash_cost='30') for y in range(1,6)])
            for name in ('bear','base','bull')}))
    facts = SimpleNamespace(operating_inputs=dict(start_book_equity='100', ordinary_shares='10'))
    return policy, dict(symbol='600519', point_in_time=dict(valuation_date='2026-06-30')), ledger, facts


def test_research_has_real_calculations_and_independent_cash_rejections(inputs):
    policy, package, ledger, facts = inputs
    original = deepcopy(ledger)
    result = research.build_finite_advantage_research(policy=policy, package=package, ledger=ledger, facts=facts)
    assert len(result['branches']) == 12
    baseline = [b for b in result['branches'] if b['branch']=='BALANCED_NET_MAINTENANCE']
    assert len(baseline)==6
    assert all(b['result']['valuation']['usable'] for b in baseline)
    assert all(b['result']['valuation']['per_share_cny'] is not None for b in baseline)
    extra = [b for b in result['branches'] if b['branch'].startswith('EXTRA_')]
    assert all(not b['result']['valuation']['usable'] for b in extra)
    assert all('TERMINAL_net_maintenance_wc_balanced' in b['result']['blockers'] for b in extra)
    assert ledger == original
    assert result['price_condition_cny'] is None and result['primary_valuation_changed'] is False


@pytest.mark.parametrize('damage', ['cash_scope','yield','retention','currency_identity','horizon','ratio'])
def test_changed_basis_requires_research_again(inputs, damage):
    policy, package, ledger, facts = inputs
    if damage=='cash_scope': ledger['history']['scope']='consolidated'
    if damage=='yield': ledger['plan']['incremental_parent_cash_yield']='.10'
    if damage=='retention': ledger['plan']['explicit_retention']='0.01'
    if damage=='currency_identity': ledger['history']['unit']='USD'
    if damage=='horizon': ledger['plan']['horizon']=6
    if damage=='ratio': policy['maintenance_gap_challenge_ratios']=['0','0.01']
    with pytest.raises(ValueError):
        research.build_finite_advantage_research(policy=policy,package=package,ledger=ledger,facts=facts)


@pytest.fixture
def source_root(tmp_path, monkeypatch, inputs):
    policy, package, ledger, facts = inputs
    for ref in research._IMPLEMENTATIONS:
        target = tmp_path/ref['path']
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((Path(__file__).resolve().parents[1]/ref['path']).read_bytes())
    def write(name, value):
        p=tmp_path/name
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(json.dumps(value),encoding='utf-8')
        return dict(path=name,sha256=sha256(p.read_bytes()).hexdigest())
    p_ref=write('runtime/TEST_ONLY-package.json',package)
    l_ref=write('runtime/TEST_ONLY-ledger.json',ledger)
    candidate=dict(source_package_binding=p_ref,native_cash_ledger_binding=l_ref,source_bindings=[])
    c_ref=write('runtime/TEST_ONLY-candidate.json',candidate)
    policy['candidate_binding']=c_ref
    policy_path='config/research-assumptions/600519-finite-advantage-cash-v1.json'
    write(policy_path,policy)
    monkeypatch.setattr(research,'load_current_pending_candidate_supplement',lambda **kw:dict(candidate_binding=c_ref))
    monkeypatch.setattr(research,'verify_source_native_candidate',lambda **kw:candidate)
    monkeypatch.setattr(research,'build_descriptor',lambda *a,**kw:SimpleNamespace(facts=facts))
    return tmp_path, policy_path, c_ref


def test_current_source_read_recomputes_without_writes(source_root):
    root, _, _=source_root
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result=research.load_finite_advantage_research(root=root,symbol='600519',now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED'
    assert result['formal_eligibility'] is result['economic_approval'] is result['price_admission'] is False
    assert before=={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('damage',['future','wrong_current','changed_source','changed_implementation','during_calculation'])
def test_bad_current_evidence_does_not_fall_back(source_root,monkeypatch,damage):
    root, policy_path, c_ref=source_root
    if damage=='future':
        p=json.loads((root/policy_path).read_bytes());p['generated_at']='2999-01-01T00:00:00+00:00'
        (root/policy_path).write_text(json.dumps(p),encoding='utf-8')
    if damage=='wrong_current':
        monkeypatch.setattr(research,'load_current_pending_candidate_supplement',lambda **kw:dict(candidate_binding={**c_ref,'sha256':'0'*64}))
    if damage=='changed_source': (root/c_ref['path']).write_text('{}',encoding='utf-8')
    if damage=='changed_implementation':
        (root/research._IMPLEMENTATIONS[0]['path']).write_bytes(b'TEST_ONLY altered implementation')
    if damage=='during_calculation':
        original=research.build_finite_advantage_research
        def changed(**kw):
            result=original(**kw)
            (root/policy_path).write_text('{}',encoding='utf-8')
            return result
        monkeypatch.setattr(research,'build_finite_advantage_research',changed)
    result=research.load_finite_advantage_research(root=root,symbol='600519',now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_OR_HYPOTHESIS_REVALIDATION_FAILED'
    assert result['branches']==[]


def test_retained_original_research_is_not_strategy_admission():
    path=os.environ.get('FINITE_ADVANTAGE_RESEARCH_ROOT')
    if not path: pytest.skip('Opt-in retained public original sources')
    result=research.load_finite_advantage_research(root=Path(path),symbol='600519',now=datetime.now(timezone.utc))
    assert result['status']=='SOURCE_BOUND_FINITE_RESEARCH_NOT_APPROVED'
    base=[b for b in result['branches'] if b['scenario']=='base' and b['branch']=='BALANCED_NET_MAINTENANCE']
    assert len(base)==2 and all(b['result']['valuation']['usable'] for b in base)
    persistent=[b for b in result['branches'] if b['branch']=='PERSISTENT_10_PERCENT_UNREMITTED']
    assert all('YEAR_5_CASH_FLOOR' in b['result']['blockers'] for b in persistent)
    assert result['formal_eligibility'] is False
