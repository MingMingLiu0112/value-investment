"""TEST_ONLY journal closure with signed isolated research and the real v3 builder."""
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_d2_conditional_shared_service import synthetic_chain
from test_p7_signed_review_workflow import _complete_signed_case, _registered_policy_fixture
from test_advisory_decision_recommendation_v3 import _entry, _consistency
from test_private_ips_policy import full_policy
from test_portfolio_risk_assessment import _attributes
from test_independent_hotspot_signed_pipeline import pipeline
from test_hotspot_current_price_case import NOW as HOTSPOT_NOW
from value_investment_agent.application.portfolio import personal_entry_thesis as thesis
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio.held_continuity import (
    evaluate_owned_held_advisory, owned_held_action, SELL_REVIEW_SCHEMA,
)
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService,
)
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_artifacts import ResearchArtifactIdentity
from value_investment_agent.research_artifacts import ResearchArtifactEnvelope, StoredResearchArtifact
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry


@pytest.mark.parametrize('transport', ['service', 'authenticated_route'])
def test_signed_research_open_owned_four_actions_manual_sales_restart(synthetic_chain, monkeypatch, transport):
    root = synthetic_chain[0]
    restored, _, _ = _complete_signed_case(synthetic_chain, monkeypatch)
    assert restored.recommendation.recommendation_action == 'BUY_CANDIDATE'
    _registered_policy_fixture(root, restored)
    symbol = restored.recommendation.symbol
    opening = datetime.fromisoformat('2026-09-18T20:00:00+08:00')
    clock = [opening]
    now = datetime.fromisoformat('2026-09-21T20:00:00+08:00')
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0] if tz is None else clock[0].astimezone(tz)

    opening = Clock.fromisoformat(opening.isoformat())
    now = Clock.fromisoformat(now.isoformat())
    clock[0] = opening
    from value_investment_agent.application.portfolio import private_portfolio_service as journal_module
    monkeypatch.setattr(journal_module, 'datetime', Clock)
    service = PrivatePortfolioService(PrivateJournal(root / 'TEST_ONLY-owned/journal.jsonl'),
        clock=lambda: clock[0])
    service.initialize(dict(idempotency_key='TEST_ONLY-init', expected_revision=0,
        account_scope='TEST_ONLY_OWNED_CLOSURE', as_of='2026-09-18', cash_cny='10000',
        holdings=[], sleeve_allocations={}, policy={}, confirmed_at=opening.isoformat(),
        confirmation_note='TEST_ONLY isolated account'))
    policy = full_policy()
    policy.update(effective_date='2026-09-18')
    policy['sleeves']['CORE_VALUE']['cash_cny'] = '7000'
    _, prepared = service.prepare_policy(dict(idempotency_key='TEST_ONLY-ips', expected_revision=1, policy=policy))
    service.confirm_policy(dict(idempotency_key='TEST_ONLY-ips-confirm', expected_revision=2,
        prepared_record_sha256=prepared, confirmed_at=opening.isoformat(), confirmation_note='TEST_ONLY IPS'))

    def fill(side, quantity, key):
        fields = dict(transaction_id=key, side=side, sleeve='CORE_VALUE', symbol=symbol,
            exchange='SSE', quantity=str(quantity), price_cny='5', fees_cny='0',
            trade_date=clock[0].date().isoformat())
        if side == 'BUY':
            fields.update(next_sell_session='2026-09-21', trading_unit='100')
        _, digest = service.prepare_fill(dict(idempotency_key=key, expected_revision=len(service.records()), fill=fields))
        return service.confirm_fill(dict(idempotency_key=key+'-confirmed', expected_revision=len(service.records()),
            prepared_record_sha256=digest, confirmed_at=clock[0].isoformat(), confirmation_note='TEST_ONLY manual fill'))

    _, buy_hash = fill('BUY', 200, 'TEST_ONLY-open')
    repository = InMemoryResearchArtifactRepository()

    from value_investment_agent import research_artifact_repository as repository_module
    monkeypatch.setattr(repository_module, 'datetime', Clock)

    def save(value):
        kind, payload = artifact_payload(value)
        return repository.save_object(value, identity=ResearchArtifactIdentity(scope_type='security',
            scope_key=symbol, artifact_type=kind, schema_version=payload['schema_version'],
            as_of=getattr(value, 'as_of', value.entry_date if hasattr(value, 'entry_date') else opening.date()),
            available_at=clock[0]), run_id='TEST_ONLY-owned-closure')

    entry = save(replace(_entry(), symbol=symbol, entry_date=opening.date(), confirmed_at=opening,
        entry_price=Decimal('5')))
    initial = save(replace(_consistency('CONSISTENT'), symbol=symbol, as_of=opening.date()))
    api = thesis.PersonalEntryThesisService(service.journal, repository=repository)
    request = dict(idempotency_key='TEST_ONLY-thesis', expected_revision=len(service.records()),
        fill_record_sha256=buy_hash, binding_mode='CONTEMPORANEOUS', read_and_confirmed=True,
        confirmation_note='TEST_ONLY original rationale', entry_artifact_id=entry.artifact_id,
        consistency_artifact_id=initial.artifact_id)
    receipt = api.confirm(request, repository_root=root, authenticated_subject='LOCAL_OPERATOR', now=opening)
    assert api.confirm(request, repository_root=root, authenticated_subject='LOCAL_OPERATOR', now=opening) == receipt
    clock[0] = now
    monkeypatch.setattr(thesis, '_application_repository', lambda *a, **k: repository)
    # Isolated source adapters provide explicit test observations. Research,
    # signatures, workbench replay, advisory builder, risk engine and ledger are real.
    attribute = _attributes(symbol=symbol).as_policy()
    monkeypatch.setattr(projection, '_verified_attributes', lambda *a, **k: [attribute])
    monkeypatch.setattr(projection, '_verified_prices', lambda *a, **k: {
        symbol: dict(price_cny='5', trade_date=now.date().isoformat(), price_admitted=True,
                     current_pit=True, scope='TEST_ONLY_SOURCE_ADAPTER', bundle_sha256='b'*64)})
    allocation_source = projection._allocations_payload
    def isolated_risk_evidence(replayed, sellable_as_of):
        return [{**row, 'committed_risk_cny': '100',
                 'evidence_ref': 'TEST_ONLY_EXPLICIT_RISK_EVIDENCE_NOT_PRODUCTION'}
                for row in allocation_source(replayed, sellable_as_of)]
    monkeypatch.setattr(projection, '_allocations_payload', isolated_risk_evidence)
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.presentation.web_api.local_auth import LocalOperatorSession
    monkeypatch.setattr(private_routes, 'resolve_private_root', lambda **k: service.journal.path)
    monkeypatch.setattr(private_routes, 'datetime', Clock)
    app = FastAPI()
    secret = 'TEST_ONLY-owned-route-' + 'x' * 40
    private_routes.register_private_routes(app, root,
        sessions=LocalOperatorSession(bootstrap_secret=secret), port=8793)
    client = TestClient(app, base_url='http://127.0.0.1:8793', client=('127.0.0.1', 51000))
    client.headers['origin'] = 'http://127.0.0.1:8793'
    route = '/api/v1/private/portfolio/held-continuity/sell-review'

    def reconcile(key):
        service.reconcile(dict(idempotency_key=key, expected_revision=len(service.records()),
            reconciled_at=clock[0].isoformat(), confirmation_note='TEST_ONLY external statement',
            account_evidence=dict(id=key, kind='broker_statement')))

    reconcile('TEST_ONLY-reconcile')
    trust = root / 'TEST_ONLY-combined-trust-registry.json'
    with _use_test_trust_registry(trust):
        for index, (status, action) in enumerate((('CONSISTENT', 'HOLD'), ('FULFILLED', 'ADD'),
                ('WEAKENED', 'REDUCE'), ('BROKEN', 'EXIT'))):
            clock[0] = now + timedelta(seconds=index)
            save(replace(_consistency(status), symbol=symbol, as_of=now.date(),
                         review_id='TEST_ONLY-current-'+status))
            context = thesis.owned_entry_context(records=service.records(), symbol=symbol,
                sleeve='CORE_VALUE', authenticated_subject='LOCAL_OPERATOR', as_of=clock[0])
            risk = projection.review_private_risk_rehearsal(service.journal, generated_at=clock[0],
                repository_root=root, today=now.date(), core_request=dict(symbol=symbol, entry_price_cny='5',
                    entry_slippage_cny='0', buy_fee_fraction='0', minimum_buy_fee_cny='1', lot_size=100,
                    max_trade_notional_cny='501', quote_as_of=now.date().isoformat(),
                    available_at=now.isoformat(), valid_until=(now+timedelta(hours=1)).isoformat(),
                    liquidity_verified=True, limit_up=False, limit_down=False))
            position = service._positions(service._replay(service.records()).state, now.date())[0]['sleeves'][0]
            plan = dict(symbol=symbol, strategy='CORE_VALUE', schema_version='value-action-plan-v1',
                action='no_order', action_intent='ADD', add_condition=dict(triggered=True), blockers=[])
            kwargs = {}
            if action in {'REDUCE', 'EXIT'}:
                kwargs['sell_review_request'] = dict(schema_version=SELL_REVIEW_SCHEMA, action='no_order',
                    expected_revision=len(service.records()), account_scope=context['account_scope'],
                    symbol=symbol, exchange='SSE', sleeve='CORE_VALUE', requested_action=action,
                    requested_quantity=100, entry_thesis_record_sha256=context['entry_thesis_record_sha256'],
                    read_and_confirmed=True)
            before = service.journal.path.read_bytes()
            result = owned_held_action(context=context, plan=plan, risk=risk, sleeve_position=position,
                advisory_provider=lambda: evaluate_owned_held_advisory(root, context=context, plan=plan,
                    now=clock[0]), **kwargs)
            assert result['decision_action'] == action, result['blockers']
            assert result['namespace'] == 'TEST_ONLY' and result['broker_execution_permission'] is False
            assert service.journal.path.read_bytes() == before
            if action in {'REDUCE', 'EXIT'} and transport == 'authenticated_route':
                payload = kwargs['sell_review_request']
                client.headers.pop('x-local-session', None)
                assert client.post(route, json=payload).status_code == 401
                unlocked = client.post('/api/v1/private/session/unlock', json={'bootstrap_token': secret})
                assert unlocked.status_code == 200, unlocked.text
                client.headers['x-local-session'] = unlocked.json()['token']
                stale = client.post(route, json={**payload, 'expected_revision': payload['expected_revision']-1})
                assert stale.status_code == 409, stale.text
                response = client.post(route, json=payload)
                assert response.status_code == 200, response.text
                body = response.json()
                assert body['status'] == 'CONDITIONAL_MANUAL_REVIEW', body['actionable_decision']['blockers']
                decision = body['actionable_decision']
                assert decision['decision_action'] == action and decision['review_quantity'] == 100
                assert body['revision'] == payload['expected_revision'] and body['request'] == payload
                assert body['ledger_written'] is body['broker_execution_permission'] is False
                assert response.headers['cache-control'] == 'no-store'
                assert service.journal.path.read_bytes() == before
            if action in {'REDUCE', 'EXIT'}:
                fill('SELL', 100, 'TEST_ONLY-'+action)
                reconcile('TEST_ONLY-reconcile-'+action)
                service = PrivatePortfolioService(PrivateJournal(service.journal.path), clock=lambda: clock[0])
                replay = service._replay(service.records())
                assert sum(lot.quantity for lot in replay.state.lots) == (100 if action == 'REDUCE' else 0)
        assert service._replay(service.records()).state.cash_cny == Decimal('10000')
        resolved = thesis.resolve_personal_entry_thesis(records=service.records(),
            account_scope='TEST_ONLY_OWNED_CLOSURE', expected_revision=len(service.records()),
            as_of=clock[0], authenticated_subject='LOCAL_OPERATOR')
        assert resolved['items'][0]['remaining_quantity'] == '0'
        assert resolved['items'][0]['current_binding']['record_sha256'] == receipt[1]
    client.close()


@pytest.mark.parametrize('status,expected', [('CONSISTENT', 'HOLD'), ('FULFILLED', 'ADD_CANDIDATE'),
    ('WEAKENED', 'TRIM_CANDIDATE'), ('BROKEN', 'SELL_CANDIDATE')])
def test_hotspot_owned_adapter_uses_signed_independent_sources_without_value_g3(pipeline, monkeypatch, status, expected):
    root, plan = pipeline['root'], pipeline['plan']
    entry = replace(_entry(), symbol='600519', entry_date=HOTSPOT_NOW.date(), confirmed_at=HOTSPOT_NOW)
    review = replace(_consistency(status), symbol='600519', as_of=HOTSPOT_NOW.date())
    def store(value, identifier):
        kind, payload = artifact_payload(value)
        return StoredResearchArtifact(artifact_id=identifier, created_at=HOTSPOT_NOW,
            envelope=ResearchArtifactEnvelope.build(identity=ResearchArtifactIdentity(
                scope_type='security', scope_key='600519', artifact_type=kind,
                schema_version=payload['schema_version'], as_of=HOTSPOT_NOW.date(), available_at=HOTSPOT_NOW),
                payload=payload, run_id='TEST_ONLY-owned-hotspot'))
    original, current = store(entry, 'TEST_ONLY-entry'), store(review, 'TEST_ONLY-consistency')
    monkeypatch.setattr(thesis, '_application_repository', lambda *a, **k: thesis._CandidateRepository([original, current]))
    monkeypatch.setattr(thesis, 'registered_entry_workbenches', lambda *a, **k:
        pytest.fail('Independent hotspot must not require value G3'))
    context = dict(namespace='TEST_ONLY', entry_artifact=original, entry_thesis=entry,
                   investment_consistency_review=review)
    action, blockers, evidence = evaluate_owned_held_advisory(root, context=context, plan=plan,
        now=HOTSPOT_NOW, allow_test_only=True)
    assert action == expected and not blockers
    assert evidence['independent_admission']['namespace'] == 'TEST_ONLY'
    with pytest.raises(ValueError):
        evaluate_owned_held_advisory(root, context=context, plan=plan, now=HOTSPOT_NOW)
    event = next(row for row in pipeline['gates'] if row['gate'] == 'event_risk')
    event['status'] = 'UNKNOWN'
    pipeline['publish']()
    with pytest.raises(ValueError, match='INDEPENDENT_ADMISSION_REQUIRED'):
        evaluate_owned_held_advisory(root, context=context, plan=plan,
            now=HOTSPOT_NOW, allow_test_only=True)
