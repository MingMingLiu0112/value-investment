"""TEST_ONLY native signed securities chain; no account or real-company approval."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json

import pytest

from test_d2_conditional_shared_service import synthetic_chain
from test_p7_signed_review_workflow import _complete_signed_case, _registered_policy_fixture
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
from value_investment_agent.application.decision.current_value_plan import (
    load_current_value_action_plans, revalidate_current_value_plan,
)
from value_investment_agent.application.decision.value_action_plan import CoreValuePublicReviews
from value_investment_agent.application.decision.public_strategy_assessment import (
    project_actionable_evaluation, summarize_actionable_evaluations,
)

NOW=datetime.fromisoformat('2026-09-21T19:00:00+08:00')


@pytest.fixture
def native_public(synthetic_chain,monkeypatch):
    root=synthetic_chain[0]
    restored,_,_=_complete_signed_case(synthetic_chain,monkeypatch)
    _registered_policy_fixture(root,restored)
    with _use_test_trust_registry(root/'TEST_ONLY-combined-trust-registry.json'):
        yield root,restored


def item(plan):
    return dict(symbol=plan['symbol'],name='TEST_ONLY',strategy='CORE_VALUE',price_action_plan=plan)


def test_native_public_securities_review_without_private_account(native_public):
    root,restored=native_public
    with CoreValuePublicReviews(root,now=NOW) as reviews:
        result=load_current_value_action_plans(root,now=NOW,symbols=[restored.recommendation.symbol],public_reviews=reviews)
        assert len(result['items'])==1,result['blockers']
        plan=result['items'][0]
        assert plan['formal_eligibility'] is True,plan
        assert plan['entry_condition']['triggered'] is True
        projected=project_actionable_evaluation(item(plan),core_reviews=reviews,now=NOW)
        assert projected['decision_action']=='CONDITIONAL_MANUAL_REVIEW',projected
        assert projected['public_action_intent']=='OPEN'
        assert projected['personal_action_review']['state']=='UNASSESSABLE'
        assert projected['eligibility'] is False and projected['review_quantity'] is None
        assert projected['position_range'] is projected['available_cash_impact'] is None
        assert projected['action']=='no_order'
        summary=summarize_actionable_evaluations([item(plan)],core_reviews=reviews,now=NOW)
        assert summary['evaluated_count']==summary['conditional_review_count']==1
        assert summary['unassessable_count']==summary['operation_eligible_count']==0
        assert summary['conclusion']=='PUBLIC_CONDITIONAL_REVIEWS_AVAILABLE'


def test_mixed_public_review_is_visible_but_not_marketwide_complete(native_public):
    root, restored = native_public
    with CoreValuePublicReviews(root, now=NOW) as reviews:
        plan = load_current_value_action_plans(root, now=NOW,
            symbols=[restored.recommendation.symbol], public_reviews=reviews)['items'][0]
        summary = summarize_actionable_evaluations([
            item(plan), dict(symbol='000544', strategy='CORE_VALUE')],
            core_reviews=reviews, now=NOW)
        assert summary['conditional_review_count'] == summary['evaluated_count'] == 1
        assert summary['unassessable_count'] == 1
        assert summary['conclusion'] == 'INCOMPLETE_EVALUATION'
        assert summary['scope'] == 'PUBLISHED_COMPANIES_ONLY'
        assert summary['items'][0]['decision_action'] == 'CONDITIONAL_MANUAL_REVIEW'
        assert summary['operation_eligible_count'] == 0


@pytest.mark.parametrize('mutation', [
    'json_proof', 'foreign_request', 'closed', 'next_day', 'plan', 'pointer', 'source',
    'typed_recommendation', 'trust_registry',
])
def test_native_public_review_rejects_changed_or_non_native_proof(native_public, mutation):
    root, restored = native_public
    with CoreValuePublicReviews(root, now=NOW) as reviews:
        plan = load_current_value_action_plans(root, now=NOW,
            symbols=[restored.recommendation.symbol], public_reviews=reviews)['items'][0]
        context, now = reviews, NOW
        if mutation == 'json_proof':
            context = dict(verified=True, formal_eligibility=True, action_intent='OPEN')
        elif mutation == 'foreign_request':
            context = CoreValuePublicReviews(root, now=NOW)
        elif mutation == 'closed':
            reviews.__exit__()
        elif mutation == 'next_day':
            now += timedelta(days=1)
        elif mutation == 'plan':
            plan = deepcopy(plan)
            plan['reference_close'] = '0.01'
        elif mutation == 'pointer':
            path = root / 'config/current-trial-workbook.json'
            path.write_bytes(path.read_bytes() + b'\n')
        elif mutation == 'source':
            ref = next(ref for ref in plan['source_bindings'] if ref['path'].startswith('runtime/'))
            path = root / ref['path']
            path.write_bytes(path.read_bytes() + b'\n')
        elif mutation == 'typed_recommendation':
            # Mutating the retained typed object must not survive fresh native replay.
            record = reviews._native[plan['symbol']]
            record['recommendation'] = '0' * 64
        elif mutation == 'trust_registry':
            path = root / 'TEST_ONLY-combined-trust-registry.json'
            path.write_text('{}', encoding='utf-8')
        result = project_actionable_evaluation(item(plan), core_reviews=context, now=now)
        assert result['decision_action'] == 'UNASSESSABLE', result
        assert result['eligibility'] is False and result['review_quantity'] is None
        assert result['action'] == 'no_order'


def _publish_test_daily(root):
    """Add TEST_ONLY discovery display data, keeping the native signed workbench."""
    from value_investment_agent.application.product.publication_chain import load_current_chain
    from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet
    from value_investment_agent.application.product.public_snapshot import publish_snapshot

    def write(path, value):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        target.write_bytes(raw)
        return dict(path=path, sha256=hashlib.sha256(raw).hexdigest())

    chain = load_current_chain(root)
    symbol = chain['model']['snapshot']['companies'][0]['symbol']
    ext = dict(
        value_discovery_report=dict(status='RESEARCH_LEADS_ONLY', lead_symbols=[symbol]),
        m2_quality_diagnostic=dict(schema_version='m2-quality-diagnostic-v1'),
        market_regime_observation=dict(schema_version='market-regime-observation-v1', status='UNKNOWN'),
        hotspot_watch_queue=dict(schema_version='hotspot-watch-queue-v1', items=[]),
        value_research_queue=dict(schema_version='value-research-queue-v1', action='no_order',
            admission='RESEARCH_QUEUE_ONLY', as_of=NOW.date().isoformat(), entries=[]))
    receipt = write('runtime/TEST_ONLY-public-screen-receipt.json', dict(
        schema_version='m2-opportunity-discovery-v2', universe=dict(records=[dict(symbol=symbol)])))
    for key, value in ext.items():
        stored = value if key != 'value_discovery_report' else dict(value,
            schema_version='m2-opportunity-report-v1', semantic_content=value,
            receipt_binding=receipt, deduplicated_lead_count=1,
            data_health=dict(universe_count=1))
        chain['model'].setdefault('product_extensions', {})[key] = write(
            f'runtime/TEST_ONLY-public-{key}.json', stored)
    chain['model']['snapshot']['companies'][0]['action'] = 'no_order'
    chain['handoff']['snapshot'] = deepcopy(chain['model']['snapshot'])
    chain['handoff']['read_model_binding'] = write('runtime/TEST_ONLY-public-model.json', chain['model'])
    chain['sources']['publication_input_binding'] = write('runtime/TEST_ONLY-public-handoff.json', chain['handoff'])
    sources = write('runtime/TEST_ONLY-public-sources.json', chain['sources'])
    chain['receipt'].update(source_bindings_path=sources['path'], source_bindings_sha256=sources['sha256'])
    receipt = write('runtime/TEST_ONLY-public-receipt.json', chain['receipt'])
    chain['pointer']['current_publication'].update(receipt=receipt['path'], receipt_sha256=receipt['sha256'])
    chain['state']['content']['extensions'] = ext
    chain['pointer']['daily_product_state_binding'] = write('runtime/TEST_ONLY-public-state.json', chain['state'])
    write('config/current-trial-workbook.json', chain['pointer'])
    packet = build_daily_public_packet(root, generated_at=NOW)
    assert packet['packet_status'] == 'CURRENT', packet.get('chain_error')
    assert packet['value_price_conditions'][symbol]['formal_eligibility'] is True
    binding = write('runtime/TEST_ONLY-public-packet.json', packet)
    publish_snapshot(root, packet, root / binding['path'], published_at=NOW)


def test_native_public_review_existing_daily_and_detail_api(native_public, monkeypatch):
    from fastapi.testclient import TestClient
    from web_api.conftest import TEST_BOOTSTRAP, open_session
    from value_investment_agent.presentation.web_api import app as api_module, private_routes
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateStoreUnavailable

    root, restored = native_public
    _publish_test_daily(root)

    class TestClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)

    def no_private(**kwargs):
        raise PrivateStoreUnavailable('TEST_ONLY no personal account')

    monkeypatch.setattr(api_module, 'datetime', TestClock)
    monkeypatch.setattr(private_routes, 'resolve_private_root', no_private)
    client = TestClient(api_module.create_app(root, port=8791, bootstrap_secret=TEST_BOOTSTRAP),
        base_url='http://127.0.0.1:8791', client=('127.0.0.1', 51000))
    client.headers.update({'host': '127.0.0.1:8791', 'origin': 'http://127.0.0.1:8791'})
    client.headers['x-local-session'] = open_session(client)
    before = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('config', 'runtime') for p in (root / folder).rglob('*') if p.is_file()}
    daily = client.get('/api/v1/daily-decisions').json()
    evaluation = daily['actionable_evaluation']
    assert evaluation['conditional_review_count'] == evaluation['evaluated_count'] == 1, daily
    assert evaluation['operation_eligible_count'] == 0
    assert evaluation['items'][0]['public_action_intent'] == 'OPEN'
    detail = client.get(f'/api/v1/decisions/{restored.recommendation.symbol}').json()
    result = detail['strategy_evaluation']
    assert result['decision_action'] == 'CONDITIONAL_MANUAL_REVIEW', detail
    assert result['eligibility'] is False and result['review_quantity'] is None
    assert result['position_range'] is result['available_cash_impact'] is None
    assert result['action'] == 'no_order'
    assert 'core_reviews' not in json.dumps(detail)
    after = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ('config', 'runtime') for p in (root / folder).rglob('*') if p.is_file()}
    assert before == after


@pytest.mark.parametrize('change', ['unchanged', 'source_bytes', 'reload_failure'])
def test_attached_analysis_closure_is_independent_from_domain_inputs(native_public, monkeypatch, change):
    from value_investment_agent.application.decision import current_value_plan
    from value_investment_agent.application.product import research_draft

    root, restored = native_public
    symbol = restored.recommendation.symbol
    source = root / 'runtime/TEST_ONLY-attached-analysis-source.json'
    source.write_text('{"scope":"TEST_ONLY_ANALYSIS_NOT_ADMISSION"}', encoding='utf-8')
    binding = dict(path=source.relative_to(root).as_posix(), sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    analysis = dict(symbol=symbol, status='TEST_ONLY_BOUND_ANALYSIS', arithmetic_complete=True,
        action='no_order', source_bindings=[binding], blockers=[])
    # Only the additional analysis is synthetic; native G3/policy/quote replay is unchanged.
    monkeypatch.setattr(current_value_plan, 'load_current_research_analysis', lambda *args, **kwargs: deepcopy(analysis))
    monkeypatch.setattr(research_draft, 'load_current_research_analysis', lambda *args, **kwargs: deepcopy(analysis))
    with CoreValuePublicReviews(root, now=NOW) as reviews:
        plan = load_current_value_action_plans(root, now=NOW, symbols=[symbol], public_reviews=reviews)['items'][0]
        assert binding not in reviews._native[symbol]['sources']
        assert binding in reviews._native[symbol]['analysis_sources']
        if change == 'source_bytes':
            source.write_bytes(source.read_bytes() + b'\n')
        elif change == 'reload_failure':
            monkeypatch.setattr(research_draft, 'load_current_research_analysis', lambda *args, **kwargs:
                dict(status='SOURCE_OR_REPLAY_UNAVAILABLE', source_bindings=[]))
        result = project_actionable_evaluation(item(plan), core_reviews=reviews, now=NOW)
        assert result['decision_action'] == ('CONDITIONAL_MANUAL_REVIEW' if change == 'unchanged' else 'UNASSESSABLE')
        assert result['eligibility'] is False and result['review_quantity'] is None
        assert result['action'] == 'no_order'
