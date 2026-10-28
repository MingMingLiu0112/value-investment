"""The real decision API exposes the registered v3 candidate, without approval."""
from copy import deepcopy
from datetime import datetime, timezone

from test_joint_cash_neutral_proposal import case
from test_joint_cash_pending_candidate import prepared_v3, save
from value_investment_agent.application.decision.current_value_plan import (
    load_current_value_action_plans,
)
from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.research.value_research_analysis import (
    load_current_value_research_analysis,
)
from value_investment_agent.presentation.web_api import app as api_module

from test_read_api import _fixture


def test_registered_v3_candidate_reaches_decision_api(prepared_v3, monkeypatch):
    root, folder, receipt, _ = prepared_v3
    symbol = receipt['symbol']
    save(root/'config/current-research-drafts.json', dict(
        schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={symbol: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(folder/'candidate.json'))}))
    company = dict(symbol=symbol, company_name=symbol, action='no_order')
    client = _fixture(root, receipt_records=[dict(symbol=symbol)],
        report_overrides=dict(lead_symbols=[symbol], deduplicated_lead_count=1),
        snapshot_overrides=dict(companies=[company], opportunities=[]))
    direct = load_current_value_research_analysis(
        root=root, symbol=symbol, now=datetime.now(timezone.utc))
    assert direct is not None
    current = load_current_value_action_plans(
        root, now=datetime.now(timezone.utc), symbols=[symbol])
    assert current['items'], current
    frozen = next(row for row in current['items'] if row['symbol'] == symbol)
    packet = dict(publication_id='TEST_ONLY_V3_API', research_version='TEST_ONLY_V3',
        generated_at=datetime.now(timezone.utc).isoformat(), engine_version='TEST_ONLY',
        value_price_conditions={symbol: frozen})
    monkeypatch.setattr(api_module, '_load_snapshot', lambda ignored: (packet, {}))

    response = client.get('/api/v1/decisions/' + symbol)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['action'] == 'no_order'
    assert payload['review_replay']['status'] == 'VERIFIED_NEW_INPUT_CANDIDATE'
    plan = payload['decision']['price_action_plan']
    assert plan['action'] == 'no_order'
    assert plan['formal_eligibility'] is False
    analysis = plan['research_analysis']
    assert analysis['input_descriptor_sha256'] == receipt['model_context']['input_descriptor_sha256']
    review = analysis['joint_capital_review']
    assert review['schema_version'] == 'joint-capital-cash-review-v3'
    assert review['status'] == 'CONDITIONAL_PATH_NOT_APPROVED'
    assert review['action'] == 'no_order'
    assert [row['valuation_per_share'] for row in review['scenarios']] == [
        analysis['valuation']['bear_value'],
        analysis['valuation']['base_value'],
        analysis['valuation']['bull_value'],
    ]


def test_registered_candidate_remains_readable_without_a_current_publication(
        prepared_v3, monkeypatch):
    root, folder, receipt, _ = prepared_v3
    symbol = receipt['symbol']
    save(root/'config/current-research-drafts.json', dict(
        schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={symbol: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(folder/'candidate.json'))}))
    client = _fixture(root)
    monkeypatch.setattr(api_module, '_public', lambda ignored: None)

    response = client.get('/api/v1/decisions/' + symbol)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload['status'] == 'RESEARCH_ONLY'
    assert payload['action'] == 'no_order'
    assert payload['formal_eligibility'] is False
    assert payload['review_replay']['status'] == 'VERIFIED_NEW_INPUT_CANDIDATE'
    assert payload['publication']['packet_status'] == 'UNAVAILABLE'
    analysis = payload['decision']['research_analysis']
    assert analysis['status'] == 'CONDITIONAL_ANALYSIS_VERIFIED'
    assert analysis['input_descriptor_sha256'] == receipt['model_context']['input_descriptor_sha256']
    assert analysis['joint_capital_review']['status'] == 'CONDITIONAL_PATH_NOT_APPROVED'


def test_latest_registered_candidate_replaces_stale_plan_and_old_opportunity(
        prepared_v3, monkeypatch):
    root, folder, receipt, _ = prepared_v3
    symbol = receipt['symbol']
    save(root/'config/current-research-drafts.json', dict(
        schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={symbol: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256=sha256_file(folder/'candidate.json'))}))
    current = load_current_value_action_plans(
        root, now=datetime.now(timezone.utc), symbols=[symbol])
    stale = deepcopy(current['items'][0])
    stale['valuation_input_version'] = '0' * 64
    stale['research_version'] = 'OLD'
    packet = dict(publication_id='TEST_ONLY_STALE_PLAN',
        research_version='TEST_ONLY_STALE_PLAN',
        generated_at=datetime.now(timezone.utc).isoformat(), engine_version='TEST_ONLY',
        value_price_conditions={symbol: stale})
    monkeypatch.setattr(api_module, '_load_snapshot', lambda ignored: (packet, {}))
    old_opportunity = dict(symbol=symbol, company_name='OLD', action='no_order')
    receipt_symbols = sorted({'600741', '600519', symbol})
    client = _fixture(root, receipt_records=[dict(symbol=item) for item in receipt_symbols],
        snapshot_overrides=dict(companies=[], opportunities=[old_opportunity]))

    payload = client.get('/api/v1/decisions/' + symbol).json()

    assert payload['review_replay']['status'] == 'VERIFIED_NEW_INPUT_CANDIDATE'
    assert payload['decision']['research_analysis']['input_descriptor_sha256'] == (
        receipt['model_context']['input_descriptor_sha256'])
    assert 'price_action_plan' not in payload['decision']
    assert payload['formal_eligibility'] is False
    assert payload['action'] == 'no_order'
    daily = client.get('/api/v1/daily-decisions').json()
    rows = [item for item in daily.get('sections', {}).get('value', [])
            if item.get('symbol') == symbol]
    assert rows, daily
    row = rows[0]
    assert 'price_action_plan' not in row
    assert 'CURRENT_VALUE_PLAN_NOT_BOUND_TO_LATEST_RESEARCH' in row['blockers']


def test_broken_registered_candidate_never_falls_back_to_old_company(
        prepared_v3):
    root, folder, receipt, _ = prepared_v3
    symbol = receipt['symbol']
    save(root/'config/current-research-drafts.json', dict(
        schema_version='current-research-drafts-v1', action='no_order',
        pending_candidates={symbol: dict(
            path=(folder/'candidate.json').relative_to(root).as_posix(),
            sha256='0' * 64)}))
    company = dict(symbol=symbol, company_name='OLD', action='no_order')
    client = _fixture(root, receipt_records=[dict(symbol=symbol)],
        report_overrides=dict(lead_symbols=[symbol], deduplicated_lead_count=1),
        snapshot_overrides=dict(companies=[company], opportunities=[]))

    payload = client.get('/api/v1/decisions/' + symbol).json()

    assert payload['status'] == 'UNAVAILABLE'
    assert payload['decision'] is None
    assert payload['reason'] == 'CURRENT_RESEARCH_CANDIDATE_UNAVAILABLE'
    assert payload['formal_eligibility'] is False
