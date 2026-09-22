from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from value_investment_agent.current_research_status import (
    CURRENT_DATA_PENDING_EXTERNAL_DATA,
    CurrentDataStatus,
    CurrentResearchStatus,
)
from value_investment_agent.distribution import DividendResearchResult
from value_investment_agent.fixed_sample_admission import (
    DECISION_RESOLVE_MODEL_INPUTS,
    BOUNDED_VALUE_NOT_AVAILABLE,
    CASH_RETURN_NOT_ASSESSED,
    ENGINEERING_REUSABLE,
    PRODUCTION_VALUATION_NOT_AVAILABLE,
    RESEARCH_SAMPLE_ADMITTED,
    FixedSampleAdmissionReview,
    FixedSampleCompanyAdmission,
)
from value_investment_agent.model_validity import ModelValidity
from value_investment_agent.price_attractiveness import (
    STATUS_NOT_ASSESSABLE,
    PriceAttractivenessAssessment,
)
from value_investment_agent.price_bridge import pending_price_bridge_for_incomplete_valuation
from value_investment_agent.quote_snapshot import (
    QUOTE_STATUS_PENDING_EXTERNAL_DATA,
    QuoteSnapshot,
)
from value_investment_agent.research_artifact_codecs import (
    decode_artifact,
    artifact_payload,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_FIXED_SAMPLE_ADMISSION,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_ASSUMPTIONS,
    ARTIFACT_VALUATION_RESULT,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_gate import ResearchGate
from value_investment_agent.valuation_assumptions import (
    ValuationAssumption,
    ValuationAssumptionSet,
)
from value_investment_agent.valuation_models.base import ValuationResult


REF = {"id": "e-1", "sha256": "a" * 64}


def _case() -> ResearchCase:
    return ResearchCase(
        symbol="600519",
        name="贵州茅台",
        as_of=date(2026, 9, 21),
        run_id="run-1",
        generated_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
        research_version="v1",
        industry="白酒",
        investment_path="quality_compounder",
        thesis="品牌和渠道形成持续现金回报",
        return_driver="高端白酒真实需求",
        mispricing_hypothesis="市场低估增长确定性",
        financial_summary={"roe": "0.30"},
        positives=[{"kind": "fact", "text": "稳定净现金", "evidence_refs": ["e-1"]}],
        counter_evidence=[
            {"kind": "fact", "text": "需求波动", "evidence_refs": ["e-1"]}
        ],
        thesis_breakers=[
            {"kind": "hypothesis", "text": "需求永久下降", "evidence_refs": ["e-1"]}
        ],
        next_events=[{"kind": "gap", "text": "年度报告"}],
        evidence_status="verified",
        valuation_status="not_ready",
        research_status="financial_scope_approved",
        blockers=["g3"],
        evidence_refs=[REF],
        quote_date=None,
        financial_period=None,
        missing_date_reasons={"quote_date": "missing", "financial_period": "missing"},
    )


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol="600519",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2026, 9, 21),
        bear_value=None,
        base_value=None,
        bull_value=None,
        confidence="低",
        assumptions={},
        sensitivities=[],
        evidence_refs=[REF],
        blockers=["inputs_missing"],
        status="not_ready",
        model_version="model-v1",
    )


def _roundtrip(artifact_type, value, **dependencies):
    _, payload = artifact_payload(value)
    restored = decode_artifact(artifact_type, payload, dependencies=dependencies)
    _, restored_payload = artifact_payload(restored)
    assert restored_payload == payload


def test_research_case_and_gate_roundtrip():
    _roundtrip(ARTIFACT_RESEARCH_CASE, _case())
    gate = ResearchGate(
        symbol="600519",
        results={"G0_证据门": True, "G1_财务门": False},
        blockers=["G1_财务门"],
        conclusion="研究未完成",
    )
    _roundtrip(ARTIFACT_RESEARCH_GATE, gate)


def test_assumptions_and_valuation_roundtrip():
    assumption = ValuationAssumption(
        name="growth",
        unit="percent",
        bear=Decimal("1"),
        base=Decimal("3"),
        bull=Decimal("5"),
        basis="history",
        rationale="franchise",
        as_of=date(2026, 9, 21),
        confidence="low",
        sensitivity="high",
        evidence_refs=[REF],
        blockers=[],
    )
    assumption_set = ValuationAssumptionSet(
        symbol="600519",
        profile_id="quality_compounder",
        model_type="residual_income_or_equity_value",
        as_of=date(2026, 9, 21),
        assumptions=[assumption],
        status="READY",
        blockers=[],
        evidence_refs=[REF],
    )
    _roundtrip(ARTIFACT_VALUATION_ASSUMPTIONS, assumption_set)
    _roundtrip(ARTIFACT_VALUATION_RESULT, _valuation())


def test_model_validity_quote_and_price_bridge_roundtrip():
    validity = ModelValidity(
        model_id="model-v1",
        symbol="600519",
        model_as_of=date(2026, 9, 21),
        valid_from=date(2026, 9, 21),
        last_material_event_check=None,
        financial_statement_changed=None,
        capital_structure_changed=None,
        material_event_found=None,
        status="UNKNOWN",
        blockers=["event_scan_missing"],
        evidence_refs=[],
    )
    _roundtrip(ARTIFACT_MODEL_VALIDITY, validity)

    quote = QuoteSnapshot(
        symbol="600519",
        quote_date=None,
        current_price=None,
        status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
        evidence_refs=[REF],
    )
    _roundtrip(ARTIFACT_QUOTE_SNAPSHOT, quote)

    valuation = _valuation()
    bridge = pending_price_bridge_for_incomplete_valuation(
        valuation,
        evidence_refs=[REF],
    )
    _roundtrip(
        ARTIFACT_PRICE_BRIDGE,
        bridge,
        valuation=valuation,
    )


def test_status_distribution_and_admission_roundtrip():
    status = CurrentResearchStatus(
        symbol="600519",
        research_conclusion="估值未就绪",
        valuation_status="not_ready",
        price_bridge_status="PENDING_EXTERNAL_DATA",
        engineering_status="READY",
        current_data_status=CurrentDataStatus(
            status=CURRENT_DATA_PENDING_EXTERNAL_DATA,
            waiting_for=["已验证收盘行情"],
            blockers=["quote_missing"],
            evidence_refs=[REF],
        ),
        price_attractiveness=PriceAttractivenessAssessment(
            symbol="600519",
            profile_id="quality_compounder",
            status=STATUS_NOT_ASSESSABLE,
            margin_to_bear=None,
            margin_to_base=None,
            downside_reference=None,
            upside_reference=None,
            confidence="低",
            reasons=["no bridge"],
            blockers=["no_ready_bridge"],
            evidence_refs=[REF],
        ),
        display_text="估值未就绪",
        blockers=["valuation_not_ready"],
        evidence_refs=[REF],
    )
    _roundtrip(ARTIFACT_CURRENT_RESEARCH_STATUS, status)

    dividend = DividendResearchResult(
        symbol="600519",
        profile_id="quality_compounder",
        history=None,
        capacity=None,
        sustainability=None,
        yield_snapshots=(),
        as_of=date(2026, 9, 21),
        blockers=["distribution_incomplete"],
    )
    _roundtrip(ARTIFACT_DIVIDEND_RESEARCH, dividend)

    company = FixedSampleCompanyAdmission(
        symbol="600519",
        profile_id="quality_compounder",
        engineering_contract_reusable=True,
        research_sample_status=RESEARCH_SAMPLE_ADMITTED,
        admission_evidence=["研究案例", "模型路由"],
        production_valuation_status=PRODUCTION_VALUATION_NOT_AVAILABLE,
        bounded_value_judgment=BOUNDED_VALUE_NOT_AVAILABLE,
        cash_return_status=CASH_RETURN_NOT_ASSESSED,
        cash_return_explanation="",
        decision=DECISION_RESOLVE_MODEL_INPUTS,
        decision_reason="补齐输入",
        required_evidence=["模型输入"],
        blockers=["valuation_not_ready"],
        evidence_refs=[REF],
        human_confirmation_required=True,
        action="no_order",
    )
    review = FixedSampleAdmissionReview(
        protocol_version="fixed-sample-admission-v1",
        rule_version="fixed-sample-admission-v1",
        as_of=date(2026, 9, 21),
        engineering_orchestration_status=ENGINEERING_REUSABLE,
        production_valuation_available=False,
        research_sample_members=("600519",),
        companies=(company,),
        blockers=["valuation_not_ready"],
        evidence_refs=[REF],
        human_confirmation_required=True,
        action="no_order",
        interpretation="research only",
    )
    _roundtrip(ARTIFACT_FIXED_SAMPLE_ADMISSION, review)
