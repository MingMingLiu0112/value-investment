from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from test_research_case import case
from value_investment_agent.research_gate import (
    CONCLUSION_RESEARCH_READY,
    GATE_BUSINESS,
    GATE_VALUATION,
    evaluate,
    evaluate_with_valuation,
)
from value_investment_agent.research_run_contract import (
    ResearchValuationApproval,
    valuation_result_sha256,
)
from value_investment_agent.valuation_models.base import ValuationResult


def _ready_case():
    referenced = {
        "kind": "fact",
        "text": "evidence-backed",
        "evidence_refs": ["source"],
    }
    return replace(
        case(),
        evidence_status="verified",
        research_status="financial_scope_approved",
        valuation_status="approved",
        evidence_refs=[{"id": "source"}],
        thesis="thesis",
        return_driver="driver",
        mispricing_hypothesis="hypothesis",
        positives=[referenced] * 3,
        counter_evidence=[referenced] * 3,
        thesis_breakers=[referenced] * 3,
        next_events=[{"kind": "hypothesis", "text": "next event"}],
    )


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol="600519",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2025, 12, 31),
        bear_value=Decimal("100"),
        base_value=Decimal("110"),
        bull_value=Decimal("120"),
        confidence="低",
        assumptions={},
        sensitivities=[],
        evidence_refs=[{"id": "valuation"}],
        blockers=[],
        status="conditional_research_only",
        model_version="v1",
    )


def _approval(valuation: ValuationResult) -> ResearchValuationApproval:
    return ResearchValuationApproval(
        model_id="residual_income_or_equity_value",
        model_type=valuation.model_type,
        model_version=valuation.model_version,
        valuation_date=valuation.valuation_date,
        result_sha256=valuation_result_sha256(valuation),
        approved_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        approver="human-reviewer",
        evidence_refs=[{"id": "approval"}],
    )


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
    assert gate.ready_for_price_assessment is True
    assert gate.internal_status == "RESEARCH_READY_FOR_PRICE_ASSESSMENT"
    assert gate.conclusion == CONCLUSION_RESEARCH_READY
    assert gate.conclusion not in {"估值具备研究吸引力", "等待更有吸引力的价格"}


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


def test_g3_requires_exact_current_result_and_human_approval():
    ready = _ready_case()
    valuation = _valuation()

    without_approval = evaluate_with_valuation(
        ready,
        valuation,
        model_id="residual_income_or_equity_value",
        approval=None,
    )
    assert without_approval.results[GATE_VALUATION] is False
    assert GATE_VALUATION in without_approval.blockers

    matching = evaluate_with_valuation(
        ready,
        valuation,
        model_id="residual_income_or_equity_value",
        approval=_approval(valuation),
    )
    assert matching.results[GATE_VALUATION] is True
    assert matching.valuation_ready is True

    wrong_model = replace(
        _approval(valuation),
        model_id="fcff",
    )
    rejected = evaluate_with_valuation(
        ready,
        valuation,
        model_id="residual_income_or_equity_value",
        approval=wrong_model,
    )
    assert rejected.results[GATE_VALUATION] is False
