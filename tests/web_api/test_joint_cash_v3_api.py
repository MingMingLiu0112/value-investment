"""The real decision API exposes the registered v3 candidate, without approval."""
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
