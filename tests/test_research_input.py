from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.research_application import (
    ResearchApplicationService,
    ResearchRunSpec,
)
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_input import (
    build_research_run_spec,
    descriptor_from_payload,
    descriptor_sha256,
    finalize_input_descriptor,
    ResearchInputDescriptor,
)
from value_investment_agent.research_run_contract import (
    AssumptionScenarioBinding,
    ResearchDependencyFingerprint,
    ResearchPitFrame,
    ResearchSourceDescriptor,
    ResearchValuationApproval,
)
from value_investment_agent.valuation_assumptions import (
    ValuationAssumption,
    build_valuation_assumption_set,
)
from value_investment_agent.valuation_models.residual_income import (
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)


AS_OF = date(2025, 12, 31)
AVAILABLE_AT = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
COMPUTED_AT = datetime(2026, 9, 21, 13, 0, tzinfo=timezone.utc)


def _case() -> ResearchCase:
    return ResearchCase(
        symbol="600519",
        name="贵州茅台",
        as_of=AS_OF,
        run_id="fixture",
        generated_at=datetime(2025, 12, 31, 12, 0, tzinfo=timezone.utc),
        research_version="v1",
        industry="白酒",
        investment_path="quality_compounder",
        thesis="品牌和渠道形成持续现金回报",
        return_driver="高端白酒真实需求",
        mispricing_hypothesis="市场低估增长确定性",
        financial_summary={"period_end": AS_OF.isoformat()},
        positives=[
            {
                "kind": "fact",
                "text": "稳定净现金",
                "evidence_refs": ["e-1"],
            }
        ],
        counter_evidence=[
            {
                "kind": "fact",
                "text": "需求波动",
                "evidence_refs": ["e-1"],
            }
        ],
        thesis_breakers=[
            {
                "kind": "hypothesis",
                "text": "需求永久下降",
                "evidence_refs": ["e-1"],
            }
        ],
        next_events=[{"kind": "gap", "text": "年度报告"}],
        evidence_status="verified",
        valuation_status="not_ready",
        research_status="financial_scope_approved",
        blockers=["g3"],
        evidence_refs=[{"id": "e-1", "sha256": "a" * 64}],
        quote_date=None,
        financial_period=AS_OF,
        missing_date_reasons={"quote_date": "not used"},
    )


def _facts() -> QualityCompounderFacts:
    return QualityCompounderFacts(
        symbol="600519",
        as_of=AS_OF,
        verified=True,
        confidence="低",
        evidence_refs=[{"id": "f-1", "sha256": "b" * 64}],
        blockers=[],
        operating_inputs={
            "start_book_equity": Decimal("1000"),
            "ordinary_shares": Decimal("100"),
        },
        scenario_inputs={
            "bear": ResidualIncomeScenarioInputs(
                cost_of_equity=Decimal("0.10"),
                forecast_roes=(Decimal("0.10"),),
                terminal_roe=Decimal("0.08"),
                terminal_growth=Decimal("0.02"),
            ),
            "base": ResidualIncomeScenarioInputs(
                cost_of_equity=Decimal("0.10"),
                forecast_roes=(Decimal("0.10"),),
                terminal_roe=Decimal("0.10"),
                terminal_growth=Decimal("0.02"),
            ),
            "bull": ResidualIncomeScenarioInputs(
                cost_of_equity=Decimal("0.10"),
                forecast_roes=(Decimal("0.10"),),
                terminal_roe=Decimal("0.12"),
                terminal_growth=Decimal("0.02"),
            ),
        },
    )


def _assumptions():
    assumption = ValuationAssumption(
        name="terminal_roe",
        unit="percent",
        bear=Decimal("0.08"),
        base=Decimal("0.10"),
        bull=Decimal("0.12"),
        basis="franchise economics",
        rationale="explicit bounded scenario",
        as_of=AS_OF,
        confidence="low",
        sensitivity="high",
        evidence_refs=[{"id": "a-1", "sha256": "c" * 64}],
        blockers=[],
    )
    return build_valuation_assumption_set(
        symbol="600519",
        profile_id="quality_compounder",
        model_type="residual_income_or_equity_value",
        as_of=AS_OF,
        assumptions=[assumption],
        evidence_refs=[{"id": "a-1", "sha256": "c" * 64}],
    )


def _source(*, published_at=None):
    return ResearchSourceDescriptor(
        id="facts-source",
        kind="filing",
        location="tests/fixtures/facts.json",
        sha256="d" * 64,
        published_at=published_at,
        retrieved_at=datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc),
        parser_version="parser-v1",
    )


def _binding(expected=Decimal("0.10")):
    return AssumptionScenarioBinding(
        assumption_name="terminal_roe",
        scenario="base",
        field_path="terminal_roe",
        expected_value=expected,
        evidence_refs=({"id": "a-1", "sha256": "c" * 64},),
    )


def _descriptor(*, binding=None, source=None, approval=None):
    return finalize_input_descriptor(
        ResearchInputDescriptor(
            schema_version="m1-fixed-sample-input-v1",
            descriptor_version="fixture-v1",
            symbol="600519",
            name="贵州茅台",
            profile_id="quality_compounder",
            requested_model=None,
            run_id="descriptor-run",
            point_in_time=ResearchPitFrame(
                report_period=AS_OF,
                research_as_of=AS_OF,
                valuation_date=AS_OF,
                available_at=AVAILABLE_AT,
                computed_at=COMPUTED_AT,
            ),
            dependencies=ResearchDependencyFingerprint(
                rule_version="m1-input-v1",
                profile_id="quality_compounder",
                model_id="residual_income_or_equity_value",
                model_version="residual-income-equity-shared-v1",
                parser_version="parser-v1",
                scan_watermark="scan-v1",
            ),
            sources=(source or _source(),),
            research_case=_case(),
            facts=_facts(),
            assumptions=_assumptions(),
            assumption_bindings=(binding or _binding(),),
            distribution_result=None,
            quote=None,
            model_validity_input=None,
            valuation_approval=approval,
        )
    )


def test_descriptor_round_trip_preserves_hash_and_typed_spec():
    descriptor = _descriptor()
    payload = descriptor.as_policy()
    restored = descriptor_from_payload(payload)

    assert restored.as_policy() == payload
    assert restored.input_sha256 == descriptor_sha256(descriptor)
    spec = build_research_run_spec(restored)
    assert isinstance(spec, ResearchRunSpec)
    assert spec.as_of == AS_OF
    assert spec.input_descriptor_sha256 == descriptor.input_sha256


def test_descriptor_round_trip_preserves_valuation_approval():
    approval = ResearchValuationApproval(
        model_id="residual_income_or_equity_value",
        model_type="residual_income_or_equity_value",
        model_version="residual-income-equity-shared-v1",
        valuation_date=AS_OF,
        result_sha256="e" * 64,
        approved_at=AVAILABLE_AT,
        approver="human-reviewer",
        evidence_refs=({"id": "approval", "sha256": "f" * 64},),
    )
    descriptor = _descriptor(approval=approval)
    restored = descriptor_from_payload(descriptor.as_policy())

    assert restored.valuation_approval == approval
    assert restored.as_policy() == descriptor.as_policy()
    spec = build_research_run_spec(restored)
    assert spec.valuation_approval == approval


def test_descriptor_accepts_tampered_payload_only_when_hash_is_consistent():
    descriptor = _descriptor()
    payload = descriptor.as_policy()
    payload["facts"]["operating_inputs"]["start_book_equity"] = "999"

    with pytest.raises(ValueError, match="hash does not match"):
        descriptor_from_payload(payload)


def test_descriptor_rejects_assumption_binding_mismatch():
    with pytest.raises(ValueError, match="binding is invalid"):
        _descriptor(binding=_binding(Decimal("0.11")))


def test_descriptor_rejects_source_available_after_input_availability():
    between = datetime(2026, 9, 21, 12, 30, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="published after availability"):
        _descriptor(source=_source(published_at=between))


def test_descriptor_rejects_source_retrieved_after_input_availability():
    between = datetime(2026, 9, 21, 12, 30, tzinfo=timezone.utc)
    source = replace(_source(), retrieved_at=between)
    with pytest.raises(ValueError, match="retrieved after availability"):
        _descriptor(source=source)


def test_pit_frame_rejects_valuation_after_research_as_of():
    with pytest.raises(ValueError, match="Valuation date"):
        ResearchPitFrame(
            report_period=AS_OF,
            research_as_of=AS_OF,
            valuation_date=date(2026, 1, 1),
            available_at=AVAILABLE_AT,
            computed_at=COMPUTED_AT,
        )


def test_run_spec_rejects_as_of_masking_and_future_availability():
    descriptor = _descriptor()
    spec = build_research_run_spec(descriptor)
    old_facts = replace(_facts(), as_of=date(2024, 12, 31))

    with pytest.raises(ValueError, match="cannot override"):
        replace(spec, as_of=date(2025, 12, 30))
    with pytest.raises(ValueError, match="cannot override"):
        replace(spec, facts=old_facts, as_of=old_facts.as_of)
    with pytest.raises(ValueError, match="availability cannot precede"):
        replace(
            spec,
            available_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )


def test_later_research_date_keeps_older_filing_valuation_date():
    base = _descriptor()
    research_date = date(2026, 9, 21)
    descriptor = finalize_input_descriptor(replace(
        base,
        point_in_time=replace(base.point_in_time, research_as_of=research_date),
        research_case=replace(base.research_case, as_of=research_date),
        input_sha256=None,
    ))
    spec = build_research_run_spec(descriptor)

    assert spec.as_of == research_date
    assert spec.facts.as_of == spec.valuation_date == AS_OF
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(spec)
    assert outcome.as_of == research_date
    assert outcome.valuation.valuation_date == AS_OF
    defaulted = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(
        replace(spec, as_of=None)
    )
    assert defaulted.as_of == research_date

    with pytest.raises(ValueError, match="cannot precede"):
        replace(spec, research_case=replace(spec.research_case, as_of=date(2025, 1, 1),
                                             financial_period=date(2024, 12, 31)),
                as_of=date(2025, 1, 1))


def test_application_adds_binding_mismatch_blocker_without_order():
    descriptor = _descriptor()
    spec = build_research_run_spec(descriptor)
    app = ResearchApplicationService(InMemoryResearchArtifactRepository())
    good = app.run_company_research(spec)
    assert "assumption_binding_value_mismatch" not in good.blockers

    bad = replace(
        spec,
        assumption_bindings=(_binding(Decimal("0.11")),),
    )
    outcome = app.run_company_research(bad)
    assert "assumption_binding_value_mismatch:terminal_roe" in outcome.blockers
    assert "action" not in outcome.current_status.as_policy()
    assert all(
        "order" not in ref.get("id", "") for ref in outcome.valuation.evidence_refs
    )
