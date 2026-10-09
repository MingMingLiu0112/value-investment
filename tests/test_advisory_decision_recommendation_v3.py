from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from value_investment_agent.application.decision.build_advisory_decision_recommendation_v3 import (
    build_advisory_decision_recommendation_v3,
)
from value_investment_agent.application.decision.restore_decision_recommendation import (
    restore_decision_recommendation,
    verify_decision_recommendation_payload,
)
from value_investment_agent.domain.decision.decision_recommendation import (
    DECISION_RECOMMENDATION_V3_SCHEMA,
    RECOMMENDATION_ADD_CANDIDATE,
    RECOMMENDATION_BUY_CANDIDATE,
    RECOMMENDATION_HOLD,
    RECOMMENDATION_NO_ACTION,
    RECOMMENDATION_SELL_CANDIDATE,
    RECOMMENDATION_TRIM_CANDIDATE,
    decision_recommendation_from_payload,
)
from value_investment_agent.domain.decision.recommendation_rules import (
    CONSISTENCY_BROKEN,
    CONSISTENCY_CONSISTENT,
    CONSISTENCY_WEAKENED,
    RecommendationRuleInputs,
)
from value_investment_agent.investment_decision import (
    COMPARISON_BROKEN,
    COMPARISON_FULFILLED,
    COMPARISON_NEGATIVE,
    COMPARISON_NEUTRAL,
    DIMENSION_THESIS,
    ENTRY_TYPE_ACTUAL,
    ENTRY_TYPE_SIMULATED,
    ConsistencyComparison,
    EntryThesisSnapshot,
    InvestmentConsistencyReview,
)
from value_investment_agent.pre_decision_eligibility import (
    evaluate_pre_decision_eligibility,
    STATUS_NOT_ELIGIBLE,
)
from value_investment_agent.price_attractiveness import STATUS_NOT_ASSESSABLE
from value_investment_agent.quote_snapshot import QUOTE_STATUS_PENDING_EXTERNAL_DATA
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifact_codecs import (
    artifact_payload,
    decode_artifact,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION,
    ARTIFACT_ENTRY_THESIS_SNAPSHOT,
    ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    SCOPE_SECURITY,
    StoredResearchArtifact,
)
from value_investment_agent.valuation_models.fcff import FinancialFacts
from value_investment_agent.domain.research.research_gate import ResearchGate

from test_decision_recommendation import (
    AS_OF,
    MODEL_ID,
    SYMBOL,
    _approval_bundle,
    _assumptions_payload,
    _bridge,
    _case,
    _dependencies,
    _event_materiality,
    _facts_payload,
    _predecision,
    _price,
    _stored_dependencies,
    _valuation,
    _validity,
)


CONFIRMED_AT = datetime(2026, 9, 22, tzinfo=timezone.utc)


def _entry() -> EntryThesisSnapshot:
    return EntryThesisSnapshot(
        entry_id=f"{SYMBOL}-entry-v1",
        symbol=SYMBOL,
        confirmed_at=CONFIRMED_AT,
        entry_type=ENTRY_TYPE_ACTUAL,
        entry_date=AS_OF,
        entry_price=Decimal("18"),
        review_id=f"{SYMBOL}-buy-review-v1",
        bundle_id=f"{SYMBOL}-bundle-v1",
        thesis="品牌与渠道支持长期现金回报",
        return_driver="经营现金流转换",
        mispricing_hypothesis="市场低估稳定现金回报",
        bear_value=Decimal("20"),
        base_value=Decimal("30"),
        bull_value=Decimal("40"),
        confidence="中",
        dividend_thesis="稳定分红",
        hold_logic="只要现金转换和品牌力不恶化则持有",
        risks=("消费需求下行",),
        counter_evidence=("利润增速放缓",),
        breakers=("品牌力永久下降",),
        catalysts=("下一期财报",),
        reasons_to_add=("新增产能兑现",),
        reasons_not_to_add=("估值已高于基准",),
        reasons_to_reduce=("行业集中度风险上升",),
        reasons_to_exit=("原始论点已破裂",),
    )


def _consistency(status: str) -> InvestmentConsistencyReview:
    impact = {
        CONSISTENCY_CONSISTENT: COMPARISON_NEUTRAL,
        "FULFILLED": COMPARISON_FULFILLED,
        CONSISTENCY_WEAKENED: COMPARISON_NEGATIVE,
        CONSISTENCY_BROKEN: COMPARISON_BROKEN,
    }[status]
    entry = _entry()
    return InvestmentConsistencyReview(
        review_id=f"{SYMBOL}-consistency-v1",
        symbol=SYMBOL,
        entry_id=entry.entry_id,
        as_of=AS_OF,
        status=status,
        comparisons=(
            ConsistencyComparison(
                dimension=DIMENSION_THESIS,
                original_value="original",
                current_value="current",
                impact=impact,
                change_reason="fixture review",
                evidence_refs=({"id": "consistency-source"},),
            ),
        ),
        evidence_refs=({"id": "consistency-source"},),
    )


def _stored(value: object, artifact_type: str, role: str) -> StoredResearchArtifact:
    _, payload = artifact_payload(value)
    identity = ResearchArtifactIdentity(
        scope_type=SCOPE_SECURITY,
        scope_key=SYMBOL,
        artifact_type=artifact_type,
        schema_version="m3-investment-decision-v2",
        as_of=AS_OF,
        available_at=CONFIRMED_AT,
    )
    return StoredResearchArtifact(
        artifact_id=f"fixture-{role}",
        envelope=ResearchArtifactEnvelope.build(
            identity=identity,
            payload=payload,
            run_id=f"fixture-{role}",
        ),
        created_at=CONFIRMED_AT,
    )


def _save_object(
    repository: InMemoryResearchArtifactRepository,
    value: object,
    role: str,
) -> StoredResearchArtifact:
    artifact_type, _ = artifact_payload(value)
    return repository.save_object(
        value,
        identity=ResearchArtifactIdentity(
            scope_type=SCOPE_SECURITY,
            scope_key=SYMBOL,
            artifact_type=artifact_type,
            schema_version="research-artifact-v1",
            as_of=AS_OF,
            available_at=CONFIRMED_AT,
        ),
        run_id=f"fixture-{role}",
    )


def _repository_dependencies(
    *,
    entry: EntryThesisSnapshot | None = None,
    consistency: InvestmentConsistencyReview | None = None,
    include_positive_gate: bool = False,
):
    repository = InMemoryResearchArtifactRepository()
    dependencies = _dependencies()
    financial_facts = FinancialFacts(
        symbol=SYMBOL,
        as_of=AS_OF,
        verified=True,
        evidence_refs=[{"id": "facts-source"}],
        blockers=[],
    )
    research_gate = ResearchGate(
        symbol=SYMBOL,
        results={
            "G0_证据门": True,
            "G1_财务门": True,
            "G2_商业论点门": True,
            "G3_估值门": True,
        },
        blockers=[],
        conclusion="research ready",
    )
    values: dict[str, object] = {
        "research_case": dependencies["research_case"],
        "valuation": dependencies["valuation"],
        "model_validity": dependencies["model_validity"],
        "financial_facts": financial_facts,
        "research_gate": research_gate,
        "event_materiality": dependencies["event_materiality"],
    }
    if include_positive_gate:
        values.update(
            {
                "price_bridge": dependencies["price_bridge"],
                "price_attractiveness": dependencies["price_attractiveness"],
                "human_approval": dependencies["human_approval"],
                "pre_decision": evaluate_pre_decision_eligibility(
                    gate=research_gate,
                    valuation=dependencies["valuation"],
                    approval=dependencies["human_approval"],
                    model_validity=dependencies["model_validity"],
                    price_bridge=dependencies["price_bridge"],
                    event_materiality=dependencies["event_materiality"],
                    decision_as_of=AS_OF,
                    model_id=MODEL_ID,
                    research_case_payload=artifact_payload(
                        dependencies["research_case"]
                    )[1],
                    facts_payload=_facts_payload(),
                    assumptions_payload=_assumptions_payload(),
                    price_attractiveness=dependencies["price_attractiveness"],
                ),
            }
        )
    if entry is not None:
        values["entry_thesis"] = entry
    if consistency is not None:
        values["investment_consistency_review"] = consistency
    stored = {
        role: _save_object(repository, value, role)
        for role, value in values.items()
    }
    return repository, stored, values
    return StoredResearchArtifact(
        artifact_id=f"fixture-{role}",
        envelope=ResearchArtifactEnvelope.build(
            identity=identity,
            payload=payload,
            run_id=f"fixture-{role}",
        ),
        created_at=CONFIRMED_AT,
    )


def _build_v3(
    *,
    entry: EntryThesisSnapshot | None = None,
    consistency: InvestmentConsistencyReview | None = None,
    rule_evidence: RecommendationRuleInputs | None = None,
    bridge=None,
    price=None,
    predecision=None,
    validity=None,
):
    case = _case()
    valuation = _valuation()
    selected_validity = validity or _validity()
    selected_bridge = bridge or _bridge()
    selected_price = price or _price()
    selected_predecision = predecision or _predecision()
    dependencies = _dependencies() | {
        "model_validity": selected_validity,
        "price_bridge": selected_bridge,
        "price_attractiveness": selected_price,
        "pre_decision": selected_predecision,
    }
    stored = _stored_dependencies(dependencies)
    if entry is not None:
        stored["entry_thesis"] = _stored(
            entry, ARTIFACT_ENTRY_THESIS_SNAPSHOT, "entry_thesis"
        )
    if consistency is not None:
        stored["investment_consistency_review"] = _stored(
            consistency,
            ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
            "investment_consistency_review",
        )
    return build_advisory_decision_recommendation_v3(
        run_id="d3-v3-run",
        research_case=case,
        valuation=valuation,
        model_validity=selected_validity,
        price_bridge=selected_bridge,
        price_attractiveness=selected_price,
        pre_decision=selected_predecision,
        human_approval=dependencies["human_approval"],
        entry_thesis=entry,
        investment_consistency_review=consistency,
        rule_evidence=rule_evidence,
        model_id=MODEL_ID,
        research_case_payload=dependencies["research_case_payload"],
        facts_payload=dependencies["facts_payload"],
        assumptions_payload=dependencies["assumptions_payload"],
        dependency_artifacts=stored,
        event_materiality=_event_materiality(),
    )


def _pending_quote_inputs():
    pending_bridge = replace(
        _bridge(),
        quote_date=None,
        current_price=None,
        margin_to_bear=None,
        margin_to_base=None,
        quote_status=QUOTE_STATUS_PENDING_EXTERNAL_DATA,
        bridge_status="PENDING_EXTERNAL_DATA",
        quote_evidence_refs=[],
    )
    pending_price = replace(
        _price(),
        status=STATUS_NOT_ASSESSABLE,
        margin_to_bear=None,
        margin_to_base=None,
        downside_reference=None,
        upside_reference=None,
        blockers=["pending_quote"],
    )
    pending_predecision = replace(
        _predecision(),
        status=STATUS_NOT_ELIGIBLE,
        price_bridge_status="PENDING_EXTERNAL_DATA",
        price_attractiveness_status=STATUS_NOT_ASSESSABLE,
        positive_price_review_eligible=False,
        blockers=("price_bridge_pending_external_data",),
    )
    return pending_bridge, pending_price, pending_predecision


def test_v3_buy_keeps_no_order_and_human_review() -> None:
    recommendation = _build_v3()
    assert recommendation.schema_version == DECISION_RECOMMENDATION_V3_SCHEMA
    assert recommendation.recommendation_action == RECOMMENDATION_BUY_CANDIDATE
    assert recommendation.action == "no_order"
    assert recommendation.requires_human_review is True
    assert recommendation.position_guidance is None
    assert recommendation.portfolio_input_status == "BLOCKED_PRIVATE_INPUT"
    payload = recommendation.as_policy()
    assert payload["recommendation_type"] == RECOMMENDATION_BUY_CANDIDATE
    assert payload["requires_human_review"] is True
    assert decision_recommendation_from_payload(
        payload, verify_dependencies=False
    ).recommendation_action == RECOMMENDATION_BUY_CANDIDATE


def test_v3_add_requires_entry_incremental_evidence_and_full_buy_gate() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency("FULFILLED"),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_ADD_CANDIDATE
    assert recommendation.entry_id == _entry().entry_id
    assert recommendation.thesis_consistency_status == "FULFILLED"


def test_price_only_add_does_not_create_add_candidate() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_CONSISTENT),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_HOLD


def test_v3_hold_requires_current_review_and_valid_model() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_CONSISTENT),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_HOLD
    assert recommendation.requires_human_review is True


def test_v3_trim_requires_weakened_thesis_and_original_entry() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_WEAKENED),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_TRIM_CANDIDATE
    assert recommendation.entry_id == _entry().entry_id


def test_v3_sell_works_without_current_quote_when_thesis_is_broken() -> None:
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_BROKEN),
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
    assert recommendation.current_price is None
    assert recommendation.action == "no_order"


def test_broken_consistency_without_entry_cannot_create_buy() -> None:
    with pytest.raises(ValueError, match="rule evidence does not match"):
        _build_v3(
            rule_evidence=RecommendationRuleInputs(
                has_entry=False,
                consistency_status=CONSISTENCY_BROKEN,
            )
        )
    recommendation = _build_v3()
    assert recommendation.recommendation_action == RECOMMENDATION_BUY_CANDIDATE


def test_v3_sell_without_exit_condition_is_not_promoted() -> None:
    case = replace(_case(), thesis_breakers=[])
    dependencies = _dependencies() | {"research_case": case}
    stored = _stored_dependencies(dependencies)
    entry = replace(_entry(), reasons_to_exit=())
    consistency = _consistency(CONSISTENCY_BROKEN)
    stored["entry_thesis"] = _stored(
        entry, ARTIFACT_ENTRY_THESIS_SNAPSHOT, "entry_thesis"
    )
    stored["investment_consistency_review"] = _stored(
        consistency,
        ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
        "investment_consistency_review",
    )
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-no-exit",
        research_case=case,
        valuation=_valuation(),
        model_validity=_validity(),
        price_bridge=_bridge(),
        price_attractiveness=_price(),
        pre_decision=_predecision(),
        human_approval=dependencies["human_approval"],
        entry_thesis=entry,
        investment_consistency_review=consistency,
        model_id=MODEL_ID,
        research_case_payload=dependencies["research_case_payload"],
        facts_payload=dependencies["facts_payload"],
        assumptions_payload=dependencies["assumptions_payload"],
        dependency_artifacts=stored,
        event_materiality=_event_materiality(),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION


def test_v3_sell_exact_repository_replay_without_quote() -> None:
    entry = _entry()
    consistency = _consistency(CONSISTENCY_BROKEN)
    repository, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
    )
    _, case_payload = artifact_payload(values["research_case"])
    _, facts_payload = artifact_payload(values["financial_facts"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-restore-sell",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        human_approval=None,
        entry_thesis=entry,
        investment_consistency_review=consistency,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload={},
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
    restored = verify_decision_recommendation_payload(
        repository,
        payload=recommendation.as_policy(),
    )
    assert restored.recommendation.as_policy() == recommendation.as_policy()


def test_v3_derives_hold_without_supplied_rule_evidence() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_CONSISTENT),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_HOLD
    assert recommendation.entry_id == _entry().entry_id
    assert recommendation.thesis_consistency_status == CONSISTENCY_CONSISTENT
    assert recommendation.rule_evidence["hold_logic_present"] is True
    assert recommendation.requires_human_review is True
    assert recommendation.position_guidance is None
    assert recommendation.action == "no_order"


def test_v3_derives_add_from_fulfilled_consistency() -> None:
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency("FULFILLED"),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_ADD_CANDIDATE
    assert recommendation.rule_evidence["add_evidence_present"] is True
    assert recommendation.entry_id == _entry().entry_id


def test_v3_derives_trim_without_a_quote_when_the_thesis_weakens() -> None:
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_WEAKENED),
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_TRIM_CANDIDATE
    assert recommendation.rule_evidence["trim_reason_present"] is True
    assert recommendation.current_price is None
    assert recommendation.position_guidance is None


def test_v3_derives_sell_without_a_quote_when_the_thesis_breaks() -> None:
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_BROKEN),
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
    assert recommendation.thesis_consistency_status == CONSISTENCY_BROKEN
    assert recommendation.current_price is None
    assert recommendation.action == "no_order"


def test_v3_without_an_original_entry_cannot_reduce_or_add_risk() -> None:
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    with pytest.raises(ValueError, match="rule evidence does not match"):
        _build_v3(
            rule_evidence=RecommendationRuleInputs(
                has_entry=True,
                add_evidence_present=True,
                hold_logic_present=True,
                trim_reason_present=True,
                sell_reason_present=True,
                exit_condition_present=True,
            ),
            bridge=pending_bridge,
            price=pending_price,
            predecision=pending_predecision,
        )


def test_v3_risk_reduction_requires_a_consistency_review_with_evidence() -> None:
    review_without_evidence = replace(
        _consistency(CONSISTENCY_BROKEN),
        comparisons=(
            replace(
                _consistency(CONSISTENCY_BROKEN).comparisons[0],
                evidence_refs=(),
            ),
        ),
        evidence_refs=(),
    )
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=review_without_evidence,
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION


def test_v3_risk_reduction_survives_a_stale_model() -> None:
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    stale_bridge = replace(pending_bridge, model_validity_status="STALE")
    recommendation = _build_v3(
        entry=_entry(),
        consistency=_consistency(CONSISTENCY_BROKEN),
        bridge=stale_bridge,
        price=pending_price,
        predecision=pending_predecision,
        validity=replace(_validity(), status="STALE", material_event_found=True),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
    assert any(
        blocker.startswith("model_validity") for blocker in recommendation.blockers
    )


def test_v3_risk_reduction_is_blocked_by_unverified_research_evidence() -> None:
    case = replace(_case(), evidence_status="unverified")
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    dependencies = _dependencies() | {
        "research_case": case,
        "price_bridge": pending_bridge,
        "price_attractiveness": pending_price,
        "pre_decision": pending_predecision,
    }
    stored = _stored_dependencies(dependencies)
    entry = _entry()
    consistency = _consistency(CONSISTENCY_BROKEN)
    stored["entry_thesis"] = _stored(
        entry, ARTIFACT_ENTRY_THESIS_SNAPSHOT, "entry_thesis"
    )
    stored["investment_consistency_review"] = _stored(
        consistency,
        ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
        "investment_consistency_review",
    )
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-unverified-research",
        research_case=case,
        valuation=_valuation(),
        model_validity=_validity(),
        price_bridge=pending_bridge,
        price_attractiveness=pending_price,
        pre_decision=pending_predecision,
        human_approval=dependencies["human_approval"],
        entry_thesis=entry,
        investment_consistency_review=consistency,
        model_id=MODEL_ID,
        research_case_payload=dependencies["research_case_payload"],
        facts_payload=dependencies["facts_payload"],
        assumptions_payload=dependencies["assumptions_payload"],
        dependency_artifacts=stored,
        event_materiality=_event_materiality(),
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    assert "research_evidence_not_verified" in recommendation.blockers


def test_v3_no_quote_state_invents_no_price_evidence() -> None:
    entry = _entry()
    consistency = _consistency(CONSISTENCY_BROKEN)
    repository, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
    )
    _, case_payload = artifact_payload(values["research_case"])
    _, facts_payload = artifact_payload(values["financial_facts"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-no-quote-evidence",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        human_approval=None,
        entry_thesis=entry,
        investment_consistency_review=consistency,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload={},
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_SELL_CANDIDATE
    assert recommendation.current_price is None
    assert recommendation.price_bridge_status == "PENDING_EXTERNAL_DATA"
    assert recommendation.price_attractiveness_status == STATUS_NOT_ASSESSABLE
    ref_ids = [str(ref.get("id", "")) for ref in recommendation.evidence_refs]
    assert all("pending-price" not in ref_id for ref_id in ref_ids)


def test_v3_payload_rejects_a_coercible_human_review_flag() -> None:
    payload = _build_v3().as_policy()
    assert payload["requires_human_review"] is True
    for forged in ("false", 0, 1, None):
        with pytest.raises(ValueError):
            decision_recommendation_from_payload(
                {**payload, "requires_human_review": forged},
                verify_dependencies=False,
            )


def test_v3_hold_exact_repository_replay() -> None:
    entry = _entry()
    consistency = _consistency(CONSISTENCY_CONSISTENT)
    repository, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
    )
    _, case_payload = artifact_payload(values["research_case"])
    _, facts_payload = artifact_payload(values["financial_facts"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-restore-hold",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        human_approval=None,
        entry_thesis=entry,
        investment_consistency_review=consistency,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload={},
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_HOLD
    restored = verify_decision_recommendation_payload(
        repository,
        payload=recommendation.as_policy(),
    )
    assert restored.recommendation.as_policy() == recommendation.as_policy()


def test_v3_add_requires_the_full_positive_dependency_contract() -> None:
    entry = _entry()
    consistency = _consistency("FULFILLED")
    _, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
        include_positive_gate=True,
    )
    _, case_payload = artifact_payload(values["research_case"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-restore-add",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=values["price_bridge"],
        price_attractiveness=values["price_attractiveness"],
        pre_decision=values["pre_decision"],
        human_approval=values["human_approval"],
        entry_thesis=entry,
        investment_consistency_review=consistency,
        model_id=MODEL_ID,
        research_case_payload=case_payload,
        facts_payload=_facts_payload(),
        assumptions_payload=_assumptions_payload(),
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_ADD_CANDIDATE
    payload = recommendation.as_policy()
    roles = {ref["role"] for ref in payload["decision_dependency_refs"]}
    assert {
        "price_bridge",
        "price_attractiveness",
        "pre_decision",
        "human_approval",
        "entry_thesis",
        "investment_consistency_review",
    } <= roles
    assert payload["requires_human_review"] is True
    assert payload["position_guidance"] is None
    with pytest.raises(ValueError):
        decision_recommendation_from_payload(
            {
                **payload,
                "decision_dependency_refs": [
                    ref for ref in payload["decision_dependency_refs"]
                    if ref["role"] != "human_approval"
                ],
            },
            verify_dependencies=False,
        )


def test_v3_builder_rejects_cross_symbol_entry_dependency() -> None:
    entry = replace(_entry(), symbol="000001")
    with pytest.raises(ValueError, match="entry thesis symbol"):
        _build_v3(entry=entry, consistency=_consistency(CONSISTENCY_CONSISTENT))


def test_v3_builder_rejects_mismatched_entry_review_pair() -> None:
    review = replace(
        _consistency(CONSISTENCY_CONSISTENT), entry_id="another-entry"
    )
    with pytest.raises(ValueError, match="entry_id"):
        _build_v3(entry=_entry(), consistency=review)


def test_v3_builder_rejects_simulated_entry_in_production() -> None:
    entry = replace(_entry(), entry_type=ENTRY_TYPE_SIMULATED)
    with pytest.raises(ValueError, match="actual entry thesis"):
        _build_v3(entry=entry, consistency=_consistency(CONSISTENCY_CONSISTENT))


def test_v3_builder_rejects_future_entry_confirmation() -> None:
    entry = replace(
        _entry(),
        entry_date=AS_OF + timedelta(days=1),
        confirmed_at=CONFIRMED_AT + timedelta(days=2),
    )
    review = replace(
        _consistency(CONSISTENCY_CONSISTENT), as_of=AS_OF + timedelta(days=1)
    )
    with pytest.raises(ValueError, match="cannot follow"):
        _build_v3(entry=entry, consistency=review)


def test_v3_trim_requires_negative_comparison_evidence_not_review_level_evidence() -> None:
    review = _consistency(CONSISTENCY_WEAKENED)
    review = replace(
        review,
        comparisons=(replace(review.comparisons[0], evidence_refs=()),),
        evidence_refs=({"id": "review-only-evidence"},),
    )
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=review,
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION


def test_v3_sell_requires_broken_comparison_evidence_not_review_level_evidence() -> None:
    review = _consistency(CONSISTENCY_BROKEN)
    review = replace(
        review,
        comparisons=(replace(review.comparisons[0], evidence_refs=()),),
        evidence_refs=({"id": "review-only-evidence"},),
    )
    pending_bridge, pending_price, pending_predecision = _pending_quote_inputs()
    recommendation = _build_v3(
        entry=_entry(),
        consistency=review,
        bridge=pending_bridge,
        price=pending_price,
        predecision=pending_predecision,
    )
    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION


def test_v3_add_requires_fulfilled_comparison_evidence() -> None:
    review = _consistency("FULFILLED")
    review = replace(
        review,
        comparisons=(replace(review.comparisons[0], evidence_refs=()),),
        evidence_refs=({"id": "review-only-evidence"},),
    )
    recommendation = _build_v3(entry=_entry(), consistency=review)
    assert recommendation.recommendation_action != RECOMMENDATION_ADD_CANDIDATE


def test_v3_hold_payload_cannot_forge_trim_rule_evidence() -> None:
    entry = _entry()
    consistency = _consistency(CONSISTENCY_CONSISTENT)
    repository, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
    )
    _, case_payload = artifact_payload(values["research_case"])
    _, facts_payload = artifact_payload(values["financial_facts"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-forged-trim",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        human_approval=None,
        entry_thesis=entry,
        investment_consistency_review=consistency,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload={},
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    assert recommendation.recommendation_action == RECOMMENDATION_HOLD
    forged_rule_evidence = dict(recommendation.rule_evidence or {})
    forged_rule_evidence["trim_reason_present"] = True
    forged = replace(
        recommendation,
        recommendation_action=RECOMMENDATION_TRIM_CANDIDATE,
        rule_evidence=forged_rule_evidence,
        recommendation_payload_sha256=None,
    )
    with pytest.raises(ValueError, match="rule evidence"):
        verify_decision_recommendation_payload(
            repository,
            payload=forged.as_policy(),
        )


def test_v3_no_action_downgrade_still_requires_repository_replay() -> None:
    entry = _entry()
    consistency = _consistency(CONSISTENCY_CONSISTENT)
    repository, stored, values = _repository_dependencies(
        entry=entry,
        consistency=consistency,
    )
    _, case_payload = artifact_payload(values["research_case"])
    _, facts_payload = artifact_payload(values["financial_facts"])
    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-downgrade",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=values["model_validity"],
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        human_approval=None,
        entry_thesis=entry,
        investment_consistency_review=consistency,
        research_case_payload=case_payload,
        facts_payload=facts_payload,
        assumptions_payload={},
        dependency_artifacts=stored,
        event_materiality=values["event_materiality"],
    )
    downgraded = replace(
        recommendation,
        recommendation_action=RECOMMENDATION_NO_ACTION,
        requires_human_review=False,
        recommendation_payload_sha256=None,
    )
    payload = downgraded.as_policy()
    with pytest.raises(ValueError, match="requires a repository"):
        decode_artifact(ARTIFACT_DECISION_RECOMMENDATION, payload)
    with pytest.raises(ValueError):
        decode_artifact(
            ARTIFACT_DECISION_RECOMMENDATION,
            payload,
            repository=repository,
        )


def test_v3_no_action_replays_without_optional_model_event_or_quote() -> None:
    repository, stored, values = _repository_dependencies()
    base_roles = ("research_case", "financial_facts", "research_gate", "valuation")
    dependencies = {role: stored[role] for role in base_roles}

    recommendation = build_advisory_decision_recommendation_v3(
        run_id="d3-no-action-minimal",
        research_case=values["research_case"],
        valuation=values["valuation"],
        model_validity=None,
        price_bridge=None,
        price_attractiveness=None,
        pre_decision=None,
        dependency_artifacts=dependencies,
        event_materiality=None,
    )

    assert recommendation.recommendation_action == RECOMMENDATION_NO_ACTION
    roles = {item["role"] for item in recommendation.decision_dependency_refs}
    assert roles == set(base_roles)
    decision = _save_object(repository, recommendation, "decision")
    restored = restore_decision_recommendation(
        repository,
        artifact_id=decision.artifact_id,
    )

    assert restored.recommendation.as_policy() == recommendation.as_policy()
    assert set(restored.dependencies) == set(base_roles)
