"""Versioned operational control and emergency-stop contract for M6.

This module is an offline policy engine. It records the allowed
staging/shadow/limited-use mode and provides an atomic emergency-stop state
without connecting to production, publishing a workbook or creating an order.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
import tempfile
from typing import Any, Iterator, Mapping


SCHEMA_VERSION = "m6-operational-control-v1"
ACTION_NO_ORDER = "no_order"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

MODE_OFFLINE_ENGINEERING = "OFFLINE_ENGINEERING"
MODE_STAGING = "STAGING"
MODE_SHADOW = "SHADOW"
MODE_LIMITED_USE = "LIMITED_USE"
MODE_STOPPED = "STOPPED"
MODES = frozenset(
    {
        MODE_OFFLINE_ENGINEERING,
        MODE_STAGING,
        MODE_SHADOW,
        MODE_LIMITED_USE,
        MODE_STOPPED,
    }
)

_MODE_ORDER = {
    MODE_OFFLINE_ENGINEERING: 0,
    MODE_STAGING: 1,
    MODE_SHADOW: 2,
    MODE_LIMITED_USE: 3,
}

_AUTHORIZATION_PROOF_TARGET_MODES = frozenset(
    {MODE_OFFLINE_ENGINEERING, MODE_STAGING, MODE_SHADOW}
)


@dataclass(frozen=True)
class ModeChange:
    from_mode: str
    to_mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str
    authorization_sha256: str

    def __post_init__(self) -> None:
        if self.from_mode not in MODES or self.to_mode not in MODES:
            raise ValueError("unknown operational mode")
        if self.from_mode == self.to_mode:
            raise ValueError("operational mode change must alter the mode")
        if self.changed_at.tzinfo is None:
            raise ValueError("operational control timestamp must be timezone-aware")
        if not self.reason.strip() or not self.operator_id.strip():
            raise ValueError("operational control reason and operator are required")
        if self.to_mode not in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED}:
            if not self.authorization_id.strip():
                raise ValueError("production mode transition requires an authorization id")
            if not _SHA256.fullmatch(self.authorization_sha256):
                raise ValueError("production mode transition requires an authorization hash")
        elif self.authorization_id or self.authorization_sha256:
            if not self.authorization_id.strip() or not _SHA256.fullmatch(self.authorization_sha256):
                raise ValueError("authorization id and hash must be supplied together")


@dataclass(frozen=True)
class OperationalControlState:
    mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str
    authorization_sha256: str
    publish_allowed: bool
    new_review_allowed: bool
    source_read_allowed: bool
    history: tuple[ModeChange, ...]
    schema_version: str = SCHEMA_VERSION
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported operational control schema")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("operational control must remain no_order")
        if self.mode not in MODES:
            raise ValueError(f"unknown operational mode: {self.mode}")
        if self.changed_at.tzinfo is None:
            raise ValueError("operational control timestamp must be timezone-aware")
        if not self.reason.strip() or not self.operator_id.strip():
            raise ValueError("operational control reason and operator are required")
        if self.mode not in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED}:
            if not self.authorization_id.strip():
                raise ValueError("production mode transition requires an authorization id")
            if not _SHA256.fullmatch(self.authorization_sha256):
                raise ValueError("production mode transition requires an authorization hash")
        elif self.authorization_id or self.authorization_sha256:
            if not self.authorization_id.strip() or not _SHA256.fullmatch(self.authorization_sha256):
                raise ValueError("authorization id and hash must be supplied together")
        expected_permissions = _permissions_for(self.mode)
        actual_permissions = (
            self.publish_allowed,
            self.new_review_allowed,
            self.source_read_allowed,
        )
        if actual_permissions != expected_permissions:
            raise ValueError("operational permissions do not match the current mode")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "mode": self.mode,
            "changed_at": self.changed_at.isoformat(),
            "reason": self.reason,
            "operator_id": self.operator_id,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256,
            "permissions": {
                "publish_allowed": self.publish_allowed,
                "new_review_allowed": self.new_review_allowed,
                "source_read_allowed": self.source_read_allowed,
            },
            "history": [
                {
                    "from_mode": item.from_mode,
                    "to_mode": item.to_mode,
                    "changed_at": item.changed_at.isoformat(),
                    "reason": item.reason,
                    "operator_id": item.operator_id,
                    "authorization_id": item.authorization_id,
                    "authorization_sha256": item.authorization_sha256,
                }
                for item in self.history
            ],
        }


def initial_state(*, operator_id: str, now: datetime | None = None) -> OperationalControlState:
    changed_at = now or datetime.now(timezone.utc)
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=timezone.utc)
    return OperationalControlState(
        mode=MODE_OFFLINE_ENGINEERING,
        changed_at=changed_at,
        reason="offline engineering baseline",
        operator_id=operator_id,
        authorization_id="",
        authorization_sha256="",
        publish_allowed=False,
        new_review_allowed=False,
        source_read_allowed=True,
        history=(),
    )


def _permissions_for(mode: str) -> tuple[bool, bool, bool]:
    if mode == MODE_STOPPED:
        return False, False, True
    if mode == MODE_OFFLINE_ENGINEERING:
        return False, False, True
    if mode == MODE_STAGING:
        return False, True, True
    if mode == MODE_SHADOW:
        return False, True, True
    if mode == MODE_LIMITED_USE:
        return True, True, True
    raise ValueError(f"unknown operational mode: {mode}")


@dataclass(frozen=True, init=False)
class OperationalAuthorizationProof:
    """A verifier-issued proof that a signed authorization was accepted.

    The public constructor is deliberately disabled. Only the signed
    authorization verifier should call ``_issue`` after signature, external
    hash, scope-artifact and validity checks.
    """

    authorization_id: str
    authorization_sha256: str
    authorization_mode: str
    target_mode: str
    operator_id: str
    venue: str
    valid_from: datetime
    valid_until: datetime
    verified_at: datetime
    action: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "operational authorization proof must be issued by the signed verifier"
        )

    @classmethod
    def _issue(
        cls,
        *,
        authorization_id: str,
        authorization_sha256: str,
        authorization_mode: str,
        target_mode: str,
        operator_id: str,
        venue: str,
        valid_from: datetime,
        valid_until: datetime,
        verified_at: datetime,
        action: str = ACTION_NO_ORDER,
    ) -> "OperationalAuthorizationProof":
        proof = object.__new__(cls)
        object.__setattr__(proof, "authorization_id", authorization_id)
        object.__setattr__(proof, "authorization_sha256", authorization_sha256)
        object.__setattr__(proof, "authorization_mode", authorization_mode)
        object.__setattr__(proof, "target_mode", target_mode)
        object.__setattr__(proof, "operator_id", operator_id)
        object.__setattr__(proof, "venue", venue)
        object.__setattr__(proof, "valid_from", valid_from)
        object.__setattr__(proof, "valid_until", valid_until)
        object.__setattr__(proof, "verified_at", verified_at)
        object.__setattr__(proof, "action", action)
        proof._validate()
        return proof

    def _validate(self) -> None:
        if self.action != ACTION_NO_ORDER:
            raise ValueError("operational authorization proof must remain no_order")
        if self.authorization_mode != MODE_SHADOW:
            raise ValueError("operational authorization proof must come from a Shadow authorization")
        if self.target_mode not in _AUTHORIZATION_PROOF_TARGET_MODES:
            raise ValueError("operational authorization proof target mode is not enabled")
        if not self.authorization_id.strip() or not self.operator_id.strip() or not self.venue.strip():
            raise ValueError("operational authorization proof identity is required")
        if not _SHA256.fullmatch(self.authorization_sha256):
            raise ValueError("operational authorization proof hash is invalid")
        for label, value in (
            ("valid_from", self.valid_from),
            ("valid_until", self.valid_until),
            ("verified_at", self.verified_at),
        ):
            if value.tzinfo is None:
                raise ValueError(f"operational authorization proof {label} must be timezone-aware")
        if self.valid_from >= self.valid_until:
            raise ValueError("operational authorization proof validity window is invalid")
        if not self.valid_from <= self.verified_at <= self.valid_until:
            raise ValueError("operational authorization proof was verified outside its validity window")


@contextmanager
def control_state_lock(path: Path) -> Iterator[None]:
    """Serialize CLI mutations so an emergency stop cannot be overwritten."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"\0")
            handle.flush()
            os.fsync(handle.fileno())
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def transition(
    current: OperationalControlState,
    *,
    target_mode: str,
    reason: str,
    operator_id: str,
    authorization: OperationalAuthorizationProof | None = None,
    changed_at: datetime,
) -> OperationalControlState:
    if target_mode not in MODES:
        raise ValueError(f"unknown operational mode: {target_mode}")
    if target_mode == MODE_LIMITED_USE:
        raise ValueError("limited use has no enabled operational-control transition")
    if changed_at.tzinfo is None:
        raise ValueError("operational control timestamp must be timezone-aware")
    if changed_at <= current.changed_at:
        raise ValueError("operational control time must move strictly forward")
    if not reason.strip() or not operator_id.strip():
        raise ValueError("operational control reason and operator are required")
    current_mode = current.mode
    if target_mode == current_mode:
        raise ValueError("operational mode change must alter the mode")
    if target_mode == MODE_STOPPED:
        if authorization is not None:
            raise ValueError("emergency stop must not consume an authorization proof")
        effective_authorization_id = current.authorization_id
        effective_authorization_sha256 = current.authorization_sha256
    else:
        if not isinstance(authorization, OperationalAuthorizationProof):
            raise ValueError(
                "production mode transition requires a verifier-issued authorization proof"
            )
        if authorization.target_mode != target_mode:
            raise ValueError("authorization proof target mode does not match transition")
        if authorization.operator_id != operator_id:
            raise ValueError("authorization proof operator does not match transition operator")
        if not authorization.valid_from <= changed_at <= authorization.valid_until:
            raise ValueError("authorization proof is outside its validity window")
        if changed_at < authorization.verified_at:
            raise ValueError("authorization proof cannot be used before verification")
        if current_mode == MODE_STOPPED and (
            authorization.authorization_id == current.authorization_id
            or authorization.authorization_sha256 == current.authorization_sha256
        ):
            raise ValueError("resuming from emergency stop requires a new authorization id")
        if current_mode == MODE_STOPPED and target_mode != MODE_OFFLINE_ENGINEERING:
            raise ValueError("resuming from emergency stop must return to offline engineering first")
        if current_mode != MODE_STOPPED and target_mode == MODE_OFFLINE_ENGINEERING:
            raise ValueError("offline engineering is only an initial mode after stop")
        if current_mode != MODE_STOPPED and _MODE_ORDER[target_mode] != _MODE_ORDER[current_mode] + 1:
            raise ValueError(
                f"operational mode must advance one stage at a time: {current_mode} -> {target_mode}"
            )
        effective_authorization_id = authorization.authorization_id
        effective_authorization_sha256 = authorization.authorization_sha256

    publish_allowed, new_review_allowed, source_read_allowed = _permissions_for(target_mode)
    change = ModeChange(
        from_mode=current_mode,
        to_mode=target_mode,
        changed_at=changed_at,
        reason=reason,
        operator_id=operator_id,
        authorization_id=effective_authorization_id,
        authorization_sha256=effective_authorization_sha256,
    )
    return OperationalControlState(
        mode=target_mode,
        changed_at=changed_at,
        reason=reason,
        operator_id=operator_id,
        authorization_id=effective_authorization_id,
        authorization_sha256=effective_authorization_sha256,
        publish_allowed=publish_allowed,
        new_review_allowed=new_review_allowed,
        source_read_allowed=source_read_allowed,
        history=current.history + (change,),
    )


def apply_emergency_stop(
    current: OperationalControlState,
    *,
    reason: str,
    operator_id: str,
    changed_at: datetime,
) -> OperationalControlState:
    if current.mode == MODE_STOPPED:
        return current
    return transition(
        current,
        target_mode=MODE_STOPPED,
        reason=reason,
        operator_id=operator_id,
        authorization=None,
        changed_at=changed_at,
    )


def _validate_history(
    history: tuple[ModeChange, ...],
    *,
    mode: str,
    authorization_id: str,
    authorization_sha256: str,
    changed_at: datetime,
    reason: str,
    operator_id: str,
) -> None:
    expected_mode = MODE_OFFLINE_ENGINEERING
    expected_authorization_id = ""
    expected_authorization_sha256 = ""
    previous_changed_at: datetime | None = None
    for change in history:
        if (
            previous_changed_at is not None
            and change.changed_at <= previous_changed_at
        ):
            raise ValueError("operational control history time must move forward")
        if change.from_mode != expected_mode:
            raise ValueError("operational control history is not contiguous")
        if change.to_mode == MODE_LIMITED_USE:
            raise ValueError("limited use has no enabled operational-control transition")
        if change.to_mode == MODE_STOPPED:
            if (
                change.authorization_id != expected_authorization_id
                or change.authorization_sha256 != expected_authorization_sha256
            ):
                raise ValueError("emergency stop must preserve the active authorization")
        elif expected_mode == MODE_STOPPED:
            if change.to_mode != MODE_OFFLINE_ENGINEERING:
                raise ValueError(
                    "resuming from emergency stop must return to offline engineering first"
                )
            if (
                not change.authorization_id
                or change.authorization_id == expected_authorization_id
                or not change.authorization_sha256
                or change.authorization_sha256 == expected_authorization_sha256
            ):
                raise ValueError("resuming from emergency stop requires a new authorization")
        elif change.to_mode == MODE_OFFLINE_ENGINEERING:
            raise ValueError("offline engineering is only an initial mode after stop")
        elif _MODE_ORDER[change.to_mode] != _MODE_ORDER[expected_mode] + 1:
            raise ValueError("operational control history must advance one stage at a time")
        expected_mode = change.to_mode
        expected_authorization_id = change.authorization_id
        expected_authorization_sha256 = change.authorization_sha256
        previous_changed_at = change.changed_at

    if history:
        last = history[-1]
        if (
            last.to_mode != mode
            or last.authorization_id != authorization_id
            or last.authorization_sha256 != authorization_sha256
            or last.changed_at != changed_at
            or last.reason != reason
            or last.operator_id != operator_id
        ):
            raise ValueError("operational control snapshot does not match its history")
    elif mode != MODE_OFFLINE_ENGINEERING or authorization_id or authorization_sha256:
        raise ValueError("historyless operational control state must be offline engineering")


def from_dict(payload: Mapping[str, Any]) -> OperationalControlState:
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported operational control schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("operational control must remain no_order")
    permissions = payload.get("permissions") or {}
    history_payload = payload.get("history") or []
    if not isinstance(permissions, Mapping):
        raise ValueError("operational permissions must be an object")
    if not isinstance(history_payload, list):
        raise ValueError("operational control history must be a list")
    for key in (
        "publish_allowed",
        "new_review_allowed",
        "source_read_allowed",
    ):
        if not isinstance(permissions.get(key), bool):
            raise ValueError("operational permissions must be boolean")
    history = tuple(
        ModeChange(
            from_mode=str(item["from_mode"]),
            to_mode=str(item["to_mode"]),
            changed_at=datetime.fromisoformat(str(item["changed_at"])),
            reason=str(item["reason"]),
            operator_id=str(item["operator_id"]),
            authorization_id=str(item.get("authorization_id") or ""),
            authorization_sha256=str(item.get("authorization_sha256") or ""),
        )
        for item in history_payload
    )
    state = OperationalControlState(
        mode=str(payload["mode"]),
        changed_at=datetime.fromisoformat(str(payload["changed_at"])),
        reason=str(payload["reason"]),
        operator_id=str(payload["operator_id"]),
        authorization_id=str(payload.get("authorization_id") or ""),
        authorization_sha256=str(payload.get("authorization_sha256") or ""),
        publish_allowed=bool(permissions.get("publish_allowed")),
        new_review_allowed=bool(permissions.get("new_review_allowed")),
        source_read_allowed=bool(permissions.get("source_read_allowed")),
        history=history,
        schema_version=SCHEMA_VERSION,
        action=ACTION_NO_ORDER,
    )
    _validate_history(
        history,
        mode=state.mode,
        authorization_id=state.authorization_id,
        authorization_sha256=state.authorization_sha256,
        changed_at=state.changed_at,
        reason=state.reason,
        operator_id=state.operator_id,
    )
    return state


def read_control_state(path: Path) -> OperationalControlState:
    return from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_control_state(path: Path, state: OperationalControlState) -> OperationalControlState:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.as_dict(), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.stem + ".", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return state
