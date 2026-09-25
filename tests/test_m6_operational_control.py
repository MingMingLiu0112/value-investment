from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import multiprocessing
from pathlib import Path

import pytest

from value_investment_agent.m6_operational_control import (
    ACTION_NO_ORDER,
    MODE_LIMITED_USE,
    MODE_OFFLINE_ENGINEERING,
    MODE_SHADOW,
    MODE_STAGING,
    MODE_STOPPED,
    OperationalAuthorizationProof,
    apply_emergency_stop,
    control_state_lock,
    from_dict,
    initial_state,
    read_control_state,
    transition,
    write_control_state,
)


def _now(hour: int = 10) -> datetime:
    return datetime(2026, 9, 24, hour, 0, tzinfo=timezone.utc)


def _proof(
    target_mode: str,
    *,
    authorization_id: str | None = None,
    operator_id: str = "operator",
    verified_at: datetime | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    digest: str | None = None,
) -> OperationalAuthorizationProof:
    authorization_id = authorization_id or f"auth-{target_mode.lower()}"
    if digest is None:
        digest = hashlib.sha256(
            f"{authorization_id}:{target_mode}".encode("ascii")
        ).hexdigest()
    return OperationalAuthorizationProof._issue(
        authorization_id=authorization_id,
        authorization_sha256=digest,
        authorization_mode=MODE_SHADOW,
        target_mode=target_mode,
        operator_id=operator_id,
        venue="SSE",
        valid_from=valid_from or datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc),
        valid_until=valid_until or datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc),
        verified_at=verified_at or _now(9),
    )


def _hold_control_lock(path: str, entered, release) -> None:
    with control_state_lock(Path(path)):
        entered.set()
        if not release.wait(10):
            raise TimeoutError("lock holder release timeout")


def _acquire_control_lock(path: str, entered) -> None:
    with control_state_lock(Path(path)):
        entered.set()


def test_initial_state_and_round_trip_are_fail_closed(tmp_path):
    state = initial_state(operator_id="codex", now=_now())
    assert state.mode == MODE_OFFLINE_ENGINEERING
    assert state.publish_allowed is False
    assert state.new_review_allowed is False
    assert state.source_read_allowed is True
    assert state.action == ACTION_NO_ORDER
    assert state.authorization_sha256 == ""

    path = tmp_path / "state.json"
    write_control_state(path, state)
    restored = read_control_state(path)
    assert restored.as_dict() == state.as_dict()


def test_staged_progression_requires_verified_proof_and_sequential_modes():
    state = initial_state(operator_id="operator", now=_now(9))
    with pytest.raises(ValueError, match="one stage at a time"):
        transition(
            state,
            target_mode=MODE_SHADOW,
            authorization=_proof(MODE_SHADOW, authorization_id="skip-shadow"),
            reason="skip staging",
            operator_id="operator",
            changed_at=_now(10),
        )

    with pytest.raises(ValueError, match="verifier-issued authorization proof"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization=None,
            reason="missing authorization",
            operator_id="operator",
            changed_at=_now(10),
        )

    staging_proof = _proof(MODE_STAGING, authorization_id="auth-staging")
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=staging_proof,
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    assert staging.new_review_allowed is True
    assert staging.publish_allowed is False
    assert staging.authorization_id == "auth-staging"
    assert staging.authorization_sha256 == staging_proof.authorization_sha256

    shadow = transition(
        staging,
        target_mode=MODE_SHADOW,
        authorization=_proof(MODE_SHADOW, authorization_id="auth-shadow"),
        reason="approved shadow",
        operator_id="operator",
        changed_at=_now(11),
    )
    assert shadow.mode == MODE_SHADOW
    assert shadow.publish_allowed is False
    assert len(shadow.history) == 2

    with pytest.raises(ValueError, match="limited use"):
        transition(
            shadow,
            target_mode=MODE_LIMITED_USE,
            authorization=None,
            reason="limited use must remain disabled",
            operator_id="operator",
            changed_at=_now(12),
        )
    with pytest.raises(ValueError, match="target mode is not enabled"):
        _proof(MODE_LIMITED_USE, authorization_id="auth-limited")


def test_transition_rejects_bare_authorization_id_and_mismatched_proofs():
    state = initial_state(operator_id="operator", now=_now(9))

    with pytest.raises(ValueError, match="verifier-issued authorization proof"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization="auth-fabricated",
            reason="fabricated string",
            operator_id="operator",
            changed_at=_now(10),
        )

    with pytest.raises(ValueError, match="target mode"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization=_proof(MODE_SHADOW),
            reason="wrong target",
            operator_id="operator",
            changed_at=_now(10),
        )

    with pytest.raises(ValueError, match="operator"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization=_proof(MODE_STAGING, operator_id="other-operator"),
            reason="wrong operator",
            operator_id="operator",
            changed_at=_now(10),
        )

    with pytest.raises(ValueError, match="validity window"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization=_proof(
                MODE_STAGING,
                valid_from=_now(8),
                valid_until=_now(9),
            ),
            reason="expired proof",
            operator_id="operator",
            changed_at=_now(10),
        )


def test_transition_rejects_proof_verified_after_change():
    state = initial_state(operator_id="operator", now=_now(9))
    with pytest.raises(ValueError, match="before verification"):
        transition(
            state,
            target_mode=MODE_STAGING,
            authorization=_proof(MODE_STAGING, verified_at=_now(11)),
            reason="future verification",
            operator_id="operator",
            changed_at=_now(10),
        )


def test_transition_requires_forward_time_and_a_mode_change():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )

    with pytest.raises(ValueError, match="strictly forward"):
        transition(
            staging,
            target_mode=MODE_SHADOW,
            authorization=_proof(MODE_SHADOW, authorization_id="auth-shadow"),
            reason="backward clock",
            operator_id="operator",
            changed_at=_now(9),
        )
    with pytest.raises(ValueError, match="must alter the mode"):
        transition(
            staging,
            target_mode=MODE_STAGING,
            authorization=_proof(MODE_STAGING, authorization_id="auth-staging-2"),
            reason="same mode",
            operator_id="operator",
            changed_at=_now(11),
        )


def test_emergency_stop_is_always_allowed_and_blocks_publication():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
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
    assert stopped.history[-1].authorization_sha256 == staging.authorization_sha256

    with pytest.raises(ValueError, match="new authorization"):
        transition(
            stopped,
            target_mode=MODE_STAGING,
            authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
            reason="restart with old authorization",
            operator_id="operator",
            changed_at=_now(12),
        )


def test_repeated_emergency_stop_is_idempotent():
    state = initial_state(operator_id="operator", now=_now(9))
    stopped = apply_emergency_stop(
        state,
        reason="critical data defect",
        operator_id="oncall",
        changed_at=_now(10),
    )
    repeated = apply_emergency_stop(
        stopped,
        reason="duplicate alert",
        operator_id="second-oncall",
        changed_at=_now(11),
    )

    assert repeated.as_dict() == stopped.as_dict()
    assert len(repeated.history) == 1


def test_control_state_lock_serializes_separate_processes(tmp_path):
    context = multiprocessing.get_context("spawn")
    path = tmp_path / "state.json"
    holder_entered = context.Event()
    holder_release = context.Event()
    contender_entered = context.Event()
    holder = context.Process(
        target=_hold_control_lock,
        args=(str(path), holder_entered, holder_release),
    )
    contender = None
    try:
        holder.start()
        assert holder_entered.wait(5)
        contender = context.Process(
            target=_acquire_control_lock,
            args=(str(path), contender_entered),
        )
        contender.start()
        assert not contender_entered.wait(0.25)
        holder_release.set()
        assert contender_entered.wait(5)
        holder.join(5)
        contender.join(5)
        assert holder.exitcode == 0
        assert contender.exitcode == 0
    finally:
        holder_release.set()
        for process in (holder, contender):
            if process is not None and process.is_alive():
                process.terminate()
                process.join(5)


def test_emergency_stop_can_only_reset_to_offline_engineering():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
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
            authorization=_proof(MODE_STAGING, authorization_id="auth-reset"),
            reason="attempt direct staging restart",
            operator_id="operator",
            changed_at=_now(12),
        )

    reset_proof = _proof(MODE_OFFLINE_ENGINEERING, authorization_id="auth-reset")
    reset = transition(
        stopped,
        target_mode=MODE_OFFLINE_ENGINEERING,
        authorization=reset_proof,
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
    assert reset.authorization_sha256 == reset_proof.authorization_sha256


def test_deserialization_rejects_inconsistent_permissions():
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
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    payload = staging.as_dict()
    payload["reason"] = "tampered snapshot reason"

    with pytest.raises(ValueError, match="snapshot does not match its history"):
        from_dict(payload)


def test_deserialization_rejects_history_hash_tampering():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    payload = staging.as_dict()
    payload["authorization_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="snapshot does not match its history"):
        from_dict(payload)


def test_deserialization_rejects_non_contiguous_history_chain():
    state = initial_state(operator_id="operator", now=_now(9))
    staging = transition(
        state,
        target_mode=MODE_STAGING,
        authorization=_proof(MODE_STAGING, authorization_id="auth-staging"),
        reason="approved staging",
        operator_id="operator",
        changed_at=_now(10),
    )
    shadow = transition(
        staging,
        target_mode=MODE_SHADOW,
        authorization=_proof(MODE_SHADOW, authorization_id="auth-shadow"),
        reason="approved shadow",
        operator_id="operator",
        changed_at=_now(11),
    )
    payload = shadow.as_dict()
    payload["history"][0]["from_mode"] = MODE_SHADOW

    with pytest.raises(ValueError, match="not contiguous"):
        from_dict(payload)
