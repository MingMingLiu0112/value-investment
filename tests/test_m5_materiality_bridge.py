from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

import pytest

from value_investment_agent.event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.m5_event_core import (
    EVENT_TYPE_MATERIAL_ANNOUNCEMENT,
    NAMESPACE_SIMULATED,
    SEVERITY_HIGH,
    SEVERITY_MEDIUM,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_VALUATION_INPUTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_event_run import run_event_batch
from value_investment_agent.m5_event_watermark import (
    SOURCE_HEALTHY,
    WATERMARK_COVERAGE_COMPLETE,
    ScanWatermark,
)
from value_investment_agent.m5_materiality_bridge import (
    MATERIALITY_BRIDGE_SCHEMA,
    build_materiality_bridge_batch,
    materiality_direct_kinds,
    materiality_event_from_decision,
)


TZ = timezone(datetime.now(timezone.utc).astimezone().utcoffset())
PUBLISHED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=TZ)
REVIEWED_AT = datetime(2026, 9, 24, 9, 30, tzinfo=TZ)


def _decision(
    human_decision: str,
    *,
    announcement_id: str = "1225542476",
    affected_domains: tuple[str, ...] = (),
    affected_fact_fields: tuple[str, ...] = (),
    affected_assumptions: tuple[str, ...] = (),
    affected_artifacts: tuple[str, ...] = (),
) -> EventMaterialityDecision:
    recalc = human_decision == DECISION_REQUIRES_RECALCULATION
    stale = human_decision == DECISION_REQUIRES_RECALCULATION
    followup = human_decision in {
        DECISION_REQUIRES_DECOMPOSITION,
        DECISION_RISK_MONITOR,
    }
    return EventMaterialityDecision(
        event_decision_id=f"event-decision-{announcement_id}",
        symbol="600887",
        announcement_id=announcement_id,
        title="fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"pdf-{announcement_id}",
            "path": f"fixtures/{announcement_id}.pdf",
            "sha256": "a" * 64,
        },
        source_sha256="a" * 64,
        machine_candidate_reason="rule candidate from title",
        human_decision=human_decision,
        affected_domains=affected_domains,
        affected_fact_fields=affected_fact_fields,
        affected_assumptions=affected_assumptions,
        affected_artifacts=affected_artifacts,
        requires_recalculation=recalc,
        requires_model_stale=stale,
        requires_followup=followup,
        reviewed_at=REVIEWED_AT,
        review_notes=("human review note",),
    )


def _review(decisions: tuple[EventMaterialityDecision, ...]) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-event-review-20260924",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol="600887",
        scan_id="600887-scan-20260924",
        scan_sha256="b" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=date(2026, 9, 24),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=decisions,
        evidence_refs=({"id": "scan"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts-600887",
                kind=KIND_FACTS,
                symbol="600887",
                inputs=(),
                version="v1",
                evidence_refs=({"id": "facts"},),
            ),
            DependencyNode(
                node_id="valuation-inputs-600887",
                kind=KIND_VALUATION_INPUTS,
                symbol="600887",
                inputs=("facts-600887",),
                version="v1",
                evidence_refs=({"id": "valuation"},),
            ),
            DependencyNode(
                node_id="model-validity-600887",
                kind=KIND_MODEL_VALIDITY,
                symbol="600887",
                inputs=(),
                version="v1",
                evidence_refs=({"id": "model"},),
            ),
            DependencyNode(
                node_id="decision-review-600887",
                kind=KIND_DECISION_REVIEW,
                symbol="600887",
                inputs=("valuation-inputs-600887",),
                version="v1",
                evidence_refs=({"id": "decision"},),
            ),
            DependencyNode(
                node_id="current-status-600887",
                kind=KIND_CURRENT_STATUS,
                symbol="600887",
                inputs=("decision-review-600887",),
                version="v1",
                evidence_refs=({"id": "status"},),
            ),
        )
    )


def _watermark() -> ScanWatermark:
    return ScanWatermark(
        watermark_id="materiality-scan-20260924",
        scope="600887",
        source="cninfo",
        coverage_through=REVIEWED_AT,
        retrieved_at=REVIEWED_AT,
        parser_version="fixture-v1",
        coverage_status=WATERMARK_COVERAGE_COMPLETE,
        source_health=SOURCE_HEALTHY,
        evidence_refs=({"id": "scan"},),
    )


def test_silent_materiality_decision_does_not_create_event():
    decision = _decision(DECISION_ALREADY_INCORPORATED)

    assert materiality_event_from_decision(
        decision,
        namespace=NAMESPACE_SIMULATED,
    ) is None
    assert materiality_direct_kinds(decision) == ()


def test_recalculation_decision_maps_to_precise_event_and_dependencies():
    decision = _decision(
        DECISION_REQUIRES_RECALCULATION,
        affected_domains=("balance_sheet_risk",),
        affected_fact_fields=("total_liabilities",),
    )
    event = materiality_event_from_decision(
        decision,
        namespace=NAMESPACE_SIMULATED,
    )

    assert event is not None
    assert event.event_type == EVENT_TYPE_MATERIAL_ANNOUNCEMENT
    assert event.severity == SEVERITY_HIGH
    assert event.available_at == PUBLISHED_AT
    assert event.detected_at == REVIEWED_AT
    assert event.current_state["materiality_status"] == DECISION_REQUIRES_RECALCULATION
    assert event.current_state["source_sha256"] == "a" * 64
    assert event.current_state["source_ref_id"] == "pdf-1225542476"
    assert event.current_state["source_ref_sha256"] == "a" * 64
    assert event.evidence_refs[0]["sha256"] == "a" * 64
    human_refs = tuple(
        ref
        for ref in event.evidence_refs
        if ref.get("type") == "human_event_materiality_review"
    )
    assert len(human_refs) == 1
    assert human_refs[0]["source_sha256"] == "a" * 64
    kinds = materiality_direct_kinds(decision)
    assert KIND_FACTS in kinds
    assert KIND_MODEL_VALIDITY in kinds
    assert KIND_VALUATION_INPUTS in kinds
    assert KIND_DECISION_REVIEW in kinds


def test_decomposition_and_risk_monitor_do_not_invalidate_model():
    decomposition = _decision(DECISION_REQUIRES_DECOMPOSITION)
    risk_monitor = _decision(DECISION_RISK_MONITOR)

    assert KIND_MODEL_VALIDITY not in materiality_direct_kinds(decomposition)
    assert KIND_DECISION_REVIEW in materiality_direct_kinds(decomposition)
    assert KIND_CURRENT_STATUS in materiality_direct_kinds(decomposition)
    assert materiality_direct_kinds(risk_monitor) == (KIND_DECISION_REVIEW,)
    risk_event = materiality_event_from_decision(
        risk_monitor,
        namespace=NAMESPACE_SIMULATED,
    )
    assert risk_event is not None
    assert risk_event.severity == SEVERITY_MEDIUM


def test_unknown_domain_is_preserved_instead_of_silently_mapped():
    decision = _decision(
        DECISION_REQUIRES_RECALCULATION,
        affected_domains=("a_future_domain_without_a_registered_meaning",),
    )
    event = materiality_event_from_decision(
        decision,
        namespace=NAMESPACE_SIMULATED,
    )

    assert event is not None
    assert event.current_state["unmapped_domains"] == [
        "a_future_domain_without_a_registered_meaning"
    ]


def test_review_cannot_precede_publication():
    decision = replace(
        _decision(DECISION_REQUIRES_RECALCULATION),
        published_at=REVIEWED_AT,
        reviewed_at=PUBLISHED_AT,
    )

    with pytest.raises(ValueError, match="cannot precede"):
        materiality_event_from_decision(
            decision,
            namespace=NAMESPACE_SIMULATED,
        )


def test_review_window_and_decision_clock_cannot_extend_beyond_review() -> None:
    review = _review((_decision(DECISION_REQUIRES_RECALCULATION),))

    with pytest.raises(ValueError, match="cannot extend beyond"):
        replace(review, scan_to=review.review_as_of + timedelta(days=1))

    late_decision = replace(
        review.decisions[0],
        reviewed_at=review.reviewed_at + timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="decision time cannot follow"):
        replace(review, decisions=(late_decision,))


def test_materiality_event_rejects_unbound_or_tampered_source_hashes():
    event = materiality_event_from_decision(
        _decision(DECISION_REQUIRES_RECALCULATION),
        namespace=NAMESPACE_SIMULATED,
    )
    assert event is not None

    mismatched_state = dict(event.current_state)
    mismatched_state["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="source_ref_sha256"):
        replace(event, current_state=mismatched_state)

    tampered_evidence = tuple(dict(ref) for ref in event.evidence_refs)
    for ref in tampered_evidence:
        if ref.get("type") == "human_event_materiality_review":
            ref["source_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="Human materiality evidence hash"):
        replace(event, evidence_refs=tampered_evidence)

    tampered_source = tuple(dict(ref) for ref in event.evidence_refs)
    tampered_source[0]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="source reference hash"):
        replace(event, evidence_refs=tampered_source)


def test_bridge_batch_preserves_silence_and_feeds_run_with_custom_policy():
    review = _review(
        (
            _decision(DECISION_ALREADY_INCORPORATED, announcement_id="1225542476"),
            _decision(
                DECISION_REQUIRES_RECALCULATION,
                announcement_id="1225511493",
                affected_domains=("balance_sheet_risk",),
            ),
        )
    )
    batch = build_materiality_bridge_batch(
        review,
        namespace=NAMESPACE_SIMULATED,
    )

    assert batch.schema_version == MATERIALITY_BRIDGE_SCHEMA
    assert batch.silent_count == 1
    assert len(batch.events) == 1
    assert batch.direct_kinds_by_source_event_id
    receipt = run_event_batch(
        events=batch.events,
        observed_times=batch.observed_times,
        watermark=_watermark(),
        graph=_graph(),
        run_id="materiality-run-20260924",
        generated_at=REVIEWED_AT,
        namespace=NAMESPACE_SIMULATED,
        direct_kinds_by_source_event_id=batch.direct_kinds_by_source_event_id,
    )

    affected_kinds = {
        item.kind
        for invalidation in receipt.invalidations
        for item in invalidation.affected_nodes
    }
    assert KIND_FACTS in affected_kinds
    assert KIND_VALUATION_INPUTS in affected_kinds
    assert KIND_DECISION_REVIEW in affected_kinds
    assert receipt.action == "no_order"
