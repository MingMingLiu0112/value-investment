from datetime import date, datetime, timezone

import pytest

from value_investment_agent.event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_DUPLICATE,
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
    event_materiality_decision_from_payload,
    event_materiality_review_from_payload,
)
from value_investment_agent.model_validity import evaluate_model_validity


REVIEWED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
PUBLISHED_AT = datetime(2026, 9, 2, tzinfo=timezone.utc)
MODEL_DATE = date(2026, 9, 22)


def _decision(
    human_decision: str,
    *,
    announcement_id="1225542476",
    event_cluster_id=None,
    supersedes_event_id=None,
) -> EventMaterialityDecision:
    expected = {
        DECISION_NOT_MATERIAL: (False, False, False),
        DECISION_ALREADY_INCORPORATED: (False, False, False),
        DECISION_REQUIRES_RECALCULATION: (True, True, False),
        DECISION_RISK_MONITOR: (False, False, True),
        DECISION_DUPLICATE: (False, False, False),
        DECISION_REQUIRES_DECOMPOSITION: (False, False, True),
    }
    recalc, stale, followup = expected[human_decision]
    return EventMaterialityDecision(
        event_decision_id=f"event-decision-{announcement_id}",
        symbol="600887",
        announcement_id=announcement_id,
        title="fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"pdf-{announcement_id}",
            "path": f"fixtures/{announcement_id}.pdf",
        },
        source_sha256="a" * 64,
        machine_candidate_reason="rule candidate from title",
        human_decision=human_decision,
        affected_domains=("balance_sheet_risk",),
        affected_fact_fields=(),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=recalc,
        requires_model_stale=stale,
        requires_followup=followup,
        event_cluster_id=event_cluster_id,
        supersedes_event_id=supersedes_event_id,
        reviewed_at=REVIEWED_AT,
        review_notes=("human review note",),
    )


def _review(decisions) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-event-review-20260923",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol="600887",
        scan_id="600887-scan-20260923T051018Z",
        scan_sha256="b" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=MODEL_DATE,
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=tuple(decisions),
        evidence_refs=({"id": "scan"},),
    )


def _validity(review):
    return evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=MODEL_DATE,
        valid_from=MODEL_DATE,
        quote_date=MODEL_DATE,
        events=[],
        event_scan_evidence_refs=[{"id": "scan"}],
        event_materiality=review,
    )


def test_event_decision_round_trip_preserves_classification():
    decision = _decision(DECISION_RISK_MONITOR, event_cluster_id="RISK_CLUSTER")
    restored = event_materiality_decision_from_payload(decision.as_policy())

    assert restored == decision
    assert restored.human_decision == DECISION_RISK_MONITOR
    assert restored.requires_followup is True
    assert restored.requires_model_stale is False


def test_not_material_and_already_incorporated_do_not_stale_model():
    for decision in (
        _decision(DECISION_NOT_MATERIAL),
        _decision(DECISION_ALREADY_INCORPORATED),
    ):
        checked = _validity(_review((decision,)))
        assert checked.status == "VALID"
        assert checked.material_event_found is False


def test_material_recalculation_makes_model_stale():
    checked = _validity(_review((_decision(DECISION_REQUIRES_RECALCULATION),)))

    assert checked.status == "STALE"
    assert checked.material_event_found is True
    assert any("requires recalculation" in blocker for blocker in checked.blockers)


def test_risk_monitor_keeps_model_valid_but_records_review_due():
    checked = _validity(_review((_decision(DECISION_RISK_MONITOR),)))

    assert checked.status == "VALID"
    assert any("event_risk_monitor" in blocker for blocker in checked.blockers)


def test_duplicate_decision_requires_cluster_and_does_not_stale():
    with pytest.raises(ValueError, match="Duplicate"):
        _decision(DECISION_DUPLICATE)

    checked = _validity(
        _review(
            (
                _decision(
                    DECISION_DUPLICATE,
                    event_cluster_id="YILI_BUYBACK_2026",
                ),
            )
        )
    )
    assert checked.status == "VALID"


def test_decomposition_keeps_model_non_stale_but_reports_blocker():
    checked = _validity(_review((_decision(DECISION_REQUIRES_DECOMPOSITION),)))

    assert checked.status == "VALID"
    assert any("event_requires_decomposition" in blocker for blocker in checked.blockers)


def test_review_round_trip_and_coverage_watermark():
    review = _review(
        (
            _decision(DECISION_NOT_MATERIAL),
            _decision(
                DECISION_REQUIRES_RECALCULATION,
                announcement_id="1225511493",
            ),
        )
    )
    restored = event_materiality_review_from_payload(review.as_policy())

    assert restored == review
    assert restored.coverage_watermark == MODEL_DATE
    assert restored.has_unresolved_recalculation is True
    assert restored.covers(MODEL_DATE) is True
    assert restored.covers(date(2026, 9, 23)) is False
