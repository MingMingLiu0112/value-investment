from dataclasses import replace
from datetime import date
from decimal import Decimal
import json

import pytest

from value_investment_agent.current_research_status import (
    CONCLUSION_RESEARCH_READY,
    CONCLUSION_VALUATION_NOT_READY,
    CURRENT_DATA_PENDING_EXTERNAL_DATA,
    ENGINEERING_READY,
    CurrentDataStatus,
    current_research_status_from_payloads,
    evaluate_current_research_status,
)
from value_investment_agent.price_bridge import PriceBridgeResult
from value_investment_agent.price_attractiveness import (
    STATUS_KEY_OBSERVATION,
    STATUS_NOT_ASSESSABLE,
    STATUS_RESEARCH_ATTRACTIVE,
    STATUS_WAITING_FOR_BETTER_PRICE,
)
from value_investment_agent.research_gate import ResearchGate
from value_investment_agent.valuation_models.base import ValuationResult


def gate(conclusion=CONCLUSION_RESEARCH_READY):
    return ResearchGate(
        symbol="600519",
        results={
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": True,
        },
        blockers=[],
        conclusion=conclusion,
    )


def valuation(**overrides):
    values = dict(
        symbol="600519",
        model_type="fixture",
        valuation_date=date(2026, 9, 20),
        bear_value=Decimal("400"),
        base_value=Decimal("500"),
        bull_value=Decimal("600"),
        confidence="中",
        assumptions={},
        sensitivities=[],
        evidence_refs=[{"id": "valuation"}],
        blockers=[],
        status="approved_research_only",
        model_version="fixture-v1",
    )
    values.update(overrides)
    return ValuationResult(**values)


def bridge(status="READY", **overrides):
    values = dict(
        symbol="600519",
        valuation_date=date(2026, 9, 20),
        quote_date=date(2026, 9, 21),
        current_price=Decimal("350"),
        margin_to_bear=Decimal("0.125"),
        margin_to_base=Decimal("0.3"),
        model_validity_status="VALID",
        quote_status="verified_close",
        bridge_status=status,
        evidence_refs=[{"id": "quote"}],
        blockers=[],
    )
    if status != "READY":
        values.update(current_price=None, margin_to_bear=None, margin_to_base=None)
    values.update(overrides)
    return PriceBridgeResult(**values)


def test_pending_quote_retains_research_and_valuation_while_splitting_data_status():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(),
        bridge(
            "PENDING_EXTERNAL_DATA",
            quote_status="PENDING_EXTERNAL_DATA",
            blockers=["等待已验证收盘行情"],
        ),
    )

    assert outcome.research_conclusion == CONCLUSION_RESEARCH_READY
    assert outcome.price_attractiveness.status == STATUS_NOT_ASSESSABLE
    assert outcome.research_attractive is False
    assert "估值具备研究吸引力" not in outcome.display_text
    assert outcome.valuation_status == "approved_research_only"
    assert outcome.price_bridge_status == "PENDING_EXTERNAL_DATA"
    assert outcome.engineering_status == ENGINEERING_READY
    assert outcome.current_data_status.status == CURRENT_DATA_PENDING_EXTERNAL_DATA
    assert outcome.current_data_status.waiting_for == ["已验证收盘行情"]
    assert "等待已验证收盘行情" in outcome.current_data_status.blockers
    assert "等待已验证收盘行情" not in outcome.blockers
    assert "估值结果已保留" in outcome.display_text


def test_low_confidence_cannot_become_research_attractive():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(confidence="低"),
        bridge(),
        profile_id="quality_compounder",
    )

    assert outcome.research_conclusion == CONCLUSION_RESEARCH_READY
    assert outcome.price_attractiveness.status == STATUS_WAITING_FOR_BETTER_PRICE
    assert outcome.research_attractive is False
    assert "valuation_confidence_low" in outcome.blockers


def test_unperformed_valuation_remains_valuation_not_ready():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(
            status="not_ready",
            bear_value=None,
            base_value=None,
            bull_value=None,
        ),
        bridge("PENDING_EXTERNAL_DATA"),
    )

    assert outcome.research_conclusion == CONCLUSION_VALUATION_NOT_READY
    assert "valuation_not_ready" in outcome.blockers
    assert outcome.current_data_status.status == CURRENT_DATA_PENDING_EXTERNAL_DATA


def test_conditional_research_only_is_not_promoted_to_attractive():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(status="conditional_research_only"),
        bridge(),
    )

    assert outcome.research_conclusion == CONCLUSION_RESEARCH_READY
    assert outcome.price_attractiveness.status == STATUS_KEY_OBSERVATION
    assert outcome.research_attractive is False
    assert "profile_not_identified" in outcome.blockers


def test_stale_and_invalid_price_bridges_do_not_become_attractive():
    stale = evaluate_current_research_status(
        gate(),
        valuation(confidence="高"),
        bridge("STALE_MODEL", model_validity_status="STALE"),
    )
    invalid = evaluate_current_research_status(
        gate(),
        valuation(confidence="高"),
        bridge("INVALID", model_validity_status="INVALID"),
    )

    assert stale.research_conclusion == CONCLUSION_RESEARCH_READY
    assert invalid.research_conclusion == CONCLUSION_RESEARCH_READY
    assert stale.price_attractiveness.status == STATUS_NOT_ASSESSABLE
    assert invalid.price_attractiveness.status == STATUS_NOT_ASSESSABLE
    assert "price_bridge_stale_model" in stale.blockers
    assert "price_bridge_invalid" in invalid.blockers


def test_complete_high_confidence_research_can_be_research_attractive():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(confidence="高"),
        bridge(),
        profile_id="quality_compounder",
    )

    assert outcome.research_conclusion == CONCLUSION_RESEARCH_READY
    assert outcome.price_attractiveness.status == STATUS_RESEARCH_ATTRACTIVE
    assert outcome.research_attractive is True
    assert "估值具备研究吸引力" in outcome.display_text
    assert outcome.current_data_status.status == "READY"


def test_non_attractive_gate_conclusion_is_preserved():
    outcome = evaluate_current_research_status(
        gate(conclusion="研究未完成"),
        valuation(status="not_ready", bear_value=None, base_value=None, bull_value=None),
        bridge("PENDING_EXTERNAL_DATA"),
    )

    assert outcome.research_conclusion == "研究未完成"
    assert outcome.price_attractiveness.status == STATUS_NOT_ASSESSABLE
    assert outcome.research_attractive is False


def test_explicit_current_data_status_must_match_price_bridge():
    matching = CurrentDataStatus(
        status="PENDING_EXTERNAL_DATA",
        waiting_for=["特定公告披露"],
        blockers=[],
        evidence_refs=[{"id": "pending-data"}],
    )
    outcome = evaluate_current_research_status(
        gate(),
        valuation(),
        bridge("PENDING_EXTERNAL_DATA"),
        current_data_status=matching,
    )
    assert outcome.current_data_status.waiting_for == ["特定公告披露"]

    conflicting = replace(matching, status="READY", waiting_for=[])
    with pytest.raises(ValueError, match="contradicts"):
        evaluate_current_research_status(
            gate(),
            valuation(),
            bridge("PENDING_EXTERNAL_DATA"),
            current_data_status=conflicting,
        )


def test_identity_mismatch_and_unknown_statuses_are_rejected():
    with pytest.raises(ValueError, match="symbols must match"):
        evaluate_current_research_status(gate(), valuation(), bridge(symbol="000333"))
    with pytest.raises(ValueError, match="engineering"):
        evaluate_current_research_status(
            gate(), valuation(), bridge(), engineering_status="BLOCKED_BY_DATA"
        )


def test_policy_is_serializable_and_contains_no_trading_state():
    outcome = evaluate_current_research_status(
        gate(),
        valuation(),
        bridge("PENDING_EXTERNAL_DATA", blockers=["等待已验证收盘行情"]),
    )
    policy = outcome.as_policy()
    restored = json.loads(outcome.to_json())

    assert restored == policy
    assert "research_attractive" not in policy
    assert policy["price_attractiveness"]["status"] == STATUS_NOT_ASSESSABLE
    for key in ("trade", "order", "position", "target_weight", "shares"):
        assert key not in json.dumps(policy, ensure_ascii=False)
    assert policy["evidence_refs"] == [{"id": "valuation"}, {"id": "quote"}]


def test_serialized_domain_payloads_restore_before_aggregation():
    outcome = current_research_status_from_payloads(
        gate_payload={
            "results": {
                "G0_证据门": True,
                "G1_财务门": True,
                "G2_商业论点门": True,
                "G3_估值门": True,
            },
            "blockers": [],
            "conclusion": "估值具备研究吸引力",
        },
        valuation_payload=json.loads(valuation().to_json()),
        price_bridge_payload=json.loads(bridge().to_json()),
        profile_id="quality_compounder",
    )

    assert outcome.research_conclusion == CONCLUSION_RESEARCH_READY
    assert outcome.price_attractiveness.status == STATUS_RESEARCH_ATTRACTIVE
    assert outcome.current_data_status.status == "READY"
    assert outcome.evidence_refs == [{"id": "valuation"}, {"id": "quote"}]

    with pytest.raises(ValueError, match="valuation_date"):
        current_research_status_from_payloads(
            gate_payload={
                "results": {},
                "blockers": [],
                "conclusion": "估值未就绪",
            },
            valuation_payload={
                **json.loads(valuation().to_json()),
                "valuation_date": "not-a-date",
            },
            price_bridge_payload=json.loads(bridge().to_json()),
        )
