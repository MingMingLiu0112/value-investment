"""Isolated signed fixtures; real retained-source replay, producer and risk rules."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
from decimal import Decimal
import hashlib
import json

import pytest

from test_private_risk_preview import actual_contract_preview as base_account, register_hotspot_contract, NOW, ASSUMPTIONS
from test_private_risk_preview import simulated_hotspot_machine_validation
from test_hotspot_price_behavior import rows, retest_rows
from test_advisory_decision_recommendation_v3 import _entry, _consistency
from value_investment_agent.application.portfolio import private_risk_preview as preview
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.application.portfolio import personal_entry_thesis as personal
from value_investment_agent.application.hotspot.price_action_case import project_current_price_action_plan
from value_investment_agent.application.hotspot.independent_price_conditions import project_independent_price_condition
from value_investment_agent.infrastructure.hotspot import current_price_case as retained
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent import research_artifact_repository as repositories
from value_investment_agent.research_artifacts import ResearchArtifactIdentity
from value_investment_agent.research_artifact_codecs import artifact_payload


class ClockMeta(type):
    def __instancecheck__(cls, value):
        return isinstance(value, type(NOW))


class FixtureClock(type(NOW), metaclass=ClockMeta):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz is None else NOW.astimezone(tz)


@pytest.fixture
def actual_contract_preview(tmp_path, monkeypatch, request):
    from value_investment_agent.application.portfolio import private_portfolio_service as journal
    monkeypatch.setattr(journal, 'datetime', FixtureClock)
    account = base_account.__wrapped__(tmp_path, monkeypatch, request)
    account[0]._clock = lambda: NOW
    return account


def retained_recovery(root, monkeypatch):
    directory = root / 'runtime/hotspot-current-price-cases/isolated-add'
    directory.mkdir(parents=True)
    # Enough confirmed daily swings/upper space, then a completed retest recovery.
    minutes = []
    for day, row in enumerate(rows([10, 11, 18, 11, 10, 11, 20, 12, 11, 12, 22, 13]), 1):
        for clock in SESSION_TIMES['60m']:
            minutes.append({**row, 'time': f'2026-10-{day:02} {clock}'})
    for index, row in enumerate(retest_rows()):
        minutes.append({**row, 'time': f'2026-10-{13 + index // 4:02} {SESSION_TIMES["60m"][index % 4]}'})
    for row in minutes:
        for field in ('open', 'close', 'high', 'low'):
            row[field] = str(Decimal(row[field]) / 100)
    quarters = []
    for index, row in enumerate(minutes):
        for clock in SESSION_TIMES['15m'][(index % 4) * 4:(index % 4 + 1) * 4]:
            quarters.append({**row, 'time': row['time'][:10] + ' ' + clock,
                'volume': str(Decimal(row['volume']) / 4), 'amount': str(Decimal(row['amount']) / 4)})
    sources = {}
    for period, data, scale in [('60m', minutes, '60'), ('15m', quarters, '15')]:
        path = directory / f'sina-{period}.jsonp'
        raw = ('=(' + json.dumps([{**r, 'day': r['time']} for r in data]) + ');').encode()
        path.write_bytes(raw)
        sources[period] = dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(raw).hexdigest(),
            fetched_at=NOW.isoformat(), adjustment='UNADJUSTED', scope='SINGLE_PROVIDER_CURRENT_OBSERVATION',
            source_url=f'https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData?symbol=sz300364&scale={scale}&ma=no')
    sources['daily'] = {**sources['60m'], 'scope': 'DERIVED_FROM_SINA_60M_NOT_INDEPENDENT_DAILY_SOURCE'}
    bundle = root / 'runtime/isolated-bundle.json'
    bundle.write_text(json.dumps({'finished_at': NOW.isoformat()}), encoding='utf-8')
    # Quote-provider boundary only. All minute originals, calculations, case hash
    # and producer rules below are replayed by the production loader.
    def quote(root, path, sha, symbol, as_of, price, now):
        assert hashlib.sha256((root / path).read_bytes()).hexdigest() == sha
        return dict(status='VERIFIED_DUAL_SOURCE_CLOSE', price=price, bundle_path=path,
            bundle_sha256=sha, evidence_refs=['isolated-quote-provider'], next_session='2026-10-15',
            limit_up=False, limit_down=False)
    monkeypatch.setattr(retained, '_b1', quote)
    case = retained._build(root, '300364', date(2026, 10, 14), sources,
        bundle.relative_to(root).as_posix(), hashlib.sha256(bundle.read_bytes()).hexdigest(), NOW)
    path = directory / 'case.json'
    path.write_text(json.dumps(case), encoding='utf-8')
    loaded = retained.load_current_price_case(root=root, symbol='300364', case_path=path, now=NOW)
    return loaded


def bind_entry(service, root, monkeypatch):
    monkeypatch.setattr(repositories, 'datetime', FixtureClock)
    repository = repositories.InMemoryResearchArtifactRepository()
    entry = replace(_entry(), symbol='300364', entry_date=NOW.date(), entry_price=Decimal('0.125'), confirmed_at=NOW)
    review = replace(_consistency('FULFILLED'), symbol='300364', as_of=NOW.date())
    artifacts = []
    for obj in (entry, review):
        kind, payload = artifact_payload(obj)
        artifacts.append(repository.save_object(obj, identity=ResearchArtifactIdentity(
            scope_type='security', scope_key='300364', artifact_type=kind,
            schema_version=payload['schema_version'], as_of=NOW.date(), available_at=NOW),
            run_id='isolated-private-add'))
    personal.PersonalEntryThesisService(service.journal, repository=repository).confirm(dict(
        idempotency_key='isolated-thesis', expected_revision=len(service.records()),
        fill_record_sha256=service.records()[-1]['record_sha256'],
        binding_mode='CONTEMPORANEOUS', read_and_confirmed=True,
        confirmation_note='Isolated owned-entry regression', entry_artifact_id=artifacts[0].artifact_id,
        consistency_artifact_id=artifacts[1].artifact_id),
        repository_root=root, authenticated_subject='LOCAL_OPERATOR', now=NOW)
    monkeypatch.setattr(personal, '_application_repository', lambda *a, **k: repository)
    return repository


@pytest.mark.parametrize('fault', [None, 'no_holding', 'other_sleeve', 'source', 'admission',
    'test_release', 'capacity', 'no_thesis', 'broken_thesis', 'fees',
    'add_rule_drift', 'behavior_drift', 'price_drift', 'open_text_drift', 'machine_proof'])
def test_producer_watch_recovery_consumed_only_by_owned_private_add(actual_contract_preview, tmp_path, monkeypatch, fault,
        simulated_hotspot_machine_validation):
    service, legacy, _, packet, _, _ = actual_contract_preview
    if fault == 'machine_proof':
        from value_investment_agent.application.hotspot import independent_validation
        monkeypatch.setattr(independent_validation, 'verify_strategy_admission_sources',
            simulated_hotspot_machine_validation['original_verifier'])
    case = retained_recovery(tmp_path, monkeypatch)
    produced = project_current_price_action_plan(case)
    produced.update(case_path=case['case_path'], case_sha256=case['case_sha256'], research_version='contract')
    assert produced['action_intent'] == produced['signal_state'] == 'WATCH'
    assert produced['add_condition']['observed'] is True
    assert produced['entry_condition']['observed'] is False
    assert produced['opportunity_quality']['structure_tier'] == 'ACTIVE_ONLY'
    legacy.clear()
    legacy.update(produced)
    register_hotspot_contract(tmp_path, legacy, namespace='TEST_ONLY' if fault == 'test_release' else 'ACTUAL',
        case_binding=dict(path=case['case_path'], sha256=case['case_sha256']))
    packet['price_conditions']['items'][0]['price_action_plan'] = deepcopy(legacy)
    def current(*args, **kwargs):
        replay = retained.load_current_price_case(root=tmp_path, symbol='300364',
            case_path=tmp_path / case['case_path'], expected_sha256=case['case_sha256'], now=kwargs['now'])
        plan = project_current_price_action_plan(replay)
        return {'items': [{'symbol': '300364', 'price_action_plan': {**plan,
            'case_path': replay['case_path'], 'case_sha256': replay['case_sha256'], 'research_version': 'contract'}}]}
    monkeypatch.setattr(preview, 'load_price_conditions', current)
    if fault in {'add_rule_drift', 'behavior_drift', 'price_drift', 'open_text_drift'}:
        def altered_projection(*args, **kwargs):
            result = project_independent_price_condition(*args, **kwargs)
            if fault == 'add_rule_drift':
                result['add_condition']['price'] = '0.12'
                result['conditional_action_rules']['ADD']['price'] = '0.12'
            elif fault == 'behavior_drift':
                result['price_behavior']['pullback_recovery']['evidence']['level'] = '0.12'
            elif fault == 'price_drift':
                result['current_reference_price'] = '0.126'
            else:
                result['conditional_action_rules']['OPEN']['rule'] = 'unrecognized replacement'
            return result
        monkeypatch.setattr(preview, 'project_independent_price_condition', altered_projection)
    # Public/default projection still requires OPEN and gains no eligibility.
    public = project_independent_price_condition(tmp_path, symbol='300364', plan=legacy, now=NOW)
    assert public['risk_review_eligible'] is False
    assert 'CURRENT_ENTRY_CONDITION_NOT_OBSERVED' in public['blockers']
    repository = None
    if fault != 'no_holding':
        _, digest = service.prepare_fill(dict(idempotency_key='held-buy', expected_revision=len(service.records()),
            fill=dict(transaction_id='isolated-buy', side='BUY', sleeve='CORE_VALUE' if fault == 'other_sleeve' else 'HOTSPOT_SATELLITE',
                symbol='300364', exchange='SZSE', quantity='100', price_cny='0.125', fees_cny='0',
                trade_date='2026-10-14', next_sell_session='2026-10-15', trading_unit='100')))
        service.confirm_fill(dict(idempotency_key='held-confirm', expected_revision=len(service.records()),
            prepared_record_sha256=digest, confirmed_at=NOW.isoformat(), confirmation_note='Isolated fill'))
        if fault not in {'no_thesis', 'other_sleeve'}:
            repository = bind_entry(service, tmp_path, monkeypatch)
        service.reconcile(dict(idempotency_key='held-statement', expected_revision=len(service.records()),
            reconciled_at=NOW.isoformat(), confirmation_note='Isolated post-fill statement',
            account_evidence=dict(id='isolated-held-statement', kind='broker_statement')))
    monkeypatch.setattr(projection, '_verified_prices', lambda *a: {'300364': {
        'price_cny': '0.125', 'trade_date': '2026-10-14', 'bundle_sha256': 'a' * 64, 'price_admitted': True}})
    # Existing risk-source adapter boundary; capacity/cost still run real engine.
    original_input = projection.build_risk_input
    def risk_input(*args, **kwargs):
        data = original_input(*args, **kwargs)
        for row in data['allocations']:
            row['committed_risk_cny'] = '0'
            row['evidence_ref'] = 'isolated-explicit-committed-risk'
        return data
    monkeypatch.setattr(projection, 'build_risk_input', risk_input)
    if fault == 'source':
        source = tmp_path / case['source_bindings']['60m']['path']
        source.write_bytes(source.read_bytes() + b' ')
    if fault == 'admission':
        (tmp_path / 'gates/event_risk.json').write_text('{}', encoding='utf-8')
    if fault == 'broken_thesis':
        from test_personal_entry_thesis import _save_current_review
        _save_current_review({'repository': repository}, available=NOW, review_date=NOW.date())
    assumptions = {**ASSUMPTIONS, 'max_trade_notional_cny': '1' if fault == 'capacity' else '1000',
        'buy_fee_fraction': '0.01', 'sell_fee_fraction': '0.01',
        'minimum_buy_fee_cny': '1000' if fault == 'fees' else '1', 'minimum_sell_fee_cny': '1'}
    before = service.journal.path.read_bytes()
    result = preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path, generated_at=NOW,
        payload={'symbol': '300364', 'assumptions': assumptions}, authenticated_subject='LOCAL_OPERATOR')
    decision = result['actionable_decision']
    if fault is None:
        assert decision['decision_action'] == 'ADD', decision
        assert decision['review_quantity'] > 0
        assert decision['ownership_verified'] is True
        assert decision['plan_binding']['plan']['action_intent'] == 'WATCH'
        assert decision['entry_price_or_range'] == '0.125'
        assert decision['expected_fees_and_slippage']['buy_fee_fraction'] == '0.01'
    else:
        assert decision['decision_action'] not in {'ADD', 'BUY'}, decision
        assert decision['review_quantity'] is None and decision['blockers']
        if fault.endswith('_drift'):
            assert any(code.startswith('HELD_ADVISORY_DEPENDENCY_INVALID:') for code in decision['blockers'])
    assert decision['action'] == 'no_order'
    assert decision['trade_eligible'] is decision['broker_execution_permission'] is False
    assert legacy == produced
    assert service.journal.path.read_bytes() == before


def test_client_cannot_select_private_add_action(actual_contract_preview, tmp_path):
    service = actual_contract_preview[0]
    with pytest.raises(ValueError):
        preview.preview_private_hotspot_risk(service.journal, repository_root=tmp_path, generated_at=NOW,
            payload={'symbol': '300364', 'assumptions': ASSUMPTIONS, 'review_action': 'ADD'})
