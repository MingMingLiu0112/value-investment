from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime

import pytest

from value_investment_agent.application.product.public_event_projection import (
    project_public_event_projection_as_of,
)


def _projection(available_at: str = "2026-09-29") -> dict:
    return {
        "action": "no_order",
        "events": [{"event_id": "midea-egm", "evidence_refs": ["notice"]}],
        "audit_evidence": [{"evidence_id": "notice", "available_at": available_at}],
        "audit_decisions": [{
            "event_id": "midea-egm", "visible": True,
            "evidence_refs": ["notice"], "action": "no_order",
        }],
    }


def test_future_available_event_and_evidence_are_excluded_without_mutating_source():
    source = _projection()
    original = deepcopy(source)

    result, exclusions = project_public_event_projection_as_of(
        source, date(2026, 9, 28),
    )

    assert source == original
    assert result["events"] == []
    assert result["audit_decisions"] == []
    assert result["audit_evidence"] == []
    assert exclusions == ({
        "evidence_id": "notice",
        "available_at": "2026-09-29",
        "event_ids": ["midea-egm"],
        "reason": "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF",
    },)


def test_evidence_available_on_cutoff_remains_visible():
    result, exclusions = project_public_event_projection_as_of(
        _projection("2026-09-28"), date(2026, 9, 28),
    )

    assert len(result["events"]) == 1
    assert len(result["audit_decisions"]) == 1
    assert len(result["audit_evidence"]) == 1
    assert exclusions == ()


def test_future_evidence_referenced_only_by_decision_hides_its_event_card():
    projection = _projection("2026-09-28")
    projection["audit_evidence"].append({
        "evidence_id": "late-correction", "available_at": "2026-09-29",
    })
    projection["audit_decisions"][0]["evidence_refs"] = ["late-correction"]

    result, exclusions = project_public_event_projection_as_of(
        projection, date(2026, 9, 28),
    )

    assert result["events"] == []
    assert result["audit_decisions"] == []
    assert result["audit_evidence"] == [projection["audit_evidence"][0]]
    assert exclusions[0]["event_ids"] == ["midea-egm"]


@pytest.mark.parametrize("available_at", [None, "not-a-date", "2026-09-28T12:00:00"])
def test_missing_or_unqualified_availability_fails_closed(available_at):
    projection = _projection()
    projection["audit_evidence"][0]["available_at"] = available_at

    with pytest.raises(ValueError, match="available_at"):
        project_public_event_projection_as_of(projection, date(2026, 9, 28))


def test_dangling_event_evidence_reference_fails_closed():
    projection = _projection()
    projection["events"][0]["evidence_refs"] = ["missing"]

    with pytest.raises(ValueError, match="missing evidence"):
        project_public_event_projection_as_of(projection, date(2026, 9, 28))


def test_cutoff_rejects_datetime_to_keep_the_boundary_date_explicit():
    with pytest.raises(ValueError, match="cutoff must be a date"):
        project_public_event_projection_as_of(_projection(), datetime(2026, 9, 28))
