from dataclasses import replace

from test_research_case import case
from value_investment_agent.research_gate import GATE_BUSINESS, evaluate


def test_incomplete_case_cannot_become_a_valuation_conclusion():
    gate = evaluate(case())
    assert gate.valuation_ready is False
    assert gate.conclusion == "数据不足"
    assert "G0_证据门" in gate.blockers
    assert "G2_商业论点门" in gate.blockers


def test_all_substantive_gates_are_required():
    referenced = {"kind": "fact", "text": "evidence-backed", "evidence_refs": ["source"]}
    ready = replace(
        case(), evidence_status="verified", research_status="financial_scope_approved",
        valuation_status="approved", evidence_refs=[{"id": "source"}],
        thesis="thesis", return_driver="driver", mispricing_hypothesis="hypothesis",
        positives=[referenced] * 3, counter_evidence=[referenced] * 3,
        thesis_breakers=[referenced] * 3,
        next_events=[{"kind": "hypothesis", "text": "next event"}],
    )
    gate = evaluate(ready)
    assert gate.valuation_ready is True
    assert gate.conclusion == "估值具备研究吸引力"


def test_g2_requires_a_registered_next_event():
    referenced = {"kind": "fact", "text": "evidence-backed", "evidence_refs": ["source"]}
    ready = replace(
        case(), evidence_status="verified", research_status="financial_scope_approved",
        valuation_status="approved", evidence_refs=[{"id": "source"}],
        thesis="thesis", return_driver="driver", mispricing_hypothesis="hypothesis",
        positives=[referenced] * 3, counter_evidence=[referenced] * 3,
        thesis_breakers=[referenced] * 3, next_events=[],
    )
    gate = evaluate(ready)
    assert gate.results[GATE_BUSINESS] is False
    assert GATE_BUSINESS in gate.blockers


def test_partial_evidence_is_data_insufficient_even_when_financial_scope_exists():
    partial = replace(case(), evidence_status="partial", research_status="financial_scope_approved")
    assert evaluate(partial).conclusion == "数据不足"
