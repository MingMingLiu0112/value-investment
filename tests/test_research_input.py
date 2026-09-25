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


def test_versioned_refresh_preserves_prior_valuation_and_validity_artifacts():
    from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE, QuoteSnapshot
    from value_investment_agent.research_application import ModelValidityEvaluationInput
    from value_investment_agent.research_artifacts import (
        ARTIFACT_MODEL_VALIDITY, ARTIFACT_VALUATION_RESULT, SCOPE_SECURITY,
    )

    repository = InMemoryResearchArtifactRepository()
    service = ResearchApplicationService(repository)
    quote = QuoteSnapshot(
        symbol="600519", quote_date=AS_OF, current_price=Decimal("5"),
        status=QUOTE_STATUS_VERIFIED_CLOSE,
        evidence_refs=[{"id": "quote", "sha256": "e" * 64}],
    )
    validity_input = ModelValidityEvaluationInput(
        model_id="residual-income-equity-shared-v1", valid_from=AS_OF,
        event_scan_evidence_refs=({"id": "event-scan", "sha256": "f" * 64},),
    )
    first = finalize_input_descriptor(replace(
        _descriptor(), quote=quote, model_validity_input=validity_input,
        input_sha256=None,
    ))
    first_outcome = service.run_company_research(build_research_run_spec(first))
    first_result = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)
    first_validity = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_MODEL_VALIDITY)

    updated_facts = replace(
        first.facts,
        operating_inputs={**first.facts.operating_inputs,
                          "start_book_equity": Decimal("1200")},
        evidence_refs=[{"id": "f-2", "sha256": "1" * 64}],
    )
    second = finalize_input_descriptor(replace(
        first, run_id="descriptor-refresh", facts=updated_facts,
        input_sha256=None,
        sources=(_source(), ResearchSourceDescriptor(
            id="refreshed-facts", kind="research_artifact", location="facts-v2",
            sha256="1" * 64, retrieved_at=AVAILABLE_AT,
        )),
        point_in_time=replace(first.point_in_time,
                              available_at=datetime(2026, 9, 22, 12, tzinfo=timezone.utc),
                              computed_at=datetime(2026, 9, 22, 13, tzinfo=timezone.utc)),
    ))
    second_outcome = service.run_company_research(build_research_run_spec(second))
    second_result = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)
    second_validity = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_MODEL_VALIDITY)

    assert first_outcome.valuation.base_value != second_outcome.valuation.base_value
    assert first_outcome.model_validity.status == second_outcome.model_validity.status == "VALID"
    assert first_result.artifact_id != second_result.artifact_id
    assert first_result.envelope.payload_sha256 != second_result.envelope.payload_sha256
    assert repository.load_by_id(first_result.artifact_id) == first_result
    assert first_validity.artifact_id != second_validity.artifact_id
    assert len(repository.list_versions(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)) == 2
    assert len(repository.list_versions(SCOPE_SECURITY, "600519", ARTIFACT_MODEL_VALIDITY)) == 2
    assert not hasattr(second_outcome, "order")


def test_actual_valuation_input_node_requires_complete_event_bound_descriptor():
    from types import SimpleNamespace

    from value_investment_agent.m5_event_dependencies import DependencyGraph, DependencyNode
    from value_investment_agent.m5_research_artifact_graph import attach_valuation_input_descriptor

    facts_node = DependencyNode(
        node_id="verified-facts", kind="financial_facts", symbol="600519",
        inputs=(), version="d" * 64, evidence_refs=({"id": "facts"},),
    )
    thesis_node = DependencyNode(
        node_id="research-case", kind="research_thesis", symbol="600519",
        inputs=(), version="a" * 64, evidence_refs=({"id": "case"},),
    )
    graph = DependencyGraph((facts_node, thesis_node))
    receipt = SimpleNamespace(
        namespace="ACTUAL", action="no_order", state_sha256="2" * 64,
        generated_at=datetime(2026, 9, 20, tzinfo=timezone.utc),
        active_events=(SimpleNamespace(
            symbol="600519", evidence_refs=(
                {"id": "filing", "sha256": "3" * 64,
                 "source_url": "https://static.cninfo.com.cn/finalpage/report.PDF"},
            ),
        ),),
    )
    descriptor = _descriptor()
    descriptor = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        sources=(*descriptor.sources,
                 ResearchSourceDescriptor(id="actual-receipt", kind="research_artifact",
                                          location="receipt.json", sha256=receipt.state_sha256),
                 ResearchSourceDescriptor(id="filing", kind="filing",
                                          location="https://static.cninfo.com.cn/finalpage/report.PDF",
                                          sha256="3" * 64)),
    ))
    attached = attach_valuation_input_descriptor(
        graph=graph, descriptor=descriptor, receipt=receipt,
    )
    node = next(item for item in attached.nodes() if item.kind == "valuation_inputs")
    assert node.version == descriptor.input_sha256
    assert node.inputs == (facts_node.node_id, thesis_node.node_id)
    assert attached.node(node.node_id).action == "no_order"

    with pytest.raises(ValueError, match="incomplete"):
        attach_valuation_input_descriptor(
            graph=graph,
            descriptor=finalize_input_descriptor(replace(
                descriptor, input_sha256=None, blockers=("scenario_inputs_not_approved",),
            )),
            receipt=receipt,
        )
    with pytest.raises(ValueError, match="every ACTUAL event PDF"):
        attach_valuation_input_descriptor(
            graph=graph,
            descriptor=finalize_input_descriptor(replace(
                descriptor, input_sha256=None, sources=descriptor.sources[:-1],
            )),
            receipt=receipt,
        )
    wrong_url = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        sources=(*descriptor.sources[:-1], replace(
            descriptor.sources[-1], location="https://static.cninfo.com.cn/other.PDF",
        )),
    ))
    with pytest.raises(ValueError, match="every ACTUAL event PDF"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=wrong_url, receipt=receipt,
        )
    missing_scenarios = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        facts=replace(descriptor.facts, scenario_inputs=None), assumption_bindings=(),
    ))
    with pytest.raises(ValueError, match="model preflight remains not ready"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=missing_scenarios, receipt=receipt,
        )


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
