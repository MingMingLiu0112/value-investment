"""Point-in-time filtering for public-event projections."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any, Mapping


def _available_date(value: object) -> date:
    if not isinstance(value, str) or not value:
        raise ValueError("Public event evidence requires available_at")
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        timestamp = datetime.fromisoformat(value)
        if timestamp.utcoffset() is None:
            raise ValueError("available_at timestamp requires a timezone")
        return timestamp.date()
    except ValueError as error:
        raise ValueError("Public event available_at must be an ISO date or timestamp") from error


def project_public_event_projection_as_of(
    projection: Mapping[str, Any], cutoff: date,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    """Remove future evidence and any event or decision that depends on it."""
    if isinstance(cutoff, datetime) or not isinstance(cutoff, date):
        raise ValueError("Public event cutoff must be a date")

    result = deepcopy(dict(projection))
    evidence = result.get("audit_evidence")
    events = result.get("events")
    decisions = result.get("audit_decisions")
    if not isinstance(evidence, list) or not isinstance(events, list) or not isinstance(decisions, list):
        raise ValueError("Public event projection requires evidence, events and audit decisions")

    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    future_evidence: dict[str, Mapping[str, Any]] = {}
    for record in evidence:
        if not isinstance(record, Mapping):
            raise ValueError("Public event evidence records must be objects")
        evidence_id = record.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id or evidence_id in evidence_by_id:
            raise ValueError("Public event evidence ids must be nonempty and unique")
        evidence_by_id[evidence_id] = record
        if _available_date(record.get("available_at")) > cutoff:
            future_evidence[evidence_id] = record

    def refs_for(row: Mapping[str, Any], label: str) -> set[str]:
        refs = row.get("evidence_refs", [])
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError(f"{label} evidence_refs must be a list of ids")
        missing = set(refs) - evidence_by_id.keys()
        if missing:
            raise ValueError(f"{label} references missing evidence: {sorted(missing)}")
        return set(refs)

    excluded_events: set[str] = set()
    event_ids: set[str] = set()
    future_event_ids: dict[str, set[str]] = {evidence_id: set() for evidence_id in future_evidence}
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("Public event cards must be objects")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            raise ValueError("Public event ids must be nonempty and unique")
        event_ids.add(event_id)
        future_refs = refs_for(event, "Public event") & future_evidence.keys()
        if future_refs:
            excluded_events.add(event_id)
            for evidence_id in future_refs:
                future_event_ids[evidence_id].add(event_id)

    decision_ids: set[str] = set()
    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise ValueError("Public event audit decisions must be objects")
        event_id = decision.get("event_id")
        if not isinstance(event_id, str) or not event_id or event_id in decision_ids:
            raise ValueError("Public event decision ids must be nonempty and unique")
        decision_ids.add(event_id)
        refs = refs_for(decision, "Public event decision")
        future_refs = refs & future_evidence.keys()
        if future_refs:
            excluded_events.add(event_id)
            for evidence_id in future_refs:
                future_event_ids[evidence_id].add(event_id)

    filtered_events = [row for row in events if row["event_id"] not in excluded_events]
    filtered_decisions = [row for row in decisions if row["event_id"] not in excluded_events]

    result["events"] = filtered_events
    result["audit_decisions"] = filtered_decisions
    result["audit_evidence"] = [
        record for evidence_id, record in evidence_by_id.items()
        if evidence_id not in future_evidence
    ]

    exclusions = tuple({
        "evidence_id": evidence_id,
        "available_at": record["available_at"],
        "event_ids": sorted(future_event_ids[evidence_id]),
        "reason": "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF",
    } for evidence_id, record in future_evidence.items())
    return result, exclusions
