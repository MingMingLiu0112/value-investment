from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.domain.research.research_case import ResearchCase
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload
from value_investment_agent.presentation.read_models.research_case_card import company_with_research_case
from test_product_workbench_read_model import _payload


def case():
    path = Path(__file__).resolve().parents[1] / 'config/m1-valuation-packages-v1/600887-quality-compounder.json'
    raw = json.loads(path.read_text(encoding='utf-8'))['research_case']
    raw['as_of'] = date.fromisoformat(raw['as_of'])
    raw['generated_at'] = datetime.fromisoformat(raw['generated_at'])
    for key in ('quote_date', 'financial_period'):
        raw[key] = date.fromisoformat(raw[key])
    return ResearchCase(**raw)


@pytest.mark.parametrize('symbol', ['600887', '000333', '601088'])
def test_research_projection_preserves_entry_and_all_gates(symbol):
    original = product_workbench_from_payload(_payload()).companies[0]
    research = replace(case(), symbol=symbol, name='fixture company')
    card = replace(original, symbol=symbol, company_name=research.name)
    digest = hashlib.sha256(research.to_json().encode('utf-8')).hexdigest()
    projected = company_with_research_case(card, research, expected_sha256=digest)
    assert projected.original_thesis == card.original_thesis
    assert projected.decision_process == card.decision_process
    assert projected.valuation == card.valuation
    assert projected.price == card.price
    assert projected.action == 'no_order'
    assert research.thesis in projected.sections[0].summary
    assert '[假设]' in projected.sections[-1].summary
    assert research.mispricing_hypothesis in dict(projected.decision_review).values()


def test_research_projection_rejects_changed_case_and_wrong_identity():
    research = case()
    card = replace(product_workbench_from_payload(_payload()).companies[0], symbol=research.symbol, company_name=research.name)
    digest = hashlib.sha256(research.to_json().encode('utf-8')).hexdigest()
    with pytest.raises(ValueError, match='binding mismatch'):
        company_with_research_case(card, replace(research, thesis='changed'), expected_sha256=digest)
    with pytest.raises(ValueError, match='identity mismatch'):
        company_with_research_case(replace(card, company_name='wrong'), research, expected_sha256=digest)


@pytest.mark.parametrize('fault', [None, 'hash', 'symbol', 'admission', 'boolean'])
def test_historical_gate_display_never_changes_current_gates(fault):
    from value_investment_agent.presentation.read_models.research_case_card import company_with_historical_gate_read
    card = product_workbench_from_payload(_payload()).companies[0]
    payload = dict(symbol=card.symbol, action='no_order', mode='READ_EXISTING_ONLY', suggested_state='NOT_READY',
                   historical_research_gate=dict(current_admission=False, research_as_of='2026-09-22',
                       results={'G0': True, 'G3': False}, conclusion='valuation not ready', blockers=['approval missing']))
    if fault == 'symbol': payload['symbol'] = '999999'
    if fault == 'admission': payload['historical_research_gate']['current_admission'] = True
    if fault == 'boolean': payload['historical_research_gate']['results']['G0'] = 'true'
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    if fault == 'hash': digest = 'a' * 64
    if fault:
        with pytest.raises(ValueError): company_with_historical_gate_read(card, payload, expected_sha256=digest)
    else:
        projected = company_with_historical_gate_read(card, payload, expected_sha256=digest)
        assert projected.decision_process == card.decision_process
        assert projected.original_thesis == card.original_thesis
        assert projected.price == card.price
        assert projected.valuation == card.valuation
        assert '2026-09-22' in dict(projected.decision_review)['历史研究门评估']
