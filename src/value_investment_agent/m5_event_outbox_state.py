"""Application helpers for durable M5 outbox status transitions."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .m5_event_outbox import (
    ALERT_ACKNOWLEDGED,
    ALERT_DELIVERED,
    ALERT_FAILED_RETRYABLE,
    ALERT_FAILED_TERMINAL,
    ALERT_SENT,
)
from .m5_event_outbox_transition import (
    OutboxTransitionRecord,
    alert_by_id,
)
from .m5_event_run_state import M5EventRunState


def apply_outbox_transition(
    *,
    state: M5EventRunState,
    alert_id: str,
    from_status: str,
    to_status: str,
    occurred_at: datetime,
    error: str | None = None,
) -> M5EventRunState:
    """Return a successor state with one persisted outbox transition.

    Repeating the exact request is an idempotent clone. This function never
    sends a notification; callers record the transport outcome explicitly.
    """
    if not isinstance(state, M5EventRunState):
        raise ValueError("state must be an M5EventRunState")
    next_revision = state.outbox_revision + 1
    requested = OutboxTransitionRecord(
        outbox_revision=next_revision,
        alert_id=alert_id,
        from_status=from_status,
        to_status=to_status,
        occurred_at=occurred_at,
        error=error,
    )
    existing = next(
        (
            item
            for item in state.outbox_transitions
            if item.transition_id == requested.transition_id
        ),
        None,
    )
    if existing is not None:
        if (
            existing.alert_id != requested.alert_id
            or existing.from_status != requested.from_status
            or existing.to_status != requested.to_status
            or existing.occurred_at != requested.occurred_at
            or existing.error != requested.error
            or existing.action != requested.action
        ):
            raise ValueError("Outbox transition id was reused with different inputs")
        return state.clone()

    current_alert = alert_by_id(state.outbox, alert_id)
    if current_alert.status != from_status:
        raise ValueError("Outbox transition from_status does not match current alert")

    candidate = state.clone()
    if to_status == ALERT_SENT:
        updated = candidate.outbox.mark_sent(alert_id=alert_id, now=occurred_at)
    elif to_status == ALERT_DELIVERED:
        updated = candidate.outbox.mark_delivered(
            alert_id=alert_id,
            now=occurred_at,
        )
    elif to_status == ALERT_ACKNOWLEDGED:
        updated = candidate.outbox.mark_acknowledged(
            alert_id=alert_id,
            now=occurred_at,
        )
    elif to_status in {ALERT_FAILED_RETRYABLE, ALERT_FAILED_TERMINAL}:
        if error is None:
            raise ValueError("Failed outbox transition requires an error")
        updated = candidate.outbox.mark_failed(
            alert_id=alert_id,
            now=occurred_at,
            error=error,
            terminal=to_status == ALERT_FAILED_TERMINAL,
        )
    else:
        raise ValueError("Unsupported outbox transition")
    if updated.status != to_status:
        raise ValueError("Outbox transition produced a different status")

    return replace(
        candidate,
        outbox_revision=next_revision,
        outbox_transitions=state.outbox_transitions + (requested,),
    )
