"""Fail-closed scheduling rules for scoped research evidence stops."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class EvidenceStop:
    stop_id: str
    symbol: str
    source_id: str
    period: str
    research_question_id: str
    blocker_id: str
    reviewed_evidence_ids: tuple[str, ...]
    reopen_condition: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.source_id.casefold(), self.period.casefold(),
            self.research_question_id.casefold(), self.blocker_id.casefold(),
        )


@dataclass(frozen=True)
class ResearchScheduleRequest:
    symbol: str
    source_id: str
    period: str
    research_question_id: str
    blocker_id: str
    reopen_condition_met: bool
    new_evidence_ids: tuple[str, ...]

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (
            self.source_id.casefold(), self.period.casefold(),
            self.research_question_id.casefold(), self.blocker_id.casefold(),
        )


def evidence_stops_from_payload(payload: Mapping[str, Any]) -> tuple[EvidenceStop, ...]:
    if payload.get("schema_version") != "research-evidence-stop-ledger-v1":
        raise ValueError("unsupported evidence-stop ledger schema")
    raw_stops = payload.get("stops")
    if not isinstance(raw_stops, list):
        raise ValueError("evidence-stop ledger must contain a stops list")
    stops: list[EvidenceStop] = []
    ids: set[str] = set()
    for raw in raw_stops:
        if not isinstance(raw, Mapping):
            raise ValueError("evidence-stop entry must be an object")
        fields = (
            "stop_id", "symbol", "source_id", "period",
            "research_question_id", "blocker_id", "reopen_condition",
        )
        values = {key: raw.get(key) for key in fields}
        if any(not isinstance(value, str) or not value.strip() for value in values.values()):
            raise ValueError("evidence-stop entry has an empty required field")
        symbol = values["symbol"].strip()
        if len(symbol) != 6 or not symbol.isdigit():
            raise ValueError("evidence-stop symbol must be a six-digit A-share code")
        stop_id = values["stop_id"].strip()
        if stop_id in ids:
            raise ValueError("evidence-stop ids must be unique")
        ids.add(stop_id)
        reviewed = raw.get("reviewed_evidence_ids")
        if not isinstance(reviewed, list) or any(
            not isinstance(item, str) or not item.strip() for item in reviewed
        ):
            raise ValueError("reviewed evidence ids must be a list of nonempty strings")
        if len(reviewed) != len(set(reviewed)):
            raise ValueError("reviewed evidence ids must be unique")
        stops.append(EvidenceStop(
            stop_id=stop_id,
            symbol=symbol,
            source_id=values["source_id"].strip(),
            period=values["period"].strip(),
            research_question_id=values["research_question_id"].strip(),
            blocker_id=values["blocker_id"].strip(),
            reviewed_evidence_ids=tuple(reviewed),
            reopen_condition=values["reopen_condition"].strip(),
        ))
    return tuple(stops)


def schedule_request_from_payload(payload: Mapping[str, Any]) -> ResearchScheduleRequest:
    if payload.get("schema_version") != "research-schedule-request-v1":
        raise ValueError("unsupported research schedule request schema")
    fields = (
        "symbol", "source_id", "period", "research_question_id", "blocker_id",
    )
    values = {key: payload.get(key) for key in fields}
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("research schedule request is missing its scoped key")
    symbol = values["symbol"].strip()
    if len(symbol) != 6 or not symbol.isdigit():
        raise ValueError("research schedule symbol must be a six-digit A-share code")
    condition_met = payload.get("reopen_condition_met", False)
    if not isinstance(condition_met, bool):
        raise ValueError("reopen_condition_met must be boolean")
    evidence_ids = payload.get("new_evidence_ids", [])
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) or not item.strip() for item in evidence_ids
    ):
        raise ValueError("new_evidence_ids must be a list of nonempty strings")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("new_evidence_ids must be unique")
    return ResearchScheduleRequest(
        symbol=symbol,
        source_id=values["source_id"].strip(),
        period=values["period"].strip(),
        research_question_id=values["research_question_id"].strip(),
        blocker_id=values["blocker_id"].strip(),
        reopen_condition_met=condition_met,
        new_evidence_ids=tuple(evidence_ids),
    )


def evaluate_research_schedule(
    *,
    symbol: str,
    stops: tuple[EvidenceStop, ...],
    request: ResearchScheduleRequest | None,
    verified_evidence_ids: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    active = tuple(stop for stop in stops if stop.symbol == symbol)
    if not active:
        return {
            "allowed": False,
            "status": "BLOCKED_NO_REGISTERED_SCOPE",
            "matched_stop_ids": [],
            "reason": "Research requires an explicitly registered trigger scope.",
        }
    if request is None:
        return {
            "allowed": False,
            "status": "BLOCKED_SCOPE_REQUIRED",
            "matched_stop_ids": [stop.stop_id for stop in active],
            "reopen_conditions": [
                {"stop_id": stop.stop_id, "condition": stop.reopen_condition}
                for stop in active
            ],
            "reason": "Active Evidence Stops require a scoped, evidence-bound research request.",
        }
    if request.symbol != symbol:
        return {
            "allowed": False,
            "status": "BLOCKED_SYMBOL_MISMATCH",
            "matched_stop_ids": [],
            "reason": "Schedule request symbol does not match the requested company.",
        }

    matching = tuple(stop for stop in active if stop.key == request.key)
    scope_key = {
        "source_id": request.source_id,
        "period": request.period,
        "research_question_id": request.research_question_id,
        "blocker_id": request.blocker_id,
    }
    if not matching:
        return {
            "allowed": False,
            "status": "BLOCKED_UNREGISTERED_SCOPE",
            "matched_stop_ids": [],
            "scope_key": scope_key,
            "active_stop_ids": [stop.stop_id for stop in active],
            "reason": "A new research scope requires its own registered event trigger.",
        }
    reviewed_ids = {
        evidence_id
        for stop in matching
        for evidence_id in stop.reviewed_evidence_ids
    }
    new_ids = tuple(
        evidence_id for evidence_id in request.new_evidence_ids
        if evidence_id not in reviewed_ids
    )
    unbound_ids = tuple(
        evidence_id for evidence_id in request.new_evidence_ids
        if evidence_id not in verified_evidence_ids
    )
    if not request.reopen_condition_met:
        return {
            "allowed": False,
            "status": "BLOCKED_REOPEN_CONDITION_FALSE",
            "matched_stop_ids": [stop.stop_id for stop in matching],
            "scope_key": scope_key,
            "reopen_conditions": [
                {"stop_id": stop.stop_id, "condition": stop.reopen_condition}
                for stop in matching
            ],
            "reason": "The registered reopen condition has not been established.",
        }
    if not new_ids:
        return {
            "allowed": False,
            "status": "BLOCKED_NO_NEW_EVIDENCE_ID",
            "matched_stop_ids": [stop.stop_id for stop in matching],
            "scope_key": scope_key,
            "reopen_conditions": [
                {"stop_id": stop.stop_id, "condition": stop.reopen_condition}
                for stop in matching
            ],
            "reason": "Reopening requires an evidence ID not already reviewed for this stop.",
        }
    if unbound_ids:
        return {
            "allowed": False,
            "status": "BLOCKED_UNBOUND_EVIDENCE_ID",
            "matched_stop_ids": [stop.stop_id for stop in matching],
            "scope_key": scope_key,
            "reopen_conditions": [
                {"stop_id": stop.stop_id, "condition": stop.reopen_condition}
                for stop in matching
            ],
            "new_evidence_ids": list(new_ids),
            "unbound_evidence_ids": list(unbound_ids),
            "reason": "Every new evidence ID must be present in the hash-bound package sources.",
        }
    return {
        "allowed": True,
        "status": "REOPENED_WITH_NEW_EVIDENCE",
        "matched_stop_ids": [stop.stop_id for stop in matching],
        "scope_key": scope_key,
        "reopen_conditions": [
            {"stop_id": stop.stop_id, "condition": stop.reopen_condition}
            for stop in matching
        ],
        "new_evidence_ids": list(new_ids),
    }
