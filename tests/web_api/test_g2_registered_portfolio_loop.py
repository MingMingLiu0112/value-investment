"""Signed TEST_ONLY plans -> private API sizing -> fills -> fresh shared risk."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

import pytest
from fastapi.testclient import TestClient

from test_d2_conditional_shared_service import synthetic_chain
from test_p7_signed_review_workflow import _complete_signed_case, _registered_policy_fixture
from test_private_ips_policy import full_policy
from value_investment_agent.application.product.common import write_new_json, sha256_file
from value_investment_agent.application.product.daily_public_packet import build_daily_public_packet
from value_investment_agent.application.product.public_snapshot import publish_snapshot
from value_investment_agent.application.portfolio import private_portfolio_service as ledger
from value_investment_agent.application.portfolio import private_risk_preview as preview
from value_investment_agent.application.portfolio import private_risk_projection as projection
from value_investment_agent.domain.portfolio.security_attributes import official_observation
from value_investment_agent.domain.hotspot.current_price import SESSION_TIMES
from value_investment_agent.infrastructure.hotspot.current_price_case import collect_current_price_case
from value_investment_agent.operations.authorization.trust_root_registry import _use_test_trust_registry
from value_investment_agent.presentation.web_api import private_routes
from value_investment_agent.presentation.web_api.app import create_app

NOW = datetime.fromisoformat('2026-09-21T21:00:00+08:00')
BASE = '/api/v1/private/portfolio'
SYMBOL = '600519'


def registered_market(root, monkeypatch, chain):
    restored, _, _ = _complete_signed_case(chain, monkeypatch)
    _registered_policy_fixture(root, restored)
    bundle = root / 'runtime/TEST_ONLY-quote.json'

    class Response:
        def __init__(self, scale):
            period = '60m' if scale == '60' else '15m'
            self.url = ('https://quotes.sina.cn/cn/api/jsonp_v2.php/=/'
                f'CN_MarketDataService.getKLineData?symbol=sh600519&scale={scale}&ma=no')
            rows = [dict(day=f'2026-09-{day:02} {clock}', open='5', close='5',
                high='5.01', low='4.99', volume='100' if period == '60m' else '25',
                amount='500' if period == '60m' else '125')
                for day in (14, 15, 16, 17, 18, 21) for clock in SESSION_TIMES[period]]
            self.content = ('=(' + json.dumps(rows) + ');').encode()

        def raise_for_status(self):
            pass

    case = collect_current_price_case(root=root, symbol=SYMBOL, as_of=NOW.date(),
        quote_bundle_path=bundle, quote_bundle_sha256=sha256_file(bundle), now=NOW,
        fetch=lambda _url, params, timeout: Response(params['scale']))
    watch = root / 'runtime/TEST_ONLY-watch.json'
    write_new_json(watch, dict(namespace='TEST_ONLY', dated_quote_observations=[dict(symbol=SYMBOL)]))
    write_new_json(root / 'config/current-price-conditions.json', dict(
        schema_version='current-price-conditions-v1', action='no_order',
        watch_source_scope='DATED_SECURITIES_OBSERVATION_NOT_INDUSTRY_ADMISSION',
        watch_source_binding=dict(path=watch.relative_to(root).as_posix(), sha256=sha256_file(watch)),
        items=[dict(symbol=SYMBOL, company_name='TEST_ONLY', case_path=case['case_path'], case_sha256=case['case_sha256'])]))
    with _use_test_trust_registry(root / 'TEST_ONLY-combined-trust-registry.json'):
        packet = build_daily_public_packet(root, generated_at=NOW)
    assert packet['chain_error'] is None
    assert packet['value_price_conditions'][SYMBOL]['formal_eligibility'] is True
    assert packet['price_conditions']['items'][0]['price_action_plan']['expires_after_session'] == '2026-09-22'
    target = root / 'runtime/TEST_ONLY-registered-packet.json'
    write_new_json(target, packet)
    publish_snapshot(root, packet, target, published_at=NOW)
    return packet


def test_registered_plans_core_and_post_buy_resizing(synthetic_chain, monkeypatch):
    root = synthetic_chain[0]
    trust = root / 'TEST_ONLY-combined-trust-registry.json'
    # Signed fixture creation enters its own exact registry contexts.
    packet = registered_market(root, monkeypatch, synthetic_chain)
    journal = root / 'TEST_ONLY-private/journal.jsonl'
    monkeypatch.setattr(private_routes, 'resolve_private_root', lambda **kwargs: journal)
    clock = [NOW]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(clock[0].timestamp(), tz=tz or clock[0].tzinfo)

    monkeypatch.setattr(private_routes, 'datetime', Clock)
    monkeypatch.setattr(ledger, 'datetime', Clock)
    observation = official_observation(dict(symbol=SYMBOL, name='TEST_ONLY', exchange='SSE',
        board='MAIN', listed_on='2000-01-01', security_type='A股'), industry_code='I',
        known_at=NOW-timedelta(hours=3), valid_until=NOW+timedelta(days=1),
        evidence_refs=[dict(id='TEST_ONLY-ATTRIBUTES', path='TEST_ONLY.json', sha256='a'*64)])
    # Only the official-security source boundary is synthetic; plan loaders,
    # publication hashes, signatures, journal and both sizing engines are real.
    monkeypatch.setattr(preview, 'load_verified_security_attributes', lambda *a, **k: [deepcopy(observation)])
    monkeypatch.setattr(projection, '_verified_attributes', lambda *a, **k: [deepcopy(observation)])
    monkeypatch.setattr('requests.sessions.Session.request', lambda *a, **k: pytest.fail('No network in TEST_ONLY loop'))
    secret = 'TEST_ONLY-g2-' + 'x'*40

    def connect():
        client = TestClient(create_app(root, port=8791, bootstrap_secret=secret),
            base_url='http://127.0.0.1:8791', client=('127.0.0.1', 51000))
        client.headers['origin'] = 'http://127.0.0.1:8791'
        token = client.post('/api/v1/private/session/unlock', json=dict(bootstrap_token=secret))
        assert token.status_code == 200, token.text
        client.headers['x-local-session'] = token.json()['token']
        return client

    def post(client, path, body):
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()['action'] == 'no_order'
        return response.json()

    with _use_test_trust_registry(trust), connect() as client:
        fresh = preview.load_registered_value_action_plans(root, now=NOW, symbols=[SYMBOL])
        assert fresh['items'], fresh
        current = fresh['items'][0]
        frozen = packet['value_price_conditions'][SYMBOL]
        assert all(frozen.get(key) == value for key, value in current.items())
        bound, error = preview._current_value_plan(root, SYMBOL, NOW)
        assert error is None, error
        post(client, BASE+'/initialize', dict(idempotency_key='init', expected_revision=0,
            account_scope='TEST_ONLY_G2_REGISTERED', as_of='2026-09-21', cash_cny='10000', holdings=[],
            sleeve_allocations={}, policy={}, confirmed_at='2026-09-21T18:00:00+08:00', confirmation_note='TEST_ONLY'))
        policy = full_policy()
        policy.update(effective_date='2026-09-21', max_single_security_pct='60')
        policy['sleeves']['CORE_VALUE']['cash_cny'] = '7000'
        prepared = post(client, BASE+'/policy/prepare', dict(idempotency_key='ips', expected_revision=1, policy=policy))
        post(client, BASE+'/policy/confirm', dict(idempotency_key='ips-confirm', expected_revision=2,
            prepared_record_sha256=prepared['record_sha256'], confirmed_at='2026-09-21T18:01:00+08:00', confirmation_note='TEST_ONLY'))

        def view():
            response = client.get('/api/v1/portfolio')
            assert response.status_code == 200, response.text
            return response.json()

        def reconcile(key):
            return post(client, BASE+'/reconcile', dict(idempotency_key=key, expected_revision=view()['revision'],
                reconciled_at=clock[0].isoformat(), confirmation_note='TEST_ONLY statement',
                account_evidence=dict(id='TEST_ONLY-'+key, kind='broker_statement')))

        choices = dict(acknowledged=True, execution=dict(liquid=True, limit_up=False, limit_down=False),
            holding_risks=[], security_risks=[dict(symbol=SYMBOL, cyclical=False, common_factors=[])])
        core_assumptions = dict(lot_size='100', max_trade_notional_cny='1500',
            entry_slippage_cny='0', buy_fee_fraction='0', minimum_buy_fee_cny='1')
        hotspot_assumptions = {key: '0' for key in preview.ASSUMPTION_FIELDS}
        hotspot_assumptions.update(core_assumptions, minimum_sell_fee_cny='1', gap_stress_cny='0.01')

        def size(sleeve):
            body = dict(symbol=SYMBOL, assumptions=core_assumptions if sleeve == 'CORE_VALUE' else hotspot_assumptions,
                scenario=deepcopy(choices))
            if sleeve == 'CORE_VALUE':
                body['sleeve'] = sleeve
            before = journal.read_bytes()
            result = post(client, BASE+'/risk-preview', body)
            assert journal.read_bytes() == before
            assert result['scenario_preview']['projection']['account_revision'] == view()['revision']
            assert result['scenario_preview']['trade_eligible'] is False
            return result

        def fill(sleeve, key):
            revision = view()['revision']
            value_plan = packet['value_price_conditions'][SYMBOL]
            hotspot_plan = packet['price_conditions']['items'][0]['price_action_plan']
            plan = value_plan if sleeve == 'CORE_VALUE' else hotspot_plan
            prepared = post(client, '/api/v1/private/fills/prepare', dict(idempotency_key=key, expected_revision=revision,
                fill=dict(transaction_id='TEST_ONLY-'+key, side='BUY', sleeve=sleeve, symbol=SYMBOL, exchange='SSE',
                    quantity='100', price_cny='4.99', fees_cny='1', trade_date='2026-09-21', trading_unit='100',
                    next_sell_session='2026-09-22', decision_id=SYMBOL if sleeve == 'CORE_VALUE' else 'hotspot-'+SYMBOL,
                    research_version=plan['research_version'])))
            post(client, '/api/v1/private/fills/confirm', dict(idempotency_key=key+'-confirm', expected_revision=revision+1,
                prepared_record_sha256=prepared['record_sha256'], confirmed_at=clock[0].isoformat(), confirmation_note='TEST_ONLY manual fill'))
            snapshot = view()['trades'][-1]['judgment_snapshot']
            assert snapshot['plan'] == plan
            assert snapshot['publication_id'] == packet['publication_id']
            return view()

        reconcile('initial-statement')
        initial_core, initial_hotspot = size('CORE_VALUE'), size('HOTSPOT_SATELLITE')
        assert initial_core['scenario_preview']['review_quantity'] is not None, initial_core['scenario_preview']
        assert initial_hotspot['scenario_preview']['review_quantity'] is not None, initial_hotspot['scenario_preview']
        assert initial_core['scenario_preview']['review_quantity'] > 0
        assert initial_hotspot['scenario_preview']['review_quantity'] > 0
        assert initial_core['scenario_preview']['engine']['core_quantity_review']['mechanical_stop_required'] is False
        assert initial_core['scenario_preview']['core_sizing_inputs']['entry_price_cny'] == '5'
        assert 'stop_price_cny' not in initial_core['scenario_preview']['core_sizing_inputs']
        core = fill('CORE_VALUE', 'core-buy')
        assert Decimal(core['cash_cny']) == 9500
        assert size('HOTSPOT_SATELLITE')['scenario_preview']['review_quantity'] is None
        reconcile('after-core-statement')
        choices['holding_risks'] = [dict(sleeve='CORE_VALUE', symbol=SYMBOL, committed_risk_cny='5')]
        after_core = size('HOTSPOT_SATELLITE')
        assert after_core['scenario_preview']['review_quantity'] >= 100, after_core
        assert Decimal(after_core['facts']['cash_cny']) == 9500
        after_core_core = size('CORE_VALUE')
        assert Decimal(after_core_core['scenario_preview']['engine']['sleeves']['CORE_VALUE']['cash_cny']) == 6500
        both = fill('HOTSPOT_SATELLITE', 'hotspot-buy')
        assert Decimal(both['cash_cny']) == 9000
        reconcile('after-both-statement')
        choices['holding_risks'].append(dict(sleeve='HOTSPOT_SATELLITE', symbol=SYMBOL, committed_risk_cny='5'))
        after_both_core, after_both_hotspot = size('CORE_VALUE'), size('HOTSPOT_SATELLITE')
        assert after_both_core['scenario_preview']['review_quantity'] > 0, after_both_core
        assert after_both_hotspot['scenario_preview']['review_quantity'] < after_core['scenario_preview']['review_quantity']
        engine = after_both_hotspot['scenario_preview']['engine']
        assert len(engine['aggregate']['duplicated_security_exposure'][SYMBOL]) == 2
        assert Decimal(engine['aggregate']['cash_cny']) == 9000
        assert Decimal(engine['aggregate']['total_assets_cny']) == 10000
        assert sum(Decimal(row['market_value_cny']) for row in engine['aggregate']['duplicated_security_exposure'][SYMBOL]) == 1000
        # Each sleeve is below its own risk budget, but the SAME security's
        # combined committed risk exhausts the confirmed single-security cap.
        choices['holding_risks'][1]['committed_risk_cny'] = '95'
        combined_cap = size('HOTSPOT_SATELLITE')
        assert combined_cap['scenario_preview']['review_quantity'] is None
        cap_review = combined_cap['scenario_preview']['engine']['hotspot_quantity_review']
        assert Decimal(cap_review['same_security_existing_risk_cny']) == 100
        assert Decimal(cap_review['planned_risk_limit_cny']) == 0
        choices['holding_risks'][1]['committed_risk_cny'] = '5'
        before_rejection = journal.read_bytes()
        invalid_core = dict(sleeve='CORE_VALUE', symbol=SYMBOL, assumptions=core_assumptions,
            scenario=deepcopy(choices), entry_price_cny='0.01')
        assert client.post(BASE+'/risk-preview', json=invalid_core).status_code == 422
        # Reverify registered policy bytes at every preview, including after fills.
        policy_path = root / bound['plan']['safety_margin_policy']['source_binding']['path']
        original_policy = policy_path.read_bytes()
        policy_path.write_bytes(original_policy + b' ')
        assert size('CORE_VALUE')['scenario_preview']['review_quantity'] is None
        policy_path.write_bytes(original_policy)
        assert journal.read_bytes() == before_rejection

        sell = dict(transaction_id='TEST_ONLY-partial-sell', side='SELL', sleeve='HOTSPOT_SATELLITE',
            symbol=SYMBOL, exchange='SSE', quantity='50', price_cny='6', fees_cny='2', trade_date='2026-09-21',
            decision_id='hotspot-'+SYMBOL,
            research_version=packet['price_conditions']['items'][0]['price_action_plan']['research_version'])
        early = client.post('/api/v1/private/fills/prepare', json=dict(idempotency_key='early-sell',
            expected_revision=view()['revision'], fill=sell))
        assert early.status_code == 422 and 'insufficient sellable' in early.json()['detail']
        assert journal.read_bytes() == before_rejection
        clock[0] = NOW + timedelta(days=1)
        sell['trade_date'] = '2026-09-22'
        revision = view()['revision']
        prepared = post(client, '/api/v1/private/fills/prepare', dict(idempotency_key='partial-sell',
            expected_revision=revision, fill=sell))
        post(client, '/api/v1/private/fills/confirm', dict(idempotency_key='partial-sell-confirm',
            expected_revision=revision+1, prepared_record_sha256=prepared['record_sha256'],
            confirmed_at=clock[0].isoformat(), confirmation_note='TEST_ONLY partial sell'))
        sold = view()
        assert Decimal(sold['cash_cny']) == 9298
        assert Decimal(sold['realized_pnl_cny']) == 48
        assert Decimal(sold['positions'][0]['quantity']) == 150
        assert Decimal(sold['positions'][0]['cost_cny']) == 750
        assert sold['trades'][0]['judgment_snapshot'] == both['trades'][0]['judgment_snapshot']
        assert sold['trades'][1]['judgment_snapshot'] == both['trades'][1]['judgment_snapshot']
        # Retire only this isolated ranking; ledger membership remains authoritative.
        (root / 'config/current-price-conditions.json').unlink()
        held = client.get(BASE+'/held-continuity')
        assert held.status_code == 200, held.text
        assert len(held.json()['items']) == 1
        assert held.json()['items'][0]['selected_today'] is False
        assert Decimal(held.json()['items'][0]['quantity']) == 150
        before_restart = view()
        with connect() as restarted:
            assert restarted.get('/api/v1/portfolio').json() == before_restart
        write_new_json(root / 'TEST_ONLY-g2-receipt.json', dict(action='no_order', status='API_REHEARSAL_PASS',
            initial_core=initial_core, initial_hotspot=initial_hotspot, after_core=after_core,
            after_core_core=after_core_core, after_both_core=after_both_core,
            after_both_hotspot=after_both_hotspot, combined_security_cap=combined_cap,
            portfolio=before_restart, held_continuity=held.json()))
