from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal as D

import pytest

from value_investment_agent.fixed_sample_admission import (
    DECISION_CONTINUE_CONDITIONAL_MODEL,
    FixedSampleAdmissionPolicy,
)
from value_investment_agent.model_validity import MaterialEvent
from value_investment_agent.price_attractiveness import STATUS_NOT_ASSESSABLE
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
    ARTIFACT_DECISION_RECOMMENDATION,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_QUOTE_SNAPSHOT,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_RESULT,
    SCOPE_SECURITY,
)
from value_investment_agent.research_case import ResearchCase
from value_investment_agent.research_gate import GATE_VALUATION
from value_investment_agent.research_run_contract import (
    ResearchIssuerIdentity,
    ResearchSourceDescriptor,
    ResearchValuationApproval,
    valuation_result_sha256,
)
from value_investment_agent.valuation_models.cyclical import CyclicalFacts
from value_investment_agent.valuation_models.fcff import FinancialFacts
from value_investment_agent.valuation_models.residual_income import (
    MODEL_VERSION,
    QualityCompounderFacts,
    ResidualIncomeScenarioInputs,
)
from value_investment_agent.application.decision.artifact_bundle import (
    ReadOnlyArtifactBundleRepository,
)
from value_investment_agent.application.decision.restore_decision_recommendation import (
    verify_decision_recommendation_payload,
)
from value_investment_agent.application.product.company_research import _serialize_outcome
from value_investment_agent.application.product import workbench as product_workbench
from value_investment_agent.application.product.decision_surface import (
    project_verified_decision_workbench,
)
from value_investment_agent.domain.decision.decision_recommendation import (
    DECISION_RECOMMENDATION_SCHEMA,
    DECISION_RECOMMENDATION_V3_SCHEMA,
)


AS_OF = date(2025, 12, 31)
AVAILABLE_AT = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)


def test_serialized_research_keeps_replayable_decision_artifacts():
    spec, app = quality_spec(run_id="bundle-replay")
    outcome = app.run_company_research(spec)
    payload = _serialize_outcome(outcome)
    repository = ReadOnlyArtifactBundleRepository(payload["artifact_bundle"])
    restored = verify_decision_recommendation_payload(
        repository, payload=payload["decision_recommendation"]
    )
    assert restored.recommendation.as_policy() == payload["decision_recommendation"]
    assert restored.recommendation.action == "no_order"

    import copy

    forged = copy.deepcopy(payload["artifact_bundle"])
    forged["artifacts"][0]["canonical_payload"] += " "
    with pytest.raises(ValueError, match="payload hash does not match"):
        ReadOnlyArtifactBundleRepository(forged)

    missing_decision = {
        **payload["artifact_bundle"],
        "artifacts": [
            row for row in payload["artifact_bundle"]["artifacts"]
            if row["identity"]["artifact_type"] != ARTIFACT_DECISION_RECOMMENDATION
        ],
    }
    with pytest.raises(ValueError, match="matching bundled artifact"):
        ReadOnlyArtifactBundleRepository(missing_decision).recommendation_artifact(
            payload["decision_recommendation"]
        )


def test_recommendation_v3_is_explicit_opt_in_on_the_production_path():
    default_spec, default_app = quality_spec(run_id="default-v2-production")
    default_outcome = default_app.run_company_research(default_spec)
    assert (
        default_outcome.decision_recommendation.schema_version
        == DECISION_RECOMMENDATION_SCHEMA
    )

    v3_spec = replace(
        default_spec,
        run_id="explicit-v3-production",
        recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
    )
    v3_outcome = ResearchApplicationService(
        InMemoryResearchArtifactRepository()
    ).run_company_research(v3_spec)
    assert (
        v3_outcome.decision_recommendation.schema_version
        == DECISION_RECOMMENDATION_V3_SCHEMA
    )
    assert v3_outcome.decision_recommendation.action == "no_order"
    assert v3_outcome.decision_recommendation.position_guidance is None
    assert (
        v3_outcome.decision_recommendation.portfolio_input_status
        == "BLOCKED_PRIVATE_INPUT"
    )


def test_workbench_projects_verified_security_state_without_private_position(
    tmp_path, monkeypatch,
):
    spec, app = quality_spec(run_id="workbench-replay")
    outcome = _serialize_outcome(app.run_company_research(spec))
    seen = {}

    def fake_run_company_research(**kwargs):
        seen.update(kwargs)
        return {"result": outcome, "receipt": {"input_sha256": {}}}

    monkeypatch.setattr(
        product_workbench,
        "run_company_research_for_symbol",
        fake_run_company_research,
    )
    result = product_workbench.build_current_workbench_for_symbol(
        root=tmp_path,
        symbol="600519",
        output_path=tmp_path / "workbench.json",
        recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
    )["result"]
    assert seen["recommendation_schema_version"] == DECISION_RECOMMENDATION_V3_SCHEMA
    assert result["decision_recommendation"] == outcome["decision_recommendation"]
    assert result["suggested_state"] == outcome["decision_recommendation"]["recommendation_type"]
    assert result["portfolio_input_status"] == "BLOCKED_PRIVATE_INPUT"
    assert result["position_guidance"] is None
    assert result["action"] == "no_order"


def test_existing_workbench_rejects_recommendation_schema_override(tmp_path):
    with pytest.raises(ValueError, match="existing workbench excludes"):
        product_workbench.build_current_workbench_for_symbol(
            root=tmp_path,
            symbol="600519",
            output_path=tmp_path / "workbench.json",
            existing_manifest_path=tmp_path / "manifest.json",
            existing_manifest_sha256="a" * 64,
            recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
        )


@pytest.mark.parametrize(
    "schema_version",
    [DECISION_RECOMMENDATION_SCHEMA, DECISION_RECOMMENDATION_V3_SCHEMA],
    ids=["v2", "v3"],
)
def test_verified_decision_reaches_product_read_model_and_excel(
    tmp_path, schema_version,
):
    from test_product_workbench_excel import _payload
    from value_investment_agent.presentation.read_models.product_workbench import (
        product_workbench_from_payload,
    )
    from value_investment_agent.presentation.excel.product_workbench import (
        build_product_workbench_workbook,
    )

    spec, app = quality_spec(run_id="synthetic-product-replay")
    spec = replace(spec, recommendation_schema_version=schema_version)
    spec = replace(
        spec,
        research_case=replace(
            spec.research_case,
            as_of=date(2026, 9, 21), generated_at=AVAILABLE_AT,
        ),
    )
    outcome = _serialize_outcome(app.run_company_research(spec))
    workbench_payload = {
        "schema_version": "product-current-workbench-request-v1",
        "generated_at": "2026-09-21T12:00:00+00:00",
        "symbol": "600519",
        "action": "no_order",
        "research_status": "COMPLETED_WITH_BLOCKERS",
        "position_guidance": None,
        "portfolio_input_status": "BLOCKED_PRIVATE_INPUT",
        "decision_recommendation": outcome["decision_recommendation"],
        "artifact_bundle": outcome["artifact_bundle"],
    }
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "decision-workbench.json"
    source.write_text(json.dumps(workbench_payload, ensure_ascii=False), encoding="utf-8")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    payload = _payload()
    payload["as_of"] = outcome["decision_recommendation"]["decision_as_of"]
    payload["opportunities"][0]["symbol"] = "600519"
    payload["companies"][0]["symbol"] = "600519"
    from value_investment_agent.presentation.read_models.product_workbench import DECISION_STEP_TITLES
    payload["companies"][0]["decision_process"] = [
        {"key": key, "status": "PASS", "reason": "旧的通过状态。", "next_action": "继续。",
         "assessment_id": f"old-{key}", "evidence_refs": ["evidence-1"]}
        for key in DECISION_STEP_TITLES
    ]
    project_verified_decision_workbench(
        payload, root=tmp_path, path=source, expected_sha256=digest,
    )
    assert payload["companies"][0]["price"]["available"] is False
    assert payload["opportunities"][0]["price_status"] == "UNAVAILABLE"
    assert payload["opportunities"][0]["valuation_status"] == "UNDER_REVIEW"
    assert next(
        step for step in payload["companies"][0]["decision_process"]
        if step["key"] == "valuation"
    )["status"] == "CONDITIONAL"
    assert next(
        step for step in payload["companies"][0]["decision_process"]
        if step["key"] == "price_bridge"
    )["status"] == "BLOCKED"
    model = product_workbench_from_payload(payload)
    workbook = build_product_workbench_workbook(model)
    try:
        opportunity_text = "\n".join(
            str(cell.value) for row in workbook["02_机会"] for cell in row
            if cell.value is not None
        )
        company_text = "\n".join(
            str(cell.value) for row in workbook["03_公司"] for cell in row
            if cell.value is not None
        )
        assert "暂不可评估" in opportunity_text
        assert "暂不进入人工买入复核" in company_text
        assert "尚未接入真实组合" in company_text
        assert "人工买入复核条件" in company_text
        assert "人工加仓复核条件" in company_text
        assert "停止加仓条件" in company_text
        assert "减仓/退出复核触发" in company_text
        assert "仅有条件性研究情景" in company_text
        assert model.portfolio.real_data_available is False
        assert model.action == "no_order"
    finally:
        workbook.close()

    with pytest.raises(ValueError, match="hash mismatch"):
        project_verified_decision_workbench(
            _payload(), root=tmp_path, path=source, expected_sha256="a" * 64,
        )

    future = dict(workbench_payload, generated_at="2026-09-21T11:59:59+00:00")
    source.write_text(json.dumps(future, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError, match="future-available artifacts"):
        project_verified_decision_workbench(
            payload, root=tmp_path, path=source,
            expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        )


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


def _identity_source(symbol: str = "600519") -> ResearchSourceDescriptor:
    registered = {
        "600519": ("gssh0600519", "贵州茅台"),
        "000333": ("9900005965", "美的集团"),
        "601088": ("9900003701", "中国神华"),
        "600887": ("gssh0600887", "伊利股份"),
    }
    organization_id, issuer_name = registered[symbol]
    return ResearchSourceDescriptor(
        id="facts",
        kind="annual_report",
        location="https://www.cninfo.com.cn/annual-report.pdf",
        sha256="b" * 64,
        issuer_identity=ResearchIssuerIdentity(
            venue="CNINFO",
            security_code=symbol,
            issuer_name=issuer_name,
            organization_id=organization_id,
        ),
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
        input_sources=(_identity_source(),),
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
            input_sources=(_identity_source(symbol),),
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
        assert outcome.decision_recommendation is not None
        assert outcome.decision_recommendation.symbol == symbol
        assert outcome.decision_recommendation.recommendation_action == "NO_ACTION"
        assert outcome.decision_recommendation.action == "no_order"
        assert outcome.decision_recommendation.position_guidance is None
        assert outcome.decision_recommendation.portfolio_input_status == "BLOCKED_PRIVATE_INPUT"

        for artifact_type in (
            ARTIFACT_RESEARCH_CASE,
            ARTIFACT_VALUATION_RESULT,
            ARTIFACT_PRICE_BRIDGE,
            ARTIFACT_CURRENT_RESEARCH_STATUS,
            ARTIFACT_DECISION_RECOMMENDATION,
        ):
            artifact = app.repository.load_latest(
                SCOPE_SECURITY, symbol, artifact_type
            )
            assert artifact.envelope.run_id == spec.run_id


def test_manufacturing_profile_explicit_equity_route_uses_shared_facts_contract():
    spec = ResearchRunSpec(
        run_id="run-explicit-equity-route",
        symbol="000333",
        profile_id="mature_manufacturing",
        research_case=case("000333", industry="制造业"),
        facts=residual_facts("000333"),
        requested_model="residual_income_or_equity_value",
        available_at=AVAILABLE_AT,
        input_sources=(_identity_source("000333"),),
    )

    outcome = service().run_company_research(spec)

    assert outcome.status == RUN_COMPLETED_WITH_BLOCKERS
    assert outcome.route is not None
    assert outcome.route.as_policy()["requested_model"] == "residual_income_or_equity_value"
    assert outcome.valuation is not None
    assert outcome.valuation.model_type == "residual_income_or_equity_value"
    assert outcome.valuation.status == "conditional_research_only"


def test_manufacturing_equity_route_rejects_fcff_facts_without_fallback():
    spec = ResearchRunSpec(
        run_id="run-equity-route-wrong-facts",
        symbol="000333",
        profile_id="mature_manufacturing",
        research_case=case("000333", industry="制造业"),
        facts=FinancialFacts(
            symbol="000333",
            as_of=AS_OF,
            verified=True,
            evidence_refs=[{"id": "facts", "sha256": "b" * 64}],
            blockers=[],
        ),
        requested_model="residual_income_or_equity_value",
        available_at=AVAILABLE_AT,
        input_sources=(_identity_source("000333"),),
    )

    with pytest.raises(TypeError, match="residual_income_or_equity_value facts require QualityCompounderFacts"):
        service().run_company_research(spec)


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
        input_sources=spec.input_sources,
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
    assert outcome.price_attractiveness is not None
    assert outcome.price_attractiveness.status == STATUS_NOT_ASSESSABLE
    assert "research_gate_not_ready_for_price_assessment" in (
        outcome.price_attractiveness.blockers
    )
    assert app.repository.load_latest(
        SCOPE_SECURITY, "600519", ARTIFACT_MODEL_VALIDITY
    )
    assert app.repository.load_latest(
        SCOPE_SECURITY, "600519", ARTIFACT_QUOTE_SNAPSHOT
    )


def test_application_does_not_auto_promote_g3_without_approval():
    repository = InMemoryResearchArtifactRepository()
    spec, app = quality_spec(
        run_id="g3-approval",
        repository=repository,
    )
    referenced = {
        "kind": "fact",
        "text": "evidence-backed",
        "evidence_refs": ["source"],
    }
    approved_case = replace(
        spec.research_case,
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
    spec = replace(spec, research_case=approved_case)

    without_approval = app.run_company_research(spec)
    assert without_approval.gate.results[GATE_VALUATION] is False

    approval = ResearchValuationApproval(
        model_id="residual_income_or_equity_value",
        model_type=without_approval.valuation.model_type,
        model_version=without_approval.valuation.model_version,
        valuation_date=without_approval.valuation.valuation_date,
        result_sha256=valuation_result_sha256(without_approval.valuation),
        approved_at=AVAILABLE_AT,
        approver="human-reviewer",
        evidence_refs=[{"id": "approval"}],
    )
    with_approval = app.run_company_research(
        replace(spec, valuation_approval=approval)
    )

    assert with_approval.gate.results[GATE_VALUATION] is True
    assert with_approval.gate.ready_for_price_assessment is True
    stored_gate = app.repository.load_latest(
        SCOPE_SECURITY,
        "600519",
        ARTIFACT_RESEARCH_GATE,
    )
    assert any(
        ref.get("id") == "approval"
        for ref in stored_gate.envelope.evidence_refs
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
        input_sources=spec.input_sources,
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
