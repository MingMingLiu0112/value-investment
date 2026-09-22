from datetime import date
from decimal import Decimal
import json
from pathlib import Path

import pytest

from value_investment_agent.fixed_sample_admission import (
    BOUNDED_VALUE_CONDITIONAL,
    BOUNDED_VALUE_NOT_AVAILABLE,
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    DECISION_PAUSE_PRODUCTION_VALUATION,
    DECISION_RESOLVE_MODEL_INPUTS,
    ENGINEERING_REUSABLE,
    PRODUCTION_VALUATION_NOT_AVAILABLE,
    RESEARCH_SAMPLE_ADMITTED,
    RESEARCH_SAMPLE_REJECTED,
    FixedSampleAdmissionPolicy,
    assess_fixed_sample_company,
    review_fixed_sample,
)
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_bridge import bridge
from value_investment_agent.valuation_models.base import ValuationResult


ROOT = Path(__file__).resolve().parents[1]
MODEL_REF = {"id": "fixture-model", "path": "fixtures/model.json", "sha256": "model-hash"}
QUOTE_REF = {"id": "fixture-quote", "path": "fixtures/quote.json", "sha256": "quote-hash"}
EVENT_REF = {"id": "fixture-events", "path": "fixtures/events.json", "sha256": "event-hash"}


def _valuation(status="ready", *, confidence="中", scenarios=True, model_type="residual_income_or_equity_value"):
    values = (
        (Decimal("400"), Decimal("500"), Decimal("600"))
        if scenarios
        else (None, None, None)
    )
    return ValuationResult(
        symbol="600519",
        model_type=model_type,
        valuation_date=date(2026, 9, 18),
        bear_value=values[0],
        base_value=values[1],
        bull_value=values[2],
        confidence=confidence,
        assumptions={},
        sensitivities=[],
        evidence_refs=[MODEL_REF],
        blockers=[] if scenarios else ["missing-scenario"],
        status=status,
        model_version="fixture-v1",
    )


def _validity(status="VALID"):
    if status == "VALID":
        return ModelValidity(
            model_id="fixture-v1",
            symbol="600519",
            model_as_of=date(2026, 9, 18),
            valid_from=date(2026, 9, 18),
            last_material_event_check=date(2026, 9, 18),
            financial_statement_changed=False,
            capital_structure_changed=False,
            material_event_found=False,
            status="VALID",
            blockers=[],
            evidence_refs=[EVENT_REF],
        )
    return ModelValidity(
        model_id="fixture-v1",
        symbol="600519",
        model_as_of=date(2026, 9, 18),
        valid_from=date(2026, 9, 18),
        last_material_event_check=None,
        financial_statement_changed=None,
        capital_structure_changed=None,
        material_event_found=None,
        status="UNKNOWN",
        blockers=["event check missing"],
        evidence_refs=[EVENT_REF],
    )


def _gate(ready=True):
    return {
        "results": {
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": ready,
        },
        "blockers": [] if ready else ["valuation-not-ready"],
        "conclusion": "研究与估值已就绪" if ready else "估值未就绪",
    }


def _payload(valuation, formal_approved=False, *, ready_bridge=False):
    if ready_bridge:
        bridge_result = bridge(
            valuation,
            _validity("VALID"),
            quote_date=date(2026, 9, 18),
            current_price=Decimal("450"),
            quote_status="verified_close",
            evidence_refs=[QUOTE_REF],
        )
    else:
        bridge_result = bridge(
            valuation,
            _validity("UNKNOWN"),
            quote_date=None,
            current_price=None,
            quote_status="PENDING_EXTERNAL_DATA",
            evidence_refs=[],
        )
    return {
        "version": "fixture-v1",
        "result": json.loads(valuation.to_json()),
        "price_bridge": json.loads(bridge_result.to_json()),
        "model_validity": json.loads(_validity().to_json()),
        "valuation_approved": formal_approved,
        "formal_fair_value": None,
        "trade_approved": False,
        "live_eligible": False,
    }


def _policy(
    decision=DECISION_CONTINUE_CONDITIONAL_MODEL,
    *,
    cash_status="PARTIAL",
):
    return FixedSampleAdmissionPolicy(
        profile_id="quality_compounder",
        decision=decision,
        decision_reason="explicit research decision",
        cash_return_status=cash_status,
        cash_return_explanation="historical distribution evidence only",
        admission_evidence=("research-case-evidence", "profile-route"),
        required_evidence=("register-formal-model",),
    )


def test_policy_requires_an_explicit_decision_and_required_evidence():
    with pytest.raises(ValueError, match="requires the evidence"):
        FixedSampleAdmissionPolicy(
            profile_id="quality_compounder",
            decision=DECISION_CONTINUE_CONDITIONAL_MODEL,
            decision_reason="reason",
            cash_return_status="PARTIAL",
            cash_return_explanation="explanation",
            admission_evidence=("research-case-evidence",),
            required_evidence=(),
        )


def test_conditional_valuation_is_never_promoted_to_production_available():
    valuation = _valuation("conditional_research_only", confidence="低")
    assessment = assess_fixed_sample_company(
        gate_payload=_gate(ready=False),
        result_payload=json.loads(valuation.to_json()),
        price_bridge_payload=json.loads(
            bridge(
                valuation,
                _validity("UNKNOWN"),
                quote_date=None,
                current_price=None,
                quote_status="PENDING_EXTERNAL_DATA",
                evidence_refs=[],
            ).to_json()
        ),
        policy=_policy(),
        formal_valuation_approved=False,
        research_evidence_refs=[MODEL_REF],
        model_validity_payload=json.loads(_validity("UNKNOWN").to_json()),
    )

    assert assessment.bounded_value_judgment == BOUNDED_VALUE_CONDITIONAL
    assert assessment.production_valuation_status == PRODUCTION_VALUATION_NOT_AVAILABLE
    assert assessment.decision == DECISION_CONTINUE_CONDITIONAL_MODEL
    assert "formal_valuation_not_approved" in assessment.blockers


def test_missing_scenarios_fail_closed_with_an_explicit_resolution_decision():
    valuation = _valuation("not_ready", scenarios=False)
    assessment = assess_fixed_sample_company(
        gate_payload=_gate(ready=False),
        result_payload=json.loads(valuation.to_json()),
        price_bridge_payload=json.loads(
            bridge(
                valuation,
                _validity("UNKNOWN"),
                quote_date=None,
                current_price=None,
                quote_status="PENDING_EXTERNAL_DATA",
                evidence_refs=[],
            ).to_json()
        ),
        policy=_policy(decision=DECISION_RESOLVE_MODEL_INPUTS),
        formal_valuation_approved=False,
        research_evidence_refs=[MODEL_REF],
        model_validity_payload=json.loads(_validity("UNKNOWN").to_json()),
    )

    assert assessment.bounded_value_judgment == BOUNDED_VALUE_NOT_AVAILABLE
    assert assessment.production_valuation_status == PRODUCTION_VALUATION_NOT_AVAILABLE
    assert assessment.research_sample_status == RESEARCH_SAMPLE_ADMITTED
    assert assessment.required_evidence
    assert assessment.human_confirmation_required is True
    assert assessment.action == "no_order"


def test_missing_research_evidence_rejects_sample_admission():
    valuation = _valuation("not_ready", scenarios=False)
    assessment = assess_fixed_sample_company(
        gate_payload=_gate(ready=False),
        result_payload=json.loads(valuation.to_json()),
        price_bridge_payload=json.loads(
            bridge(
                valuation,
                _validity("UNKNOWN"),
                quote_date=None,
                current_price=None,
                quote_status="PENDING_EXTERNAL_DATA",
                evidence_refs=[],
            ).to_json()
        ),
        policy=_policy(decision=DECISION_RESOLVE_MODEL_INPUTS),
        formal_valuation_approved=False,
        research_evidence_refs=[],
        model_validity_payload=json.loads(_validity("UNKNOWN").to_json()),
    )

    assert assessment.research_sample_status == RESEARCH_SAMPLE_REJECTED
    assert "research_sample_admission_evidence_not_met" in assessment.blockers


def test_profile_route_must_match_the_valuation_model_type():
    valuation = _valuation("not_ready", scenarios=False, model_type="FCFF")
    assessment = assess_fixed_sample_company(
        gate_payload=_gate(ready=False),
        result_payload=json.loads(valuation.to_json()),
        price_bridge_payload=json.loads(
            bridge(
                valuation,
                _validity("UNKNOWN"),
                quote_date=None,
                current_price=None,
                quote_status="PENDING_EXTERNAL_DATA",
                evidence_refs=[],
            ).to_json()
        ),
        policy=_policy(decision=DECISION_RESOLVE_MODEL_INPUTS),
        formal_valuation_approved=False,
        research_evidence_refs=[MODEL_REF],
        model_validity_payload=json.loads(_validity("UNKNOWN").to_json()),
    )

    assert assessment.engineering_contract_reusable is False
    assert "valuation_model_does_not_match_profile_route" in assessment.blockers


def test_formal_ready_valuation_can_be_production_available_but_not_a_trade():
    valuation = _valuation("ready")
    assessment = assess_fixed_sample_company(
        gate_payload=_gate(ready=True),
        result_payload=json.loads(valuation.to_json()),
        price_bridge_payload=json.loads(
            bridge(
                valuation,
                _validity("VALID"),
                quote_date=date(2026, 9, 18),
                current_price=Decimal("450"),
                quote_status="verified_close",
                evidence_refs=[QUOTE_REF],
            ).to_json()
        ),
        policy=_policy(decision=DECISION_CONTINUE_CONDITIONAL_MODEL),
        formal_valuation_approved=True,
        research_evidence_refs=[MODEL_REF],
        model_validity_payload=json.loads(_validity("VALID").to_json()),
    )

    assert assessment.production_valuation_status == "AVAILABLE"
    assert assessment.action == "no_order"
    assert assessment.human_confirmation_required is True


def test_identity_conflict_is_rejected_by_the_shared_pipeline():
    valuation = _valuation("ready")
    bad_bridge = json.loads(
        bridge(
            valuation,
            _validity("VALID"),
            quote_date=date(2026, 9, 18),
            current_price=Decimal("450"),
            quote_status="verified_close",
            evidence_refs=[QUOTE_REF],
        ).to_json()
    )
    bad_bridge["symbol"] = "000333"
    bad_bridge["quote_symbol"] = "000333"
    with pytest.raises(ValueError, match="symbols differ"):
        assess_fixed_sample_company(
            gate_payload=_gate(),
            result_payload=json.loads(valuation.to_json()),
            price_bridge_payload=bad_bridge,
            policy=_policy(),
            formal_valuation_approved=True,
            research_evidence_refs=[MODEL_REF],
            model_validity_payload=json.loads(_validity("VALID").to_json()),
        )


def test_review_requires_matching_explicit_policy_registry():
    valuation = _valuation("not_ready", scenarios=False)
    payload = _payload(valuation)
    with pytest.raises(ValueError, match="policies must match"):
        review_fixed_sample(
            research_records=[{"case": {"symbol": "600519", "evidence_refs": []}, "gate": _gate(False)}],
            valuation_payloads={"600519": payload},
            policies={},
            as_of=date(2026, 9, 22),
        )


def test_review_separates_reusable_orchestration_from_production_valuation():
    valuation = _valuation("not_ready", scenarios=False)
    payload = _payload(valuation)
    review = review_fixed_sample(
        research_records=[{"case": {"symbol": "600519", "evidence_refs": [MODEL_REF]}, "gate": _gate(False)}],
        valuation_payloads={"600519": payload},
        policies={"600519": _policy(decision=DECISION_RESOLVE_MODEL_INPUTS)},
        as_of=date(2026, 9, 22),
    )
    policy = review.as_policy()
    restored = json.loads(review.to_json())

    assert review.engineering_orchestration_status == ENGINEERING_REUSABLE
    assert review.production_valuation_available is False
    assert restored == policy
    assert policy["action"] == "no_order"
    for forbidden in ("trade", "position", "target_weight", "shares"):
        assert forbidden not in json.dumps(policy, ensure_ascii=False)


@pytest.mark.skipif(
    not (ROOT / "runtime/excel-mvp-research-cases/evidence.json").is_file(),
    reason="frozen runtime evidence is not available in a clean checkout",
)
def test_frozen_three_company_payloads_are_reviewed_through_one_entrypoint():
    research_pointer = json.loads(
        (ROOT / "runtime/excel-mvp-research-cases-latest.json").read_text(encoding="utf-8")
    )
    research_path = ROOT / str(research_pointer["path"]).replace("\\", "/") / "evidence.json"
    research = json.loads(research_path.read_text(encoding="utf-8"))
    valuation_pointers = {
        "600519": "runtime/valuation-results/600519-current-equity-stage-b-latest.json",
        "000333": "runtime/valuation-results/000333-fcff-stage-b-latest.json",
        "601088": "runtime/valuation-results/601088-cyclical-stage-b-latest.json",
    }
    valuation_payloads = {}
    for symbol, pointer_name in valuation_pointers.items():
        pointer = json.loads((ROOT / pointer_name).read_text(encoding="utf-8"))
        path = ROOT / str(pointer["path"]).replace("\\", "/") / "evidence.json"
        valuation_payloads[symbol] = json.loads(path.read_text(encoding="utf-8"))

    policies = {
        "600519": FixedSampleAdmissionPolicy(
            profile_id="quality_compounder",
            decision=DECISION_CONTINUE_CONDITIONAL_MODEL,
            decision_reason="低置信度条件估值保留，正式估值与 G3 仍需完成。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有历史分配与现金覆盖证据，未完成可持续性评估。",
            admission_evidence=("研究案例与证据", "quality_compounder 模型路由"),
            required_evidence=("正式估值通过", "当前股本与估值日期绑定"),
        ),
        "000333": FixedSampleAdmissionPolicy(
            profile_id="mature_manufacturing",
            decision=DECISION_RESOLVE_MODEL_INPUTS,
            decision_reason="先补齐 FCFF 输入和股份分母，再形成情景估值。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有历史派息与现金回报候选材料，未完成可持续性评估。",
            admission_evidence=("研究案例与证据", "mature_manufacturing 模型路由"),
            required_evidence=("FCFF 输入", "当前 A/H 估值股份分母"),
        ),
        "601088": FixedSampleAdmissionPolicy(
            profile_id="cyclical_cash_return",
            decision=DECISION_PAUSE_PRODUCTION_VALUATION,
            decision_reason="周期正常化输入未注册，暂停生产估值，不做正式价值判断。",
            cash_return_status="PARTIAL",
            cash_return_explanation="已有派息与周期现金回报候选材料，未完成可持续性评估。",
            admission_evidence=("研究案例与证据", "cyclical_cash_return 模型路由"),
            required_evidence=("周期正常化输入", "成本运输口径对账"),
        ),
    }
    review = review_fixed_sample(
        research_records=research["records"],
        valuation_payloads=valuation_payloads,
        policies=policies,
        as_of=date(2026, 9, 22),
    )
    companies = {company.symbol: company for company in review.companies}

    assert review.engineering_orchestration_status == ENGINEERING_REUSABLE
    assert review.production_valuation_available is False
    assert set(review.research_sample_members) == {"600519", "000333", "601088"}
    assert companies["600519"].bounded_value_judgment == BOUNDED_VALUE_CONDITIONAL
    assert companies["000333"].bounded_value_judgment == BOUNDED_VALUE_NOT_AVAILABLE
    assert companies["601088"].bounded_value_judgment == BOUNDED_VALUE_NOT_AVAILABLE
    assert all(company.action == "no_order" for company in review.companies)
    assert all(company.required_evidence for company in review.companies)
