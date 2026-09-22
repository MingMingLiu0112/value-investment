from datetime import date
from decimal import Decimal

from value_investment_agent.price_attractiveness import (
    STATUS_KEY_OBSERVATION,
    STATUS_NOT_ASSESSABLE,
    STATUS_PRICE_NOT_ATTRACTIVE,
    STATUS_RESEARCH_ATTRACTIVE,
    STATUS_WAITING_FOR_BETTER_PRICE,
    assess_price_attractiveness,
)
from value_investment_agent.price_bridge import PriceBridgeResult
from value_investment_agent.research_gate import (
    CONCLUSION_RESEARCH_READY,
    ResearchGate,
)
from value_investment_agent.valuation_models.base import ValuationResult


def gate():
    return ResearchGate(
        symbol="600519",
        results={
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": True,
        },
        blockers=[],
        conclusion=CONCLUSION_RESEARCH_READY,
    )


def valuation(confidence="高", model_type="residual_income_or_equity_value"):
    return ValuationResult(
        symbol="600519",
        model_type=model_type,
        valuation_date=date(2026, 9, 20),
        bear_value=Decimal("400"),
        base_value=Decimal("500"),
        bull_value=Decimal("600"),
        confidence=confidence,
        assumptions={},
        sensitivities=[],
        evidence_refs=[{"id": "valuation"}],
        blockers=[],
        status="approved_research_only",
        model_version="fixture-v1",
    )


def bridge(status="READY", margin_to_bear="0.1", margin_to_base="0.05"):
    ready = status == "READY"
    return PriceBridgeResult(
        symbol="600519",
        valuation_date=date(2026, 9, 20),
        quote_date=date(2026, 9, 21) if ready else None,
        current_price=Decimal("450") if ready else None,
        margin_to_bear=Decimal(margin_to_bear) if ready else None,
        margin_to_base=Decimal(margin_to_base) if ready else None,
        model_validity_status="VALID",
        quote_status="verified_close" if ready else "PENDING_EXTERNAL_DATA",
        bridge_status=status,
        evidence_refs=[{"id": "quote"}],
        blockers=[] if ready else ["等待已验证收盘行情"],
    )


def test_pending_bridge_cannot_enter_price_assessment():
    outcome = assess_price_attractiveness(
        gate(), valuation(), bridge("PENDING_EXTERNAL_DATA")
    )

    assert outcome.status == STATUS_NOT_ASSESSABLE
    assert outcome.margin_to_bear is None
    assert "price_bridge_pending_external_data" in outcome.blockers


def test_quality_compounder_does_not_require_universal_thirty_percent():
    outcome = assess_price_attractiveness(
        gate(),
        valuation(),
        bridge(margin_to_bear="0.1", margin_to_base="0.05"),
    )

    assert outcome.status == STATUS_RESEARCH_ATTRACTIVE


def test_low_confidence_quality_compounder_waits_for_better_conditions():
    outcome = assess_price_attractiveness(
        gate(), valuation(confidence="低"), bridge()
    )

    assert outcome.status == STATUS_WAITING_FOR_BETTER_PRICE
    assert "valuation_confidence_low" in outcome.blockers


def test_price_above_bear_reference_is_not_attractive():
    outcome = assess_price_attractiveness(
        gate(),
        valuation(),
        bridge(margin_to_bear="-0.1", margin_to_base="-0.05"),
    )

    assert outcome.status == STATUS_PRICE_NOT_ATTRACTIVE
    assert "price_above_bear_reference" in outcome.blockers


def test_unregistered_profile_only_observes():
    outcome = assess_price_attractiveness(
        gate(),
        valuation(model_type="fixture"),
        bridge(),
    )

    assert outcome.status == STATUS_KEY_OBSERVATION
    assert "profile_not_identified" in outcome.blockers


def test_incomplete_gate_blocks_price_assessment_even_with_ready_bridge():
    incomplete = ResearchGate(
        symbol="600519",
        results={
            "G0_证据门": False,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": True,
        },
        blockers=["G0_证据门"],
        conclusion="数据不足",
    )
    outcome = assess_price_attractiveness(incomplete, valuation(), bridge())

    assert outcome.status == STATUS_NOT_ASSESSABLE
    assert "research_gate_not_ready_for_price_assessment" in outcome.blockers
