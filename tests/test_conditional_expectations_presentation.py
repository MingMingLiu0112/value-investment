from datetime import date
from datetime import datetime, timezone
import hashlib
import json
from dataclasses import replace
import pytest
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload, EvidenceRecord
from value_investment_agent.presentation.read_models.conditional_expectations import project_conditional_expectations


def test_price_and_gates_are_not_changed_by_historical_expectations():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    payload = dict(schema_version='retrospective-equity-expectations-v1',
        scope='RETROSPECTIVE_CONDITIONAL_EXPECTATIONS_NOT_CURRENT_ADVICE', symbol=card.symbol,
        quote_date='2026-09-22', action='no_order', strict_pit_admitted=False, current_model_admitted=False,
        performance_claim_allowed=False, assumptions_contemporaneously_registered=False,
        scenarios=[dict(scenario='base', status='CONDITIONAL_ARITHMETIC_ONLY', implied_terminal_roe='0.254')])
    evidence = EvidenceRecord('reverse-fixture', 'Historical reverse fixture', 'research',
                              'runtime/reverse.json', 'a'*64, model.as_of)
    output = project_conditional_expectations(model, payload, evidence)
    updated = output.companies[0]
    assert updated.price == card.price
    assert updated.scenarios == card.scenarios
    assert updated.decision_process == card.decision_process
    assert updated.research_status == card.research_status
    assert '25.4%' in dict(updated.decision_review)['价格隐含终局ROE（条件性）']
    assert output.portfolio == model.portfolio
    from value_investment_agent.presentation.read_models.conditional_expectations import render_company_review_cards
    report = render_company_review_cards(output)
    assert '25.4%' in report
    assert '不是当前买卖建议' in report
    assert 'action=no_order' in report
    payload['current_model_admitted'] = True
    with pytest.raises(ValueError): project_conditional_expectations(model, payload, evidence)


def test_expectations_loader_recomputes_instead_of_trusting_cached_numbers(tmp_path, monkeypatch):
    from value_investment_agent.application.historical_validation import reverse_equity_expectations as service
    digest = 'a' * 64
    cached = dict(created_at=datetime.now(timezone.utc).isoformat(), workbench_sha256=digest,
        scenarios=[dict(implied_terminal_roe='0.25')], source_bindings={name: dict(path=f'{name}.json', sha256=digest)
            for name in ('workbench', 'arithmetic', 'quote')})
    fresh = json.loads(json.dumps(cached))
    monkeypatch.setattr(service, 'reverse_equity_expectations', lambda **kwargs: fresh)
    path = tmp_path / 'replay.json'
    path.write_text(json.dumps(dict(reverse_equity_expectations=cached)), encoding='utf-8')
    args = dict(root=tmp_path, path=path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                workbench_sha256=digest)
    assert service.load_reverse_expectations_for_presentation(**args) == cached
    fresh['scenarios'][0]['implied_terminal_roe'] = '0.30'
    with pytest.raises(ValueError, match='recomputation'):
        service.load_reverse_expectations_for_presentation(**args)
