from dataclasses import replace

from test_research_case import case
from value_investment_agent.research_gate import evaluate


def test_incomplete_case_cannot_become_a_valuation_conclusion():
    gate = evaluate(case())
    assert gate.valuation_ready is False
    assert gate.conclusion == "估值未就绪"
    assert "G3_估值模型通过" in gate.blockers


def test_all_explicit_gates_are_required():
    ready = replace(case(), quote_date=case().as_of, financial_period=case().as_of,
                    missing_date_reasons={}, evidence_status="verified",
                    research_status="financial_scope_approved", valuation_status="approved")
    assert evaluate(ready).valuation_ready is True
