from dataclasses import replace
from datetime import datetime

import pytest

from value_investment_agent.presentation.read_models.m5_event_state_projection import (
    EventStateInput,
    project_m5_event_states,
)
from value_investment_agent.presentation.read_models.product_workbench import EvidenceRecord


SOURCE = EvidenceRecord(
    evidence_id="source-1", title="Synthetic source", artifact_type="event_source",
    path="fixtures/synthetic-source.json", sha256="a" * 64,
)


def event(state: str, **changes) -> EventStateInput:
    return replace(EventStateInput(
        state=state, event_id="event-1", company_name="Synthetic Company",
        what_happened="A synthetic event occurred", impact_area="Research",
        evidence=(SOURCE,),
        published_at=datetime.fromisoformat("2026-09-24T09:00:00+08:00"),
        observed_at=datetime.fromisoformat("2026-09-24T10:00:00+08:00"),
        previous_conclusion="原研究待证据", corrected_conclusion="更正后仍待证据",
        reopen_condition="取得已核原件",
    ), **changes)


def test_material_visible_with_lineage_and_no_order():
    result = project_m5_event_states((event("material"),))
    assert len(result.events) == 1
    assert result.events[0].evidence_refs == (SOURCE.evidence_id,)
    assert result.audit_evidence == (SOURCE,)
    assert result.action == result.events[0].action == "no_order"
    with pytest.raises(ValueError, match="lineage"):
        project_m5_event_states((event("material", evidence=()),))


def test_duplicate_suppressed_with_both_ids_in_audit():
    result = project_m5_event_states((event(
        "duplicate", canonical_event_id="canonical", duplicate_event_id="duplicate",
    ),))
    assert result.events == ()
    assert (result.audit_decisions[0].canonical_event_id,
            result.audit_decisions[0].duplicate_event_id) == ("canonical", "duplicate")


def test_late_only_visible_when_impact_is_explicit():
    for field in ("affects_research", "affects_materiality", "affects_dependencies"):
        assert len(project_m5_event_states((event("late", **{field: True}),)).events) == 1
    result = project_m5_event_states((event("late"),))
    assert result.events == ()
    assert result.audit_decisions[0].visible is False


def test_correction_is_append_only_and_visible_only_with_impact():
    quiet = project_m5_event_states((event("correction", correction_of_event_id="original"),))
    active = project_m5_event_states((event("correction", correction_of_event_id="original", impact=True),))
    assert quiet.events == ()
    assert active.events[0].event_id == "event-1"
    assert active.audit_decisions[0].correction_of_event_id == "original"


def test_nonmaterial_audit_only():
    result = project_m5_event_states((event("nonmaterial"),))
    assert result.events == ()
    assert result.audit_evidence == (SOURCE,)


def test_insufficient_evidence_reopens_without_promotion():
    result = project_m5_event_states((event(
        "insufficient_evidence", evidence=(), missing_evidence="filing receipt",
    ),))
    card = result.events[0]
    assert card.research_action.code == "REOPEN_RESEARCH"
    assert "取得已核原件" in card.next_step
    assert "原研究结论不变" in card.current_conclusion
    assert result.audit_evidence == ()


def test_model_unavailable_has_reason_requirements_and_no_numeric_value():
    result = project_m5_event_states((event(
        "model_unavailable", evidence=(), unavailable_reason="inputs incomplete",
        model_requirements="verified cash flows",
    ),))
    card = result.events[0]
    assert "inputs incomplete" in card.current_conclusion
    assert "verified cash flows" in card.next_step
    assert "暂不可评估" in card.current_conclusion
    assert card.action == "no_order"
