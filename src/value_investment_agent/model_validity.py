"""Determine whether an intrinsic-value model may be compared with a later quote."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from typing import Any


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
        if self.status not in VALIDITY_STATUSES:
            raise ValueError("Unknown model validity status")
        if self.valid_from < self.model_as_of:
            raise ValueError("Model validity cannot begin before model as-of")
        if self.status == "VALID":
            if self.last_material_event_check is None or self.material_event_found is not False:
                raise ValueError("VALID requires a completed no-material-event check")
            if not self.evidence_refs:
                raise ValueError("VALID model validity requires evidence")
        if self.status == "STALE" and self.material_event_found is not True:
            raise ValueError("STALE requires a material event")



    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, default=lambda value: value.isoformat(), indent=2)


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
) -> ModelValidity:
    """Evaluate whether a model remains valid at a later quote date."""
    base_blockers = list(blockers or [])
    if valid_from < model_as_of:
        raise ValueError("Model validity cannot begin before model as-of")
    if quote_date < valid_from:
        return ModelValidity(model_id, symbol, model_as_of, valid_from, None, None, None, None,
                             "INVALID", base_blockers + ["quote date precedes model validity window"], [])
    material_events = [
        event for event in events
        if event.material and model_as_of <= event.event_date <= quote_date
    ]
    if material_events:
        latest = max(event.event_date for event in material_events)
        financial_changed = any(event.kind in {"financial_statement", "financial_report"} for event in material_events)
        capital_changed = any(event.kind in {"capital_structure", "share_capital", "buyback"} for event in material_events)
        refs = [*event_scan_evidence_refs]
        for event in material_events:
            refs.extend(event.evidence_refs)
        return ModelValidity(model_id, symbol, model_as_of, valid_from, quote_date,
                             financial_changed, capital_changed, True, "STALE",
                             base_blockers + [f"material event at {latest.isoformat()}"],
                             refs)
    if not event_scan_evidence_refs:
        return ModelValidity(model_id, symbol, model_as_of, valid_from, None, None, None, None,
                             "UNKNOWN", base_blockers + ["material event scan evidence missing"], [])
    return ModelValidity(model_id, symbol, model_as_of, valid_from, quote_date,
                         False, False, False, "VALID", base_blockers, event_scan_evidence_refs)
