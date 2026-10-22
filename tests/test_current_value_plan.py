from datetime import datetime, timedelta, timezone
from copy import deepcopy
import os
from pathlib import Path

from test_pending_candidate_supplement import registered
from test_value_action_plan import _published
from value_investment_agent.application.decision.current_value_plan import revalidate_current_value_plan
from value_investment_agent.application.decision.value_action_plan import load_registered_value_action_plans
from value_investment_agent.application.decision import current_value_plan
from value_investment_agent.application.product.common import sha256_file
import pytest


NOW = datetime.now(timezone.utc) + timedelta(days=1)


def test_pending_only_plan_survives_read_time_replay(registered):
    root, symbol, _, _ = registered
    plan = current_value_plan.load_current_value_action_plans(root, now=NOW)['items'][0]

    actual = revalidate_current_value_plan(root, plan, now=NOW)

    assert actual == plan
    assert actual['base'] == actual['research_analysis']['valuation']['base_value']
    assert actual['formal_eligibility'] is actual['price_comparison_eligible'] is False


def test_read_time_replay_does_not_mix_two_selected_analysis_versions(registered, monkeypatch):
    root, _, _, _ = registered
    plan = current_value_plan.load_current_value_action_plans(root, now=NOW)['items'][0]
    first = deepcopy(plan['research_analysis'])
    later = deepcopy(first)
    later['valuation']['base_value'] = '999'
    later['input_descriptor_sha256'] = 'b' * 64
    successive_reads = iter([first, later])
    monkeypatch.setattr(current_value_plan, 'load_current_research_analysis',
        lambda *args, **kwargs: next(successive_reads))

    actual = revalidate_current_value_plan(root, plan, now=NOW)

    assert actual['base'] == actual['research_analysis']['valuation']['base_value']
    assert actual['valuation_input_version'] == actual['research_analysis']['input_descriptor_sha256']


@pytest.mark.parametrize('prior_kind', ['conditional', 'registry'])
def test_current_pending_inputs_replace_unadmitted_plan_values(registered, monkeypatch, prior_kind):
    root, symbol, _, _ = registered
    pending = current_value_plan.load_current_value_action_plans(root, now=NOW)['items'][0]
    prior = deepcopy(pending)
    prior.pop('research_analysis')
    prior.pop('research_analysis_status')
    prior.update(research_as_of='2026-10-01', bear='1', base='2', bull='3',
        model_id='old-model', model_version='old-version',
        verification_scope='HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL',
        current_quote_verified=True, reference_close='27.80', market_trade_date='2026-10-22',
        quote_bridge_status='VERIFIED_CLOSE', source_bindings=[dict(path='runtime/quote.json', sha256='a' * 64)])
    if prior_kind == 'registry':
        prior.update(research_as_of=None, bear=None, base=None, bull=None,
            verification_scope='REGISTERED_RESEARCH_GAPS_ONLY', qualification='REGISTERED_RESEARCH_GAPS_ONLY')
        prior['scenario_validity']['status'] = 'not_ready'
    original = deepcopy(prior)
    monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(items=[deepcopy(prior)], blockers=[], source_bindings=deepcopy(prior['source_bindings'])))

    result = current_value_plan.load_current_value_action_plans(root, now=NOW, symbols=[symbol])
    plan = result['items'][0]
    analysis = plan['research_analysis']

    assert len(result['items']) == 1
    assert [plan[key] for key in ('bear', 'base', 'bull')] == [
        analysis['valuation'][key + '_value'] for key in ('bear', 'base', 'bull')]
    assert plan['research_as_of'] == analysis['research_as_of']
    assert plan['valuation_date'] == analysis['valuation_date']
    assert plan['model_id'] == analysis['review_binding']['model_context']['model_id']
    assert plan['model_version'] == analysis['valuation']['model_version']
    assert plan['valuation_input_version'] == analysis['input_descriptor_sha256']
    assert plan['profile_id'] == analysis['review_binding']['model_context']['profile_id']
    assert plan['current_quote_verified'] is True and plan['reference_close'] == '27.80'
    assert plan['market_trade_date'] == '2026-10-22'
    assert all(binding in plan['source_bindings'] for binding in analysis['source_bindings'])
    assert prior['source_bindings'][0] in plan['source_bindings']
    assert plan['formal_eligibility'] is plan['price_comparison_eligible'] is False
    assert plan['action_intent'] is plan['position_guidance'] is None
    assert plan['action'] == 'no_order'
    assert all(plan[key + '_trigger_price'] is None for key in ('entry', 'add', 'reduce', 'exit'))
    assert revalidate_current_value_plan(root, plan, now=NOW) == plan
    assert prior == original


@pytest.mark.parametrize('protected', ['newer', 'approved', 'held-action'])
def test_pending_analysis_does_not_replace_newer_or_admitted_decisions(registered, monkeypatch, protected):
    root, symbol, _, _ = registered
    prior = current_value_plan.load_current_value_action_plans(root, now=NOW)['items'][0]
    prior.pop('research_analysis')
    prior.pop('research_analysis_status')
    prior.update(bear='1', base='2', bull='3',
        verification_scope='HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL')
    if protected == 'newer':
        prior['research_as_of'] = '2026-10-22'
    elif protected == 'approved':
        prior.update(verification_scope='REPOSITORY_REPLAYED_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL',
            security_review_eligible=True, formal_eligibility=True)
    else:
        prior.update(candidate_action='HOLD', action_intent='HOLD')
    monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(items=[deepcopy(prior)], blockers=[], source_bindings=[]))

    actual = current_value_plan.load_current_value_action_plans(root, now=NOW, symbols=[symbol])['items'][0]

    assert all(actual[key] == value for key, value in prior.items())
    assert actual['research_analysis']['arithmetic_complete'] is True


@pytest.mark.parametrize('has_legacy', [False, True])
def test_selected_pending_source_drift_cannot_reuse_legacy_arithmetic(registered, monkeypatch, has_legacy):
    root, symbol, _, _ = registered
    pending = current_value_plan.load_current_value_action_plans(root, now=NOW)['items'][0]
    if has_legacy:
        prior = deepcopy(pending)
        prior.pop('research_analysis')
        prior.pop('research_analysis_status')
        prior.update(bear='1', base='2', bull='3',
            verification_scope='HASH_BOUND_PUBLISHED_RESEARCH_NOT_NEW_APPROVAL',
            current_quote_verified=True, reference_close='27.80', market_trade_date='2026-10-22')
        monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
            lambda *args, **kwargs: dict(items=[deepcopy(prior)], blockers=[], source_bindings=[]))
    (root / 'runtime/original.md').write_bytes(b'CHANGED_SOURCE')

    current = current_value_plan.load_current_value_action_plans(root, now=NOW, symbols=[symbol])
    assert all(plan['base'] is None for plan in current['items'])
    actual = revalidate_current_value_plan(root, pending, now=NOW)
    assert actual['bear'] is actual['base'] is actual['bull'] is None
    assert actual['formal_eligibility'] is actual['price_comparison_eligible'] is False
    assert actual['research_analysis']['arithmetic_complete'] is False
    assert actual['reference_close'] == ('27.80' if has_legacy else None)
    assert pending['base'] is not None


@pytest.mark.skipif(not os.environ.get('VALUE_PLAN_REPLAY_ROOT'), reason='Retained public runtime not supplied')
@pytest.mark.parametrize('symbol', ['600519', '600887'])
def test_retained_public_sources_reach_current_plan_without_admission(symbol):
    root = Path(os.environ['VALUE_PLAN_REPLAY_ROOT']).resolve()
    now = datetime.now(timezone.utc)
    plan = current_value_plan.load_current_value_action_plans(root, now=now, symbols=[symbol])['items'][0]
    analysis = plan['research_analysis']
    assert analysis['arithmetic_complete'] is True
    assert plan['research_as_of'] == analysis['research_as_of']
    assert plan['valuation_date'] == analysis['valuation_date']
    assert plan['valuation_input_version'] == analysis['input_descriptor_sha256']
    assert [plan[key] for key in ('bear', 'base', 'bull')] == [
        analysis['valuation'][key + '_value'] for key in ('bear', 'base', 'bull')]
    assert plan['formal_eligibility'] is plan['price_comparison_eligible'] is False
    assert plan['action_intent'] is plan['position_guidance'] is None
    assert plan['action'] == 'no_order'
    assert revalidate_current_value_plan(root, plan, now=now) == plan
    for binding in plan['source_bindings']:
        assert sha256_file(root / binding['path']) == binding['sha256']


def test_read_time_financial_original_tamper_clears_current_conditions(tmp_path, monkeypatch):
    _, explanation, _, _ = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    frozen = load_registered_value_action_plans(tmp_path, now=now)["items"][0]
    assert revalidate_current_value_plan(tmp_path, frozen, now=now) == frozen
    (tmp_path / "runtime/fact.txt").write_bytes(b"changed financial original")
    blocked = revalidate_current_value_plan(tmp_path, frozen, now=now)
    assert blocked["signal_state"] == "BLOCKED"
    assert blocked["bear"] is None and blocked["reference_close"] is None
    assert blocked["action_intent"] is None
    assert blocked["entry_condition"] is None and blocked["formal_eligibility"] is False
    assert "CURRENT_VALUE_PLAN_CHANGED_OR_STALE" in blocked["blockers"]
    assert frozen["bear"] is not None


def test_read_time_revalidation_covers_action_and_admission_fields(tmp_path, monkeypatch):
    _, explanation, _, _ = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    frozen = load_registered_value_action_plans(tmp_path, now=now)["items"][0]
    tampered = {**frozen, "formal_eligibility": not frozen["formal_eligibility"]}

    blocked = revalidate_current_value_plan(tmp_path, tampered, now=now)

    assert blocked["signal_state"] == "STALE"
    assert blocked["formal_eligibility"] is False
    assert blocked["action_intent"] is None
    assert "CURRENT_VALUE_PLAN_CHANGED_OR_STALE" in blocked["blockers"]


@pytest.mark.parametrize('verified,price,expected', [
    (True, '100.50', '100.50'), (False, '100.50', None),
    (True, 'NaN', None), (True, '-1', None), (True, None, None),
])
def test_stale_economics_keeps_only_independently_rebuilt_quote(tmp_path, monkeypatch, verified, price, expected):
    frozen = dict(schema_version='value-action-plan-v1', symbol='600519',
                  current_quote_verified=True, reference_close='999', market_trade_date='2026-10-20',
                  bear='80', base='100', bull='120', formal_eligibility=True,
                  entry_condition=dict(price='90'), blockers=[])
    rebuilt = dict(symbol='600519', current_quote_verified=verified, reference_close=price,
                   market_trade_date='2026-10-21', source_bindings=[dict(path='TEST_ONLY.json', sha256='test')])
    monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(items=[rebuilt], blockers=[], source_bindings=[]))
    actual = revalidate_current_value_plan(tmp_path, frozen, now=datetime.now(timezone.utc))
    assert actual['reference_close'] == expected
    assert actual['current_quote_verified'] is (expected is not None)
    assert actual['price_comparison_eligible'] is False
    assert actual['formal_eligibility'] is False
    assert actual['entry_condition'] is None and actual['bear'] is None
    if expected is not None:
        assert actual['market_trade_date'] == '2026-10-21'
        assert actual['reference_price_scope'] == 'CURRENT_VERIFIED_CLOSE_NOT_VALUATION_COMPARABLE'
    assert frozen['reference_close'] == '999'
