from dataclasses import replace
import pytest
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload, EvidenceRecord
from value_investment_agent.presentation.read_models.reported_financials import project_reported_financials
from value_investment_agent.application.historical_validation.reported_cash_proxy import reported_cash_proxies


def test_cash_research_is_explanatory_and_keeps_all_decision_state():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    facts = [dict(symbol=card.symbol, metric_name=name, period='2025', value=value, unit='CNY',
                  statement_scope='CONSOLIDATED', physical_page=page, source_binding={'sha256': 'a'*64},
                  verification_status='TRANSCRIBED_ROW_NUMERIC_MATCH_ONLY')
             for name, value, page in [('reported_operating_cash_flow', '14343920490.32', 89),
                                     ('reported_cash_capex', '3036644156.68', 90)]]
    review = dict(schema_version='disclosed-metric-review-v1', symbol=card.symbol, facts=facts,
                  action='no_order', financial_gate_admitted=False, forecast_assumptions_approved=False,
                  strict_pit_admitted=False)
    evidence = EvidenceRecord('financial-fixture', 'Rows', 'research', 'runtime/rows.json', 'a'*64, model.as_of)
    output = project_reported_financials(model, review, reported_cash_proxies(review), evidence)
    updated = output.companies[0]
    assert replace(updated, decision_review=card.decision_review, evidence_refs=card.evidence_refs) == card
    assert output.portfolio == model.portfolio
    assert '113.07亿元' in dict(updated.decision_review)['已披露 2025 CFO减现金资本开支（描述性）']
    assert '不是FCFF/FCFE' in dict(updated.decision_review)['财务解释边界']
    assert project_reported_financials(output, review, reported_cash_proxies(review), evidence) == output
    review['strict_pit_admitted'] = True
    with pytest.raises(ValueError): project_reported_financials(model, review, None, evidence)
