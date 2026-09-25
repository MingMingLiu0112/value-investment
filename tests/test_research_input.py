from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

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


def _fully_bound_quality_descriptor(descriptor):
    fields = ("cost_of_equity", "terminal_roe", "terminal_growth", "retention",
              "forecast_roes.0")
    assumptions = []
    bindings = []
    for field in fields:
        values = {}
        for scenario_name, scenario in descriptor.facts.scenario_inputs.items():
            value = scenario.forecast_roes[0] if field == "forecast_roes.0" else getattr(scenario, field)
            values[scenario_name] = value
        ref = {"id": "assumption-" + field, "sha256": "c" * 64}
        assumptions.append(ValuationAssumption(
            name=field, unit="ratio", bear=values["bear"], base=values["base"],
            bull=values["bull"], basis="synthetic offline model contract",
            rationale="explicit test scenario", as_of=AS_OF, confidence="low",
            sensitivity="high", evidence_refs=[ref], blockers=[],
        ))
        for scenario_name, value in values.items():
            bindings.append(AssumptionScenarioBinding(
                assumption_name=field, scenario=scenario_name,
                field_path=field, expected_value=value,
                evidence_refs=(ref,),
            ))
    assumption_set = build_valuation_assumption_set(
        symbol=descriptor.symbol, profile_id=descriptor.profile_id,
        model_type=descriptor.assumptions.model_type, as_of=AS_OF,
        assumptions=assumptions,
        evidence_refs=[{"id": "scenario-assumptions", "sha256": "c" * 64}],
    )
    return finalize_input_descriptor(replace(
        descriptor, input_sha256=None, assumptions=assumption_set,
        assumption_bindings=tuple(bindings),
    ))


def _issuer_basis_bytes(*, equity: str) -> bytes:
    return json.dumps({
        "symbol": "600519",
        "current_disclosed_basis": {
            "period_end": AS_OF.isoformat(),
            "source_url": "https://static.cninfo.com.cn/finalpage/report.PDF",
            "raw_file_hash": "3" * 64,
            "assessment_available_at": "2026-09-19T00:00:00+00:00",
            "parent_equity_cny": equity,
            "issued_shares": "100",
        },
    }, sort_keys=True).encode("utf-8")


def _assumption_package_bytes(descriptor) -> bytes:
    return json.dumps(descriptor.assumptions.as_policy(), ensure_ascii=False,
                      sort_keys=True).encode("utf-8")


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
    from value_investment_agent.m5_research_artifact_graph import (
        attach_valuation_input_descriptor as attach_raw,
    )

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
    basis_bytes = _issuer_basis_bytes(equity="1000")
    basis_sha = hashlib.sha256(basis_bytes).hexdigest()

    def attach_valuation_input_descriptor(**kwargs):
        return attach_raw(operating_basis_bytes=basis_bytes,
                          assumption_package_bytes=assumption_bytes, **kwargs)

    descriptor = _fully_bound_quality_descriptor(_descriptor())
    assumption_bytes = _assumption_package_bytes(descriptor)
    assumption_sha = hashlib.sha256(assumption_bytes).hexdigest()
    descriptor = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        facts=replace(descriptor.facts,
                      evidence_refs=[{"id": "verified-facts", "sha256": "d" * 64},
                                     {"id": "issuer-equity-basis", "sha256": basis_sha}]),
        sources=(*descriptor.sources,
                 ResearchSourceDescriptor(id="scenario-assumptions", kind="research_artifact",
                                          location="assumptions.json", sha256="c" * 64),
                 ResearchSourceDescriptor(id="assumption-package", kind="research_artifact",
                                          location="assumption-package.json", sha256=assumption_sha),
                 ResearchSourceDescriptor(id="issuer-equity-basis", kind="research_artifact",
                                          location="issuer-equity.json", sha256=basis_sha),
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

    changed_assumptions = json.loads(assumption_bytes)
    changed_assumptions["assumptions"][0]["confidence"] = "high"
    changed_assumption_bytes = json.dumps(changed_assumptions, ensure_ascii=False,
                                          sort_keys=True).encode("utf-8")
    changed_assumption_sha = hashlib.sha256(changed_assumption_bytes).hexdigest()
    repinned_descriptor = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        sources=tuple(replace(source, sha256=changed_assumption_sha)
                      if source.id == "assumption-package" else source
                      for source in descriptor.sources),
    ))
    with pytest.raises(ValueError, match="assumption package bytes"):
        attach_raw(graph=graph, descriptor=repinned_descriptor, receipt=receipt,
                   operating_basis_bytes=basis_bytes,
                   assumption_package_bytes=changed_assumption_bytes)

    changed_package = json.loads(basis_bytes)
    changed_package["current_disclosed_basis"]["parent_equity_cny"] = "999"
    changed_bytes = json.dumps(changed_package, sort_keys=True).encode("utf-8")
    changed_sha = hashlib.sha256(changed_bytes).hexdigest()
    changed_descriptor = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        facts=replace(descriptor.facts, evidence_refs=[
            {**ref, "sha256": changed_sha} if ref["id"] == "issuer-equity-basis" else ref
            for ref in descriptor.facts.evidence_refs
        ]),
        sources=tuple(replace(source, sha256=changed_sha)
                      if source.id == "issuer-equity-basis" else source
                      for source in descriptor.sources),
    ))
    with pytest.raises(ValueError, match="operating inputs do not match"):
        attach_raw(graph=graph, descriptor=changed_descriptor, receipt=receipt,
                   operating_basis_bytes=changed_bytes,
                   assumption_package_bytes=assumption_bytes)

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
    wrong_facts = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        facts=replace(descriptor.facts,
                      evidence_refs=[{"id": "other-facts", "sha256": "4" * 64}]),
    ))
    with pytest.raises(ValueError, match="Model facts do not reference"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=wrong_facts, receipt=receipt,
        )
    wrong_case = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        research_case=replace(descriptor.research_case,
                              evidence_refs=[{"id": "e-1", "sha256": "5" * 64}]),
    ))
    with pytest.raises(ValueError, match="Research case does not reference"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=wrong_case, receipt=receipt,
        )
    missing_binding = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        assumption_bindings=descriptor.assumption_bindings[:-1],
    ))
    with pytest.raises(ValueError, match="every consumed model input"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=missing_binding, receipt=receipt,
        )
    altered = [replace(item, base=Decimal("0.11")) if item.name == "terminal_roe"
               else item for item in descriptor.assumptions.assumptions]
    wrong_assumptions = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        assumptions=build_valuation_assumption_set(
            symbol=descriptor.symbol, profile_id=descriptor.profile_id,
            model_type=descriptor.assumptions.model_type, as_of=AS_OF,
            assumptions=altered,
            evidence_refs=list(descriptor.assumptions.evidence_refs),
        ),
    ))
    with pytest.raises(ValueError, match="Scenario input does not match"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=wrong_assumptions, receipt=receipt,
        )
    unpinned_assumptions = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        sources=tuple(source for source in descriptor.sources
                      if source.id != "scenario-assumptions"),
    ))
    with pytest.raises(ValueError, match="not pinned to input sources"):
        attach_valuation_input_descriptor(
            graph=graph, descriptor=unpinned_assumptions, receipt=receipt,
        )


def test_complete_actual_bounded_refresh_persists_new_research_version(tmp_path):
    import hashlib
    import json
    from types import SimpleNamespace

    from value_investment_agent.m5_bounded_refresh import (
        execute_bounded_research_refresh, validate_bounded_research_refresh,
    )
    from value_investment_agent.m5_actual_read_model import build_actual_event_read_model
    from value_investment_agent.m5_event_dependencies import DependencyGraph, DependencyNode
    from value_investment_agent.event_materiality import EventMaterialityDecision
    from value_investment_agent.m5_recalculation_plan import build_bounded_recalculation_plan
    from value_investment_agent.m5_materiality_bridge import materiality_direct_kinds
    from value_investment_agent.m5_research_artifact_graph import attach_valuation_input_descriptor
    from value_investment_agent.m5_pending_research_input import attach_completed_event_research_input
    from value_investment_agent.research_artifacts import (
        ARTIFACT_TYPES, ARTIFACT_VALUATION_RESULT, SCOPE_SECURITY,
        ResearchArtifactEnvelope, ResearchArtifactIdentity,
        canonicalize_artifact_payload, sha256_text,
    )
    from value_investment_agent.quote_snapshot import QUOTE_STATUS_VERIFIED_CLOSE, QuoteSnapshot
    from value_investment_agent.research_application import ModelValidityEvaluationInput

    repository = InMemoryResearchArtifactRepository()
    application = ResearchApplicationService(repository)
    application.run_company_research(build_research_run_spec(_descriptor()))
    prior = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)
    prior_path = tmp_path / "prior-valuation.json"
    prior_path.write_text(canonicalize_artifact_payload(prior.envelope.payload_object()),
                          encoding="utf-8")
    prior_sha = hashlib.sha256(prior_path.read_bytes()).hexdigest()
    prior_candidate = SimpleNamespace(
        symbol="600519", artifact_type=ARTIFACT_VALUATION_RESULT,
        source_path=prior_path, source_sha256=prior_sha,
        payload=prior.envelope.payload_object(),
    )
    pdf_ref = {"id": "filing", "sha256": "3" * 64,
               "source_url": "https://static.cninfo.com.cn/finalpage/report.PDF"}
    at = datetime(2026, 9, 22, tzinfo=timezone.utc)
    decision = EventMaterialityDecision(
        event_decision_id="review-1234567890", symbol="600519", announcement_id="1234567890",
        title="Interim filing", published_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        source_ref=pdf_ref, source_sha256=pdf_ref["sha256"],
        machine_candidate_reason="financial_statement",
        human_decision="MATERIAL_REQUIRES_RECALCULATION",
        affected_domains=(), affected_fact_fields=(), affected_assumptions=(),
        affected_artifacts=(), requires_recalculation=True, requires_model_stale=True,
        requires_followup=False, reviewed_at=at,
    )
    event = SimpleNamespace(
        event_id="event-1", source_event_id="materiality-review:review-1234567890", symbol="600519",
        current_state={
            "direct_dependency_kinds": list(materiality_direct_kinds(decision)),
            "source_sha256": decision.source_sha256,
            "materiality_status": decision.human_decision,
            "event_cluster_id": decision.event_cluster_id,
            "supersedes_event_id": decision.supersedes_event_id,
            "affected_domains": list(decision.affected_domains),
            "affected_fact_fields": list(decision.affected_fact_fields),
            "affected_assumptions": list(decision.affected_assumptions),
            "affected_artifacts": list(decision.affected_artifacts),
        },
        evidence_refs=(pdf_ref,),
    )
    receipt = SimpleNamespace(
        namespace="ACTUAL", action="no_order", receipt_id="receipt-1",
        state_sha256="2" * 64, generated_at=at,
        active_events=(event,), invalidations=(SimpleNamespace(event_id="event-1"),),
    )
    graph = DependencyGraph((
        DependencyNode(node_id="verified-facts", kind="financial_facts",
                       symbol="600519", inputs=(), version="d" * 64,
                       evidence_refs=(pdf_ref,)),
        DependencyNode(node_id="research-case", kind="research_thesis",
                       symbol="600519", inputs=(), version="a" * 64,
                       evidence_refs=({"id": "case"},)),
        DependencyNode(node_id="prior-valuation", kind="valuation_result",
                       symbol="600519", inputs=("research-case",),
                       version=prior_sha, evidence_refs=({"id": "prior"},)),
        DependencyNode(node_id="prior-validity", kind="model_validity",
                       symbol="600519", inputs=("prior-valuation",),
                       version="6" * 64, evidence_refs=({"id": "validity"},)),
        DependencyNode(node_id="prior-review", kind="decision_review",
                       symbol="600519", inputs=("research-case",),
                       version="7" * 64, evidence_refs=({"id": "review"},)),
    ))
    basis_bytes = _issuer_basis_bytes(equity="1200")
    basis_sha = hashlib.sha256(basis_bytes).hexdigest()
    old = _fully_bound_quality_descriptor(_descriptor())
    assumption_bytes = _assumption_package_bytes(old)
    assumption_sha = hashlib.sha256(assumption_bytes).hexdigest()
    descriptor = finalize_input_descriptor(replace(
        old, input_sha256=None, run_id="bounded-refresh-1",
        facts=replace(old.facts,
                      operating_inputs={**old.facts.operating_inputs,
                                        "start_book_equity": Decimal("1200")},
                      evidence_refs=[{"id": "verified-facts", "sha256": "d" * 64},
                                     {"id": "issuer-equity-basis", "sha256": basis_sha},
                                     {"id": "actual-receipt", "sha256": receipt.state_sha256}]),
        research_case=replace(old.research_case,
                              evidence_refs=[*old.research_case.evidence_refs, pdf_ref]),
        sources=(*old.sources,
                 ResearchSourceDescriptor(id="scenario-assumptions", kind="research_artifact",
                                          location="assumptions.json", sha256="c" * 64),
                 ResearchSourceDescriptor(id="assumption-package", kind="research_artifact",
                                          location="assumption-package.json", sha256=assumption_sha),
                 ResearchSourceDescriptor(id="issuer-equity-basis", kind="research_artifact",
                                          location="issuer-equity.json", sha256=basis_sha),
                 ResearchSourceDescriptor(id="actual-receipt", kind="research_artifact",
                                          location="receipt.json", sha256=receipt.state_sha256),
                 ResearchSourceDescriptor(id="filing", kind="filing",
                                          location=pdf_ref["source_url"], sha256=pdf_ref["sha256"])),
        quote=QuoteSnapshot(symbol="600519", quote_date=AS_OF,
                            current_price=Decimal("5"), status=QUOTE_STATUS_VERIFIED_CLOSE,
                            evidence_refs=[{"id": "quote", "sha256": "e" * 64}]),
        model_validity_input=ModelValidityEvaluationInput(
            model_id="residual-income-equity-shared-v1", valid_from=AS_OF,
            event_scan_evidence_refs=({"id": "event-scan", "sha256": receipt.state_sha256},),
        ),
        point_in_time=replace(old.point_in_time,
                              available_at=datetime(2026, 9, 23, 12, tzinfo=timezone.utc),
                              computed_at=datetime(2026, 9, 23, 13, tzinfo=timezone.utc)),
    ))
    pending_sources = tuple(source for source in descriptor.sources
                            if source.id not in {"scenario-assumptions", "assumption-package"})
    pending = finalize_input_descriptor(replace(
        descriptor, input_sha256=None, run_id="bounded-refresh-pending",
        sources=pending_sources, assumptions=None, assumption_bindings=(),
        facts=replace(descriptor.facts, verified=False, scenario_inputs=None,
                      blockers=["scenario_inputs_not_approved"]),
        quote=None, model_validity_input=None,
        blockers=("scenario_inputs_not_approved",),
    ))
    promotion = dict(
        pending=pending, completed=descriptor, receipt=receipt, graph=graph,
        operating_basis_bytes=basis_bytes,
        assumption_package_bytes=assumption_bytes,
    )
    missing_event_pending = finalize_input_descriptor(replace(
        pending, input_sha256=None,
        sources=tuple(source for source in pending.sources if source.id != "filing"),
    ))
    with pytest.raises(ValueError, match="missing an ACTUAL event PDF"):
        attach_completed_event_research_input(
            **{**promotion, "pending": missing_event_pending},
        )
    dropped_source = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        sources=tuple(source for source in descriptor.sources if source.id != "facts-source"),
    ))
    with pytest.raises(ValueError, match="drops or changes a pending source"):
        attach_completed_event_research_input(**{**promotion, "completed": dropped_source})
    dropped_event_ref = finalize_input_descriptor(replace(
        descriptor, input_sha256=None,
        research_case=replace(descriptor.research_case,
                              evidence_refs=old.research_case.evidence_refs),
    ))
    with pytest.raises(ValueError, match="does not retain pending evidence"):
        attach_completed_event_research_input(**{**promotion, "completed": dropped_event_ref})
    graph = attach_completed_event_research_input(**promotion)
    plan = build_bounded_recalculation_plan(receipt=receipt, graph=graph, generated_at=at)
    fact_payload = {"schema_version": "m5-verified-financial-facts-v1",
                    "symbol": "600519", "pdf_sha256": pdf_ref["sha256"],
                    "announcement_id": "1234567890",
                    "source_url": pdf_ref["source_url"],
                    "facts": [{"field": "operating_revenue", "value": "1"}],
                    "action": "no_order"}
    facts_artifact = {
        "identity": {"artifact_type": "financial_facts", "scope_key": "600519"},
        "payload": fact_payload,
        "payload_sha256": sha256_text(canonicalize_artifact_payload(fact_payload)),
        "evidence_refs": [pdf_ref],
    }
    result = execute_bounded_research_refresh(
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        facts_source_sha256="d" * 64, descriptor=descriptor,
        prior_candidate=prior_candidate, operating_basis_bytes=basis_bytes,
        assumption_package_bytes=assumption_bytes,
        application=application,
        evaluated_at=datetime(2026, 9, 23, 14, tzinfo=timezone.utc),
    )
    refreshed = repository.load_latest(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)
    assert refreshed.artifact_id != prior.artifact_id
    assert repository.load_by_id(prior.artifact_id) == prior
    assert len(repository.list_versions(SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT)) == 2
    assert result["outcomes"][0]["status"] == "MODEL_STALE"
    assert result["outcomes"][0]["new_valuation_result"]["artifact_id"] == refreshed.artifact_id
    assert result["outcomes"][0]["new_valuation_result"]["event_validity_status"] == "UNRECONCILED"
    assert result["outcomes"][0]["requires_human_review"] is True
    assert result["action"] == "no_order"
    validation = dict(
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        facts_source_sha256="d" * 64, descriptor=descriptor,
        prior_candidate=prior_candidate, operating_basis_bytes=basis_bytes,
        assumption_package_bytes=assumption_bytes,
        repository=repository,
    )
    validate_bounded_research_refresh(result, **validation)
    forged = {**result, "outcomes": [{**result["outcomes"][0], "status": "RECALCULATED"}]}
    from value_investment_agent.m5_recalculation_plan import _sha
    forged["result_sha256"] = _sha({key: value for key, value in forged.items()
                                      if key != "result_sha256"})
    with pytest.raises(ValueError, match="persisted artifacts"):
        validate_bounded_research_refresh(forged, **validation)
    forged_payload = refreshed.envelope.payload_object()
    forged_payload["base_value"] = str(Decimal(forged_payload["base_value"]) + 1)
    forged_canonical = canonicalize_artifact_payload(forged_payload)
    forged_repository = InMemoryResearchArtifactRepository()
    existing = sorted((artifact for artifact_type in ARTIFACT_TYPES
                       for artifact in repository.list_versions(
                           SCOPE_SECURITY, "600519", artifact_type)),
                      key=lambda artifact: artifact.artifact_id)
    for artifact in existing:
        envelope = artifact.envelope
        if artifact.artifact_id == refreshed.artifact_id:
            envelope = replace(envelope, canonical_payload=forged_canonical,
                               payload_sha256=sha256_text(forged_canonical))
        saved_artifact = forged_repository.save(envelope)
        if artifact.artifact_id == refreshed.artifact_id:
            forged_artifact = saved_artifact
    forged_reference = {
        **result["outcomes"][0]["new_valuation_result"],
        "artifact_id": forged_artifact.artifact_id,
        "payload_sha256": forged_artifact.envelope.payload_sha256,
        "model_validity_artifact_id": None,
        "model_validity_status": "UNKNOWN",
    }
    forged_result = {
        **result,
        "outcomes": [{**result["outcomes"][0],
                      "new_valuation_result": forged_reference}],
    }
    forged_result["result_sha256"] = _sha({
        key: value for key, value in forged_result.items() if key != "result_sha256"
    })
    with pytest.raises(ValueError, match="distinct complete result"):
        validate_bounded_research_refresh(
            forged_result, **{**validation, "repository": forged_repository},
        )
    queue = {"queue_id": "synthetic-offline", "scans": [{
        "symbol": "600519", "announcements": [{
            "announcement_id": decision.announcement_id,
            "published_at": decision.published_at.isoformat(),
            "title": decision.title, "source_url": pdf_ref["source_url"],
            "review_status": "PENDING_HUMAN_REVIEW", "evidence_refs": [pdf_ref],
        }],
    }]}
    read_model = build_actual_event_read_model(
        queue=queue, reviews=[{"decisions": [decision.as_policy()]}],
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        outcome_receipt=result, facts_source_sha256="d" * 64,
        refresh_descriptor=descriptor, refresh_prior_candidate=prior_candidate,
        refresh_repository=repository, refresh_operating_basis_bytes=basis_bytes,
        refresh_assumption_package_bytes=assumption_bytes,
    )
    row = read_model["rows"][0]
    assert row["recalculation_status"] == "MODEL_STALE"
    assert row["new_valuation_result"]["artifact_id"] == refreshed.artifact_id
    assert row["requires_human_decision_review"] is True
    assert row["action"] == "no_order"
    value_ref = result["outcomes"][0]["new_valuation_result"]
    review = {
        "schema_version": "m5-event-refresh-review-v1",
        "receipt_id": receipt.receipt_id,
        "receipt_sha256": receipt.state_sha256,
        "plan_id": plan.plan_id,
        "plan_sha256": _sha(plan.as_policy()),
        "graph_sha256": _sha(graph.as_policy()),
        "refresh_result_sha256": result["result_sha256"],
        "facts_payload_sha256": facts_artifact["payload_sha256"],
        "assumption_package_sha256": hashlib.sha256(assumption_bytes).hexdigest(),
        "reviewer_id": "synthetic-human-reviewer",
        "reviewer_type": "human_research_lead",
        "reviewed_at": "2026-09-23T15:00:00+00:00",
        "event_reviews": [{
            "event_id": event.event_id,
            "source_event_id": event.source_event_id,
            "materiality_decision_id": decision.event_decision_id,
            "pdf_sha256": pdf_ref["sha256"],
            "affected_domains": list(decision.affected_domains),
            "affected_fact_fields": list(decision.affected_fact_fields),
            "affected_assumptions": list(decision.affected_assumptions),
            "affected_artifacts": list(decision.affected_artifacts),
            "valuation_artifact_id": value_ref["artifact_id"],
            "verdict": "EVENT_REFRESH_ACCEPTED",
            "review_notes": "Synthetic test-only review of all affected model inputs.",
            "evidence_sha256": sorted({
                pdf_ref["sha256"], receipt.state_sha256,
                facts_artifact["payload_sha256"],
                hashlib.sha256(assumption_bytes).hexdigest(),
                value_ref["payload_sha256"],
            }),
        }],
        "requires_human_decision_review": True,
        "action": "no_order",
    }
    review["review_sha256"] = _sha(review)
    review_projection = dict(
        queue=queue, reviews=[{"decisions": [decision.as_policy()]}],
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        outcome_receipt=result, facts_source_sha256="d" * 64,
        refresh_descriptor=descriptor, refresh_prior_candidate=prior_candidate,
        refresh_repository=repository, refresh_operating_basis_bytes=basis_bytes,
        refresh_assumption_package_bytes=assumption_bytes,
    )
    reconciled = build_actual_event_read_model(**review_projection, refresh_review=review)
    assert reconciled["rows"][0]["recalculation_status"] == "RECALCULATED"
    assert reconciled["rows"][0]["new_valuation_result"]["event_validity_status"] == "RECONCILED"
    assert reconciled["rows"][0]["requires_human_decision_review"] is True
    assert reconciled["action"] == "no_order"
    assert value_ref["model_validity_status"] == "VALID"
    rejected_review = json.loads(json.dumps(review))
    rejected_review["event_reviews"][0]["verdict"] = "EVENT_REFRESH_REJECTED"
    rejected_review["review_sha256"] = _sha({key: value for key, value in rejected_review.items()
                                               if key != "review_sha256"})
    rejected = build_actual_event_read_model(**review_projection, refresh_review=rejected_review)
    assert rejected["rows"][0]["recalculation_status"] == "MODEL_STALE"
    missing_row = json.loads(json.dumps(review))
    missing_row["event_reviews"] = []
    missing_row["review_sha256"] = _sha({key: value for key, value in missing_row.items()
                                          if key != "review_sha256"})
    with pytest.raises(ValueError, match="every active event"):
        build_actual_event_read_model(**review_projection, refresh_review=missing_row)
    wrong_reviewer = json.loads(json.dumps(review))
    wrong_reviewer["reviewer_type"] = "automated_agent"
    wrong_reviewer["review_sha256"] = _sha({key: value for key, value in wrong_reviewer.items()
                                             if key != "review_sha256"})
    with pytest.raises(ValueError, match="validated evidence"):
        build_actual_event_read_model(**review_projection, refresh_review=wrong_reviewer)
    for field, value in (("pdf_sha256", "0" * 64), ("valuation_artifact_id", "other")):
        forged_review = json.loads(json.dumps(review))
        forged_review["event_reviews"][0][field] = value
        forged_review["review_sha256"] = _sha({key: value for key, value in forged_review.items()
                                                if key != "review_sha256"})
        with pytest.raises(ValueError, match="does not reconcile"):
            build_actual_event_read_model(**review_projection, refresh_review=forged_review)
    forged_review = json.loads(json.dumps(review))
    forged_review["assumption_package_sha256"] = "0" * 64
    forged_review["review_sha256"] = _sha({key: value for key, value in forged_review.items()
                                            if key != "review_sha256"})
    with pytest.raises(ValueError, match="validated evidence"):
        build_actual_event_read_model(**review_projection, refresh_review=forged_review)
    saved = {}
    for artifact_type in ARTIFACT_TYPES:
        for artifact in repository.list_versions(SCOPE_SECURITY, "600519", artifact_type):
            saved[artifact.artifact_id] = artifact
    bundle = [{
        "artifact_id": artifact.artifact_id,
        "identity": artifact.envelope.identity.as_dict(),
        "canonical_payload": artifact.envelope.canonical_payload,
        "payload_sha256": artifact.envelope.payload_sha256,
        "evidence_refs": list(artifact.envelope.evidence_refs),
        "run_id": artifact.envelope.run_id,
    } for artifact in sorted(saved.values(), key=lambda item: item.artifact_id)]
    bundle_path = tmp_path / "research-artifact-bundle.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    restored = InMemoryResearchArtifactRepository()
    for entry in json.loads(bundle_path.read_text(encoding="utf-8")):
        identity = entry["identity"]
        envelope = ResearchArtifactEnvelope(
            identity=ResearchArtifactIdentity(
                scope_type=identity["scope_type"], scope_key=identity["scope_key"],
                artifact_type=identity["artifact_type"],
                schema_version=identity["schema_version"],
                as_of=date.fromisoformat(identity["as_of"]) if identity["as_of"] else None,
                available_at=datetime.fromisoformat(identity["available_at"]),
            ),
            canonical_payload=entry["canonical_payload"],
            payload_sha256=entry["payload_sha256"],
            evidence_refs=tuple(entry["evidence_refs"]), run_id=entry["run_id"],
        )
        assert restored.save(envelope).artifact_id == entry["artifact_id"]
    validate_bounded_research_refresh(result, **{**validation, "repository": restored})
    replayed = build_actual_event_read_model(
        queue=queue, reviews=[{"decisions": [decision.as_policy()]}],
        receipt=receipt, graph=graph, plan=plan, facts_artifact=facts_artifact,
        outcome_receipt=result, facts_source_sha256="d" * 64,
        refresh_descriptor=descriptor, refresh_prior_candidate=prior_candidate,
        refresh_repository=restored, refresh_operating_basis_bytes=basis_bytes,
        refresh_assumption_package_bytes=assumption_bytes,
    )
    assert replayed == read_model
    prior_path.write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="source bytes"):
        validate_bounded_research_refresh(result, **validation)
    prior_path.write_text(canonicalize_artifact_payload(prior.envelope.payload_object()),
                          encoding="utf-8")
    successor = finalize_input_descriptor(replace(
        descriptor, input_sha256=None, run_id="bounded-refresh-successor",
        point_in_time=replace(
            descriptor.point_in_time,
            available_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc),
            computed_at=datetime(2026, 9, 24, 13, tzinfo=timezone.utc),
        ),
    ))
    application.run_company_research(build_research_run_spec(successor))
    with pytest.raises(ValueError, match="no longer the current"):
        validate_bounded_research_refresh(result, **validation)


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
