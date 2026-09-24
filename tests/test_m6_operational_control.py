from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from value_investment_agent.m6_operational_control import (
    ACTION_NO_ORDER,
    MODE_LIMITED_USE,
    MODE_OFFLINE_ENGINEERING,
    MODE_SHADOW,
    MODE_STAGING,
    MODE_STOPPED,
    apply_emergency_stop,
    from_dict,
    initial_state,
    read_control_state,
    transition,
    write_control_state,
)


def _now(hour: int = 10) -> datetime:
    return datetime(2026, 9, 24, hour, 0, tzinfo=timezone.utc)


def test_initial_state_and_round_trip_are_fail_closed(tmp_path):
    state = initial_state(operator_id="codex", now=_now())
    assert state.mode == MODE_OFFLINE_ENGINEERING
    assert state.publish_allowed is False
    assert state.new_review_allowed is False
    assert state.source_read_allowed is True
    assert state.action == ACTION_NO_ORDER

    path = tmp_path / "state.json"
    write_control_state(path, state)
    restored = read_control_state(path)
    assert restored.as_dict() == state.as_dict()


def test_staged_progression_requires_authorization_and_sequential_modes(tmp_path):
    state = initial_state(operator_id="operator", now=_now(9))
    with pytest.raises(ValueError, match="one stage at a time"):
        transition(
            state,
            target_mode=MODE_SHADOW,
            authorization_id="auth-shadow",
            reason="skip staging",
            operator_id="operator",
            changed_at=_now(10),
        )

    with pytest.raises(ValueError, match="authorization id"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization_id="",
            reason="missing authorization",
            operator_id="operator",
            changed_at=_now(10),
        )

    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    assert staging.new_review_allowed is True
    assert staging.publish_allowed is False

    shadow = transition(
        staging,
        target_mode=MODE_SHADOW,
        authorization_id="auth-shadow",
        reason="approved shadow",
        operator_id="operator",
        changed_at=_now(11),
    )
    limited = transition(
        shadow,
        target_mode=MODE_LIMITED_USE,
        authorization_id="auth-limited",
        reason="approved limited use",
        operator_id="operator",
        changed_at=_now(12),
    )
    assert limited.mode == MODE_LIMITED_USE
    assert limited.publish_allowed is True
    assert len(limited.history) == 3


def test_transition_requires_forward_time_and_a_mode_change():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )

    with pytest.raises(ValueError, match="strictly forward"):
        transition(
            staging,
            target_mode=MODE_SHADOW,
            authorization_id="auth-shadow",
            reason="backward clock",
            operator_id="operator",
            changed_at=_now(9),
        )
    with pytest.raises(ValueError, match="must alter the mode"):
        transition(
            staging,
            target_mode=MODE_STAGING,
            authorization_id="auth-staging-2",
            reason="same mode",
            operator_id="operator",
            changed_at=_now(11),
        )


def test_emergency_stop_is_always_allowed_and_blocks_publication(tmp_path):
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    stopped = apply_emergency_stop(
        staging,
        reason="critical data defect",
        operator_id="oncall",
        changed_at=_now(11),
    )
    assert stopped.mode == MODE_STOPPED
    assert stopped.publish_allowed is False
    assert stopped.new_review_allowed is False
    assert stopped.source_read_allowed is True
    assert stopped.history[-1].to_mode == MODE_STOPPED
    assert stopped.history[-1].authorization_id == "auth-staging"

    with pytest.raises(ValueError, match="new authorization id"):
        transition(
            stopped,
            target_mode=MODE_STAGING,
            authorization_id=stopped.authorization_id,
            reason="attempt reuse",
            operator_id="operator",
            changed_at=_now(12),
        )


def test_emergency_stop_can_only_reset_to_offline_engineering(tmp_path):
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    stopped = apply_emergency_stop(
        staging,
        reason="critical data defect",
        operator_id="oncall",
        changed_at=_now(11),
    )

    with pytest.raises(ValueError, match="return to offline engineering"):
        transition(
            stopped,
            target_mode=MODE_STAGING,
            authorization_id="auth-reset",
            reason="attempt direct staging restart",
            operator_id="operator",
            changed_at=_now(12),
        )

    reset = transition(
        stopped,
        target_mode=MODE_OFFLINE_ENGINEERING,
        authorization_id="auth-reset",
        reason="authorized reset to offline",
        operator_id="operator",
        changed_at=_now(12),
    )
    assert reset.mode == MODE_OFFLINE_ENGINEERING
    assert reset.publish_allowed is False
    assert reset.new_review_allowed is False
    assert reset.source_read_allowed is True
    assert reset.history[-1].from_mode == MODE_STOPPED
    assert reset.history[-1].to_mode == MODE_OFFLINE_ENGINEERING


def test_deserialization_rejects_inconsistent_permissions(tmp_path):
    state = initial_state(operator_id="operator", now=_now())
    payload = state.as_dict()
    payload["mode"] = MODE_STOPPED
    payload["permissions"]["publish_allowed"] = True
    with pytest.raises(ValueError, match="permissions"):
        from_dict(payload)


def test_deserialization_rejects_non_boolean_permissions():
    state = initial_state(operator_id="operator", now=_now())
    payload = state.as_dict()
    payload["permissions"]["publish_allowed"] = "false"

    with pytest.raises(ValueError, match="must be boolean"):
        from_dict(payload)


def test_deserialization_rejects_history_snapshot_mismatch():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    payload = staging.as_dict()
    payload["reason"] = "tampered snapshot reason"

    with pytest.raises(ValueError, match="snapshot does not match its history"):
        from_dict(payload)


def test_deserialization_rejects_non_contiguous_history_chain():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization_id="auth-staging",
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    shadow = transition(
        staging,
        target_mode=MODE_SHADOW,
        authorization_id="auth-shadow",
        reason="approved shadow",
        operator_id="operator",
        changed_at=_now(11),
    )
    payload = shadow.as_dict()
    payload["history"][0]["from_mode"] = MODE_SHADOW

    with pytest.raises(ValueError, match="not contiguous"):
        from_dict(payload)
