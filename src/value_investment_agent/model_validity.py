"""Determine whether an intrinsic-value model may be compared with a later quote."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
import re
from typing import Any

from .event_scan import (
    COVERAGE_COMPLETE,
    SCAN_COMPLETE_MATERIAL_EVENTS,
    SCAN_COMPLETE_NO_MATERIAL_EVENT,
    SCAN_PENDING_HUMAN_REVIEW,
    EventScanResult,
)
from .valuation_models.base import ValuationResult, merge_evidence_refs


VALIDITY_STATUSES = {"VALID", "STALE", "UNKNOWN", "INVALID"}


@dataclass(frozen=True)
class ModelValidity:
    model_id: str
    symbol: str
    model_as_of: date
    valid_from: date
    last_material_event_check: date | None
    financial_statement_changed: bool | None
    capital_structure_changed: bool | None
    material_event_found: bool | None
    status: str
    blockers: list[str]
    evidence_refs: list[dict[str, Any]]

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("Model validity requires a model identity")
        if not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("Model validity symbol must contain six digits")
        if self.status not in VALIDITY_STATUSES:
            raise ValueError("Unknown model validity status")
        if self.valid_from < self.model_as_of:
            raise ValueError("Model validity cannot begin before model as-of")
        if any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("Model validity evidence requires named references")
        if self.status == "VALID":
            if self.last_material_event_check is None:
                raise ValueError("VALID requires a material-event check date")
            if self.last_material_event_check < self.valid_from:
                raise ValueError("VALID event check cannot precede the validity window")
            if self.material_event_found is not False:
                raise ValueError("VALID requires a completed no-material-event check")
            if not self.evidence_refs:
                raise ValueError("VALID model validity requires evidence")
        if self.status == "STALE" and self.material_event_found is not True:
            raise ValueError("STALE requires a material event")

    def to_json(self) -> str:
        return json.dumps(
            asdict(self),
            ensure_ascii=False,
            default=lambda value: value.isoformat(),
            indent=2,
        )


@dataclass(frozen=True)
class MaterialEvent:
    event_date: date
    kind: str
    description: str
    evidence_refs: list[dict[str, Any]]
    material: bool = True

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.description.strip():
            raise ValueError("Material event kind and description are required")
        if not self.evidence_refs or any(not ref.get("id") for ref in self.evidence_refs):
            raise ValueError("Material event requires named evidence references")


def evaluate_model_validity(
    *,
    model_id: str,
    symbol: str,
    model_as_of: date,
    valid_from: date,
    quote_date: date,
    events: list[MaterialEvent],
    event_scan_evidence_refs: list[dict[str, Any]],
    blockers: list[str] | None = None,
    event_scan: EventScanResult | None = None,
) -> ModelValidity:
    """Evaluate whether a model remains valid at a later quote date."""
    base_blockers = list(blockers or [])
    if valid_from < model_as_of:
        raise ValueError("Model validity cannot begin before model as-of")
    if quote_date < valid_from:
        return ModelValidity(
            model_id,
            symbol,
            model_as_of,
            valid_from,
            None,
            None,
            None,
            None,
            "INVALID",
            base_blockers + ["quote date precedes model validity window"],
            [],
        )
    if event_scan is not None:
        if events:
            raise ValueError(
                "event_scan and legacy material events cannot both be supplied"
            )
        if event_scan.symbol != symbol:
            raise ValueError("event_scan symbol does not match the validity symbol")
        if event_scan.validity_from != valid_from:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "INVALID",
                base_blockers + ["event scan validity window starts on a different date"],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        if event_scan.scan_to < quote_date or event_scan.validity_to < quote_date:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "INVALID",
                base_blockers + ["event scan does not cover the quote date"],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        if event_scan.coverage_status != COVERAGE_COMPLETE:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "UNKNOWN",
                [*base_blockers, "event scan coverage is incomplete", *event_scan.blockers],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        if event_scan.status == SCAN_PENDING_HUMAN_REVIEW:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "UNKNOWN",
                [*base_blockers, "event scan is pending human review", *event_scan.blockers],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        scan_events = [
            MaterialEvent(
                event_date=item.published_at.date(),
                kind=item.rule_kind,
                description=item.title,
                evidence_refs=list(item.evidence_refs),
            )
            for item in event_scan.validity_material_candidates
        ]
        material_events = [
            event
            for event in scan_events
            if model_as_of <= event.event_date <= quote_date
        ]
        if event_scan.status == SCAN_COMPLETE_MATERIAL_EVENTS and not material_events:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "UNKNOWN",
                [*base_blockers, "event scan reports material events outside the model window"],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        if material_events:
            latest = max(event.event_date for event in material_events)
            financial_changed = any(
                event.kind in {"financial_statement", "financial_report"}
                for event in material_events
            )
            capital_changed = any(
                event.kind in {"capital_structure", "share_capital", "buyback"}
                for event in material_events
            )
            refs = merge_evidence_refs(
                event_scan_evidence_refs,
                event_scan.evidence_refs,
                *(event.evidence_refs for event in material_events),
            )
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                financial_changed,
                capital_changed,
                True,
                "STALE",
                [*base_blockers, f"material event at {latest.isoformat()}"],
                refs,
            )
        if event_scan.status != SCAN_COMPLETE_NO_MATERIAL_EVENT:
            return ModelValidity(
                model_id,
                symbol,
                model_as_of,
                valid_from,
                quote_date,
                None,
                None,
                None,
                "UNKNOWN",
                [*base_blockers, f"unknown event scan status: {event_scan.status}"],
                merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
            )
        return ModelValidity(
            model_id,
            symbol,
            model_as_of,
            valid_from,
            quote_date,
            False,
            False,
            False,
            "VALID",
            [*base_blockers, *event_scan.blockers],
            merge_evidence_refs(event_scan_evidence_refs, event_scan.evidence_refs),
        )
    material_events = [
        event
        for event in events
        if event.material and model_as_of <= event.event_date <= quote_date
    ]
    if material_events:
        latest = max(event.event_date for event in material_events)
        financial_changed = any(
            event.kind in {"financial_statement", "financial_report"}
            for event in material_events
        )
        capital_changed = any(
            event.kind in {"capital_structure", "share_capital", "buyback"}
            for event in material_events
        )
        refs = merge_evidence_refs(
            event_scan_evidence_refs,
            *(event.evidence_refs for event in material_events),
        )
        return ModelValidity(
            model_id,
            symbol,
            model_as_of,
            valid_from,
            quote_date,
            financial_changed,
            capital_changed,
            True,
            "STALE",
            base_blockers + [f"material event at {latest.isoformat()}"],
            refs,
        )
    if not event_scan_evidence_refs:
        return ModelValidity(
            model_id,
            symbol,
            model_as_of,
            valid_from,
            None,
            None,
            None,
            None,
            "UNKNOWN",
            base_blockers + ["material event scan evidence missing"],
            [],
        )
    return ModelValidity(
        model_id,
        symbol,
        model_as_of,
        valid_from,
        quote_date,
        False,
        False,
        False,
        "VALID",
        base_blockers,
        merge_evidence_refs(event_scan_evidence_refs),
    )


def _optional_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date string") from exc


def _required_date(value: object, field: str) -> date:
    parsed = _optional_date(value, field)
    if parsed is None:
        raise ValueError(f"{field} is required")
    return parsed


def model_validity_from_payload(payload: dict[str, Any]) -> ModelValidity:
    """Restore a model-validity record without accepting an identity label."""
    return ModelValidity(
        model_id=str(payload["model_id"]),
        symbol=str(payload["symbol"]),
        model_as_of=_required_date(payload["model_as_of"], "model_as_of"),
        valid_from=_required_date(payload["valid_from"], "valid_from"),
        last_material_event_check=_optional_date(
            payload.get("last_material_event_check"), "last_material_event_check"
        ),
        financial_statement_changed=payload.get("financial_statement_changed"),
        capital_structure_changed=payload.get("capital_structure_changed"),
        material_event_found=payload.get("material_event_found"),
        status=str(payload["status"]),
        blockers=list(payload["blockers"]),
        evidence_refs=list(payload["evidence_refs"]),
    )


def model_validity_identity_blockers(
    validity: ModelValidity,
    valuation: ValuationResult,
) -> list[str]:
    """Return blockers when a validity record is not bound to this valuation."""
    blockers: list[str] = []
    if validity.symbol != valuation.symbol:
        blockers.append("valuation and model validity symbols differ")
    if validity.model_as_of != valuation.valuation_date:
        blockers.append("model validity as-of does not match the valuation date")
    known_model_ids = {
        str(ref.get("sha256"))
        for ref in valuation.evidence_refs
        if ref.get("sha256")
    }
    known_model_ids.add(valuation.model_version)
    if validity.model_id not in known_model_ids:
        blockers.append("model validity does not match the valuation model snapshot")
    return blockers
