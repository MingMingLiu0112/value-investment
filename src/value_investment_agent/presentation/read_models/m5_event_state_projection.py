"""Bounded M5 event-state projection for the product workbench."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .product_workbench import (
    ACTION_NO_ORDER,
    EVENT_CATEGORY_LABELS,
    RESEARCH_ACTION_LABELS,
    EventCard,
    EvidenceRecord,
    StatusView,
)

EventState = Literal[
    "material", "duplicate", "late", "correction", "nonmaterial",
    "insufficient_evidence", "model_unavailable",
]


@dataclass(frozen=True)
class EventStateInput:
    state: EventState
    event_id: str
    company_name: str
    what_happened: str
    impact_area: str
    evidence: tuple[EvidenceRecord, ...] = ()
    affects_research: bool = False
    affects_materiality: bool = False
    affects_dependencies: bool = False
    impact: bool = False
    canonical_event_id: str | None = None
    duplicate_event_id: str | None = None
    correction_of_event_id: str | None = None
    published_at: datetime | None = None
    observed_at: datetime | None = None
    previous_conclusion: str | None = None
    corrected_conclusion: str | None = None
    missing_evidence: str | None = None
    reopen_condition: str | None = None
    unavailable_reason: str | None = None
    model_requirements: str | None = None
    action: str = ACTION_NO_ORDER


@dataclass(frozen=True)
class EventAuditDecision:
    event_id: str
    state: EventState
    visible: bool
    disposition: str
    evidence_refs: tuple[str, ...]
    canonical_event_id: str | None = None
    duplicate_event_id: str | None = None
    correction_of_event_id: str | None = None
    published_at: datetime | None = None
    observed_at: datetime | None = None
    previous_conclusion: str | None = None
    corrected_conclusion: str | None = None
    action: str = ACTION_NO_ORDER


@dataclass(frozen=True)
class EventStateProjection:
    events: tuple[EventCard, ...]
    audit_evidence: tuple[EvidenceRecord, ...]
    audit_decisions: tuple[EventAuditDecision, ...]
    action: str = ACTION_NO_ORDER

    def as_payload(self) -> dict:
        return {
            "action": self.action,
            "events": [{
                "event_id": card.event_id,
                "event_type": card.category.code,
                "company_name": card.company_name,
                "what_happened": card.what_happened,
                "impact_area": card.impact_area,
                "current_conclusion": card.current_conclusion,
                "research_action": card.research_action.code,
                "next_step": card.next_step,
                "evidence_refs": list(card.evidence_refs),
                "action": card.action,
            } for card in self.events],
            "audit_evidence": [{
                "evidence_id": record.evidence_id, "title": record.title,
                "artifact_type": record.artifact_type, "path": record.path,
                "sha256": record.sha256,
                "available_at": record.available_at.isoformat() if record.available_at else None,
                "action": record.action,
            } for record in self.audit_evidence],
            "audit_decisions": [{
                "event_id": decision.event_id, "state": decision.state,
                "visible": decision.visible, "disposition": decision.disposition,
                "evidence_refs": list(decision.evidence_refs),
                "canonical_event_id": decision.canonical_event_id,
                "duplicate_event_id": decision.duplicate_event_id,
                "correction_of_event_id": decision.correction_of_event_id,
                "published_at": decision.published_at.isoformat() if decision.published_at else None,
                "observed_at": decision.observed_at.isoformat() if decision.observed_at else None,
                "previous_conclusion": decision.previous_conclusion,
                "corrected_conclusion": decision.corrected_conclusion,
                "action": decision.action,
            } for decision in self.audit_decisions],
        }


def _status(code: str, labels: dict[str, str]) -> StatusView:
    return StatusView(code=code, user_label=labels[code])


def project_m5_event_states(inputs: tuple[EventStateInput, ...]) -> EventStateProjection:
    """Project explicit upstream verdicts; never infer materiality or valuation."""
    cards: list[EventCard] = []
    evidence: dict[str, EvidenceRecord] = {}
    decisions: list[EventAuditDecision] = []
    seen_events: set[str] = set()
    for item in inputs:
        if item.action != ACTION_NO_ORDER:
            raise ValueError("Event projection must remain no_order")
        if not item.event_id or item.event_id in seen_events:
            raise ValueError("Event ids must be nonempty and unique")
        seen_events.add(item.event_id)
        if item.state not in EventState.__args__:
            raise ValueError("Unknown event state")
        if item.state == "duplicate" and (
            not item.canonical_event_id or not item.duplicate_event_id
            or item.canonical_event_id == item.duplicate_event_id
        ):
            raise ValueError("Duplicate requires distinct canonical and duplicate ids")
        if item.state == "late" and (
            item.published_at is None or item.observed_at is None
            or item.published_at.tzinfo is None or item.observed_at.tzinfo is None
            or item.observed_at <= item.published_at
        ):
            raise ValueError("Late event requires ordered timezone-aware source and observation times")
        if item.state == "correction" and (
            not item.correction_of_event_id or item.correction_of_event_id == item.event_id
            or not item.previous_conclusion or not item.corrected_conclusion
        ):
            raise ValueError("Correction requires prior event and both conclusions")
        if item.state == "insufficient_evidence" and (
            not item.missing_evidence or not item.reopen_condition
        ):
            raise ValueError("Missing evidence and reopen condition must be identified")
        if item.state == "model_unavailable" and (
            not item.unavailable_reason or not item.model_requirements
        ):
            raise ValueError("Unavailable model requires reason and requirements")

        refs = tuple(record.evidence_id for record in item.evidence)
        if item.state in {"material", "late", "correction"} and not refs:
            raise ValueError("Visible material, late or corrected event requires evidence lineage")
        if len(refs) != len(set(refs)):
            raise ValueError("Duplicate evidence ids within event")
        for record in item.evidence:
            if record.action != ACTION_NO_ORDER:
                raise ValueError("Evidence must remain no_order")
            if record.evidence_id in evidence and evidence[record.evidence_id] != record:
                raise ValueError("Conflicting evidence lineage")
            evidence[record.evidence_id] = record

        visible = (
            item.state in {"material", "insufficient_evidence", "model_unavailable"}
            or item.state == "late" and (
                item.affects_research or item.affects_materiality or item.affects_dependencies
            )
            or item.state == "correction" and item.impact
        )
        disposition = (
            "SUPPRESSED_DUPLICATE" if item.state == "duplicate"
            else "EVIDENCE_GAP" if item.state == "insufficient_evidence"
            else "MODEL_NOT_AVAILABLE" if item.state == "model_unavailable"
            else "USER_VISIBLE_EVENT" if visible else "AUDIT_ONLY"
        )
        decisions.append(EventAuditDecision(
            event_id=item.event_id, state=item.state, visible=visible,
            disposition=disposition,
            evidence_refs=refs, canonical_event_id=item.canonical_event_id,
            duplicate_event_id=item.duplicate_event_id,
            correction_of_event_id=item.correction_of_event_id,
            published_at=item.published_at, observed_at=item.observed_at,
            previous_conclusion=item.previous_conclusion,
            corrected_conclusion=item.corrected_conclusion,
        ))
        if not visible:
            continue
        category = {
            "material": "MATERIAL_REQUIRES_RECALCULATION",
            "late": "LATE_MATERIAL_INFORMATION",
            "correction": "CORRECTED_DISCLOSURE",
            "insufficient_evidence": "EVIDENCE_GAP",
            "model_unavailable": "MODEL_UNAVAILABLE",
        }[item.state]
        if item.state == "insufficient_evidence":
            conclusion = f"证据不足：{item.missing_evidence}；原研究结论不变"
            next_step = f"重开条件：{item.reopen_condition}"
        elif item.state == "model_unavailable":
            conclusion = f"暂不可评估；模型当前不可运行：{item.unavailable_reason}"
            next_step = f"需要：{item.model_requirements}"
        elif item.state == "correction":
            conclusion = f"原结论：{item.previous_conclusion}；更正后：{item.corrected_conclusion}；待复核"
            next_step = "复核更正原件及受影响的研究依赖"
        elif item.state == "late":
            conclusion = "晚到的重要信息；原研究结论尚未升级"
            next_step = "按原发布时间与实际发现时间复核受影响的研究"
        else:
            conclusion = "重大事件待复核；原研究结论尚未升级"
            next_step = "复核来源证据及受影响的研究依赖"
        happened = item.what_happened
        if item.state == "late":
            happened += f"（发布 {item.published_at.isoformat()}；发现 {item.observed_at.isoformat()}）"
        cards.append(EventCard(
            event_id=item.event_id,
            category=_status(category, EVENT_CATEGORY_LABELS),
            company_name=item.company_name,
            what_happened=happened,
            impact_area=item.impact_area,
            current_conclusion=conclusion,
            research_action=_status("REOPEN_RESEARCH" if item.state == "insufficient_evidence" else "PENDING_REVIEW", RESEARCH_ACTION_LABELS),
            next_step=next_step,
            evidence_refs=refs,
        ))
    return EventStateProjection(tuple(cards), tuple(evidence.values()), tuple(decisions))
