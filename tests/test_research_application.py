from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.fixed_sample_admission import (
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    FixedSampleAdmissionPolicy,
)
from value_investment_agent.model_validity import MaterialEvent
from value_investment_agent.quote_snapshot import (
    QUOTE_STATUS_VERIFIED_CLOSE,
    QuoteSnapshot,
)
from value_investment_agent.research_application import (
    RUN_COMPLETED_WITH_BLOCKERS,
    RUN_UNSUPPORTED,
    ModelValidityEvaluationInput,
    ResearchApplicationService,
    ResearchRunSpec,
)
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_VALUATION_RESULT,
    SCOPE_SECURITY,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.valuation_models.cyclical import CyclicalFacts
from value_investment_agent.valuation_models.fcff import FinancialFacts
from value_investment_agent.valuation_models.residual_income import (
    MODEL_VERSION,
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


AS_OF = date(2025, 12, 31)
AVAILABLE_AT = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def case(symbol: str, *, industry: str = "测试", path: str = "case.json") -> ResearchCase:
    return ResearchCase(
        symbol=symbol,
        name=f"公司{symbol}",
        as_of=AS_OF,
        run_id="fixture",
        generated_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
        research_version="v1",
        industry=industry,
        investment_path="测试路径",
        thesis="测试论点",
        return_driver="测试驱动",
        mispricing_hypothesis="未证明",
        financial_summary={"period_end": "2025-12-31"},
        positives=[],
        counter_evidence=[],
        thesis_breakers=[],
        next_events=[],
        evidence_status="partial",
        valuation_status="not_ready",
        research_status="financial_scope_blocked",
        blockers=[],
        evidence_refs=[{"id": "case", "path": path, "sha256": "a" * 64}],
        quote_date=None,
        financial_period=AS_OF,
        missing_date_reasons={"quote_date": "not used"},
    )


def service():
    return ResearchApplicationService(InMemoryResearchArtifactRepository())


def residual_facts(symbol: str = "600519") -> QualityCompounderFacts:
    return QualityCompounderFacts(
        symbol=symbol,
        as_of=AS_OF,
        verified=True,
        confidence="低",
        evidence_refs=[{"id": "facts", "path": "facts.json", "sha256": "b" * 64}],
        blockers=[],
        operating_inputs={
            "start_book_equity": D("1000"),
            "ordinary_shares": D("100"),
        },
        scenario_inputs={
            "bear": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.08"),
                terminal_growth=D("0.02"),
            ),
            "base": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.10"),
                terminal_growth=D("0.02"),
            ),
            "bull": ResidualIncomeScenarioInputs(
                cost_of_equity=D("0.10"),
                forecast_roes=(D("0.10"),),
                terminal_roe=D("0.12"),
                terminal_growth=D("0.02"),
            ),
        },
    )


def quality_spec(*, run_id: str, repository=None) -> tuple[ResearchRunSpec, ResearchApplicationService]:
    app = ResearchApplicationService(repository)
    spec = ResearchRunSpec(
        run_id=run_id,
        symbol="600519",
        profile_id="quality_compounder",
        research_case=case("600519", industry="消费品"),
        facts=residual_facts(),
        available_at=AVAILABLE_AT,
    )
    return spec, app


def test_three_profiles_execute_through_one_symbol_free_runner():
    cases = [
        (
            "600519",
            "quality_compounder",
            residual_facts(),
            "conditional_research_only",
        ),
        (
            "000333",
            "mature_manufacturing",
            FinancialFacts(
                symbol="000333",
                as_of=AS_OF,
                verified=False,
                evidence_refs=[{"id": "facts", "path": "facts.json"}],
                blockers=["shares_not_verified"],
            ),
            "not_ready",
        ),
        (
            "601088",
            "cyclical_cash_return",
            CyclicalFacts(
                symbol="601088",
                as_of=AS_OF,
                verified=False,
                confidence="低",
                evidence_refs=[{"id": "facts", "path": "facts.json"}],
                blockers=["cycle_inputs_not_verified"],
            ),
            "not_ready",
        ),
    ]

    app = service()
    for symbol, profile_id, facts, valuation_status in cases:
        spec = ResearchRunSpec(
            run_id=f"run-{symbol}",
            symbol=symbol,
            profile_id=profile_id,
            research_case=case(symbol),
            facts=facts,
            available_at=AVAILABLE_AT,
        )
        outcome = app.run_company_research(spec)

        assert outcome.status == RUN_COMPLETED_WITH_BLOCKERS
        assert outcome.valuation is not None
        assert outcome.valuation.status == valuation_status
        assert outcome.route is not None
        assert "symbol" not in outcome.route.as_policy()
        assert outcome.price_bridge is not None
        assert outcome.price_bridge.bridge_status == "PENDING_EXTERNAL_DATA"
        assert outcome.current_status is not None
        assert outcome.current_status.symbol == symbol

        for artifact_type in (
            ARTIFACT_RESEARCH_CASE,
            ARTIFACT_VALUATION_RESULT,
            ARTIFACT_PRICE_BRIDGE,
            ARTIFACT_CURRENT_RESEARCH_STATUS,
        ):
            artifact = app.repository.load_latest(
                SCOPE_SECURITY, symbol, artifact_type
            )
            assert artifact.envelope.run_id == spec.run_id


def test_verified_quote_and_validity_produce_a_ready_bridge():
    repository = InMemoryResearchArtifactRepository()
    spec, app = quality_spec(run_id="ready-bridge", repository=repository)
    spec = ResearchRunSpec(
        run_id=spec.run_id,
        symbol=spec.symbol,
        profile_id=spec.profile_id,
        research_case=spec.research_case,
        facts=spec.facts,
        available_at=spec.available_at,
        quote=QuoteSnapshot(
            symbol="600519",
            quote_date=AS_OF,
            current_price=D("5"),
            status=QUOTE_STATUS_VERIFIED_CLOSE,
            evidence_refs=[
                {"id": "quote", "path": "quote.json", "sha256": "c" * 64}
            ],
        ),
        model_validity_input=ModelValidityEvaluationInput(
            model_id=MODEL_VERSION,
            valid_from=AS_OF,
            event_scan_evidence_refs=(
                {"id": "event-scan", "path": "events.json", "sha256": "d" * 64},
            ),
        ),
    )

    outcome = app.run_company_research(spec)

    assert outcome.model_validity is not None
    assert outcome.model_validity.status == "VALID"
    assert outcome.price_bridge is not None
    assert outcome.price_bridge.bridge_status == "READY"
    assert outcome.price_bridge.current_price == D("5")
    assert outcome.price_bridge.margin_to_bear > 0
    assert app.repository.load_latest(
        SCOPE_SECURITY, "600519", ARTIFACT_MODEL_VALIDITY
    )
    assert app.repository.load_latest(
        SCOPE_SECURITY, "600519", ARTIFACT_QUOTE_SNAPSHOT
    )


def test_verified_quote_without_validity_contract_fails_closed_as_invalid_bridge():
    spec, app = quality_spec(run_id="missing-validity")
    spec = ResearchRunSpec(
        run_id=spec.run_id,
        symbol=spec.symbol,
        profile_id=spec.profile_id,
        research_case=spec.research_case,
        facts=spec.facts,
        available_at=spec.available_at,
        quote=QuoteSnapshot(
            symbol="600519",
            quote_date=AS_OF,
            current_price=D("5"),
            status=QUOTE_STATUS_VERIFIED_CLOSE,
            evidence_refs=[
                {"id": "quote", "path": "quote.json", "sha256": "c" * 64}
            ],
        ),
    )

    outcome = app.run_company_research(spec)

    assert outcome.price_bridge is not None
    assert outcome.price_bridge.bridge_status == "INVALID"
    assert "verified quote requires a model validity input" in outcome.price_bridge.blockers


def test_unsupported_model_route_is_a_typed_outcome_without_downstream_artifacts():
    repository = InMemoryResearchArtifactRepository()
    app = ResearchApplicationService(repository)
    spec = ResearchRunSpec(
        run_id="unsupported",
        symbol="000333",
        profile_id="mature_manufacturing",
        requested_model="generic_pe",
        research_case=case("000333", industry="家电"),
        facts=FinancialFacts(
            symbol="000333",
            as_of=AS_OF,
            verified=False,
            evidence_refs=[{"id": "facts", "path": "facts.json"}],
            blockers=[],
        ),
        available_at=AVAILABLE_AT,
    )

    outcome = app.run_company_research(spec)

    assert outcome.status == RUN_UNSUPPORTED
    assert outcome.gate is None
    assert outcome.valuation is None
    assert outcome.current_status is None
    assert "model_not_authorized_for_profile:generic_pe" in outcome.blockers
    assert repository._artifacts == {}


def test_identity_or_contract_mismatches_fail_closed():
    repository = InMemoryResearchArtifactRepository()
    app = ResearchApplicationService(repository)
    base = ResearchRunSpec(
        run_id="bad-symbol",
        symbol="600519",
        profile_id="quality_compounder",
        research_case=case("600519"),
        facts=residual_facts(),
        available_at=AVAILABLE_AT,
    )
    from dataclasses import replace

    with pytest.raises(ValueError, match="symbol"):
        ResearchRunSpec(
            **{
                **base.__dict__,
                "symbol": "600519",
                "research_case": case("000333"),
            }
        )
    with pytest.raises(TypeError, match="facts"):
        app.run_company_research(
            replace(base, facts=FinancialFacts(
                symbol="600519",
                as_of=AS_OF,
                verified=False,
                evidence_refs=[{"id": "facts"}],
                blockers=[],
            ))
        )


def test_review_company_research_preserves_research_only_boundary():
    spec, app = quality_spec(run_id="review-boundary")
    outcome = app.run_company_research(spec)
    policy = FixedSampleAdmissionPolicy(
        profile_id="quality_compounder",
        decision=DECISION_CONTINUE_CONDITIONAL_MODEL,
        decision_reason="保留条件估值，仅研究。",
        cash_return_status="PARTIAL",
        cash_return_explanation="现金回报研究未完成。",
        admission_evidence=("六位证券代码", "带证据引用的 ResearchCase"),
        required_evidence=("正式估值人工批准", "当前股本证据"),
    )

    review = app.review_company_research(outcome, policy)

    assert review.action == "no_order"
    assert review.human_confirmation_required is True
    assert review.production_valuation_available is False
    assert review.research_sample_members == ("600519",)
    assert review.companies[0].action == "no_order"

