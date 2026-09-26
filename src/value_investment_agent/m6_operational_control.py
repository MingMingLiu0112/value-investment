"""Versioned operational control and emergency-stop contract for M6.

This module is an offline policy engine. It never connects to production,
publishes a workbook, or creates an order. A mode advance is accepted only
when it carries a proof reconstructed from the exact signed authorization,
its scope/deployment/config artifacts, and a separately supplied trust root.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import tempfile
from typing import Any, Iterator, Mapping

from .operations.authorization.trust_root_registry import require_pinned_trust_root


SCHEMA_VERSION = "m6-operational-control-v2"
LEGACY_SCHEMA_VERSION = "m6-operational-control-v1"
PROOF_SCHEMA_VERSION = "m6-operational-authorization-proof-v1"
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
_PROOF_FIELDS = frozenset(
    {
        "schema_version",
        "authorization_bundle",
        "trust_root",
        "authorization_id",
        "authorization_sha256",
        "authorization_mode",
        "target_mode",
        "operator_id",
        "venue",
        "scope_manifest_sha256",
        "deployment_sha256",
        "config_sha256",
        "valid_from",
        "valid_until",
        "verified_at",
        "proof_id",
        "action",
    }
)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")
    return value.strip()


def _required_sha256(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if not _SHA256.fullmatch(text):
        raise ValueError(f"{field_name} must be SHA-256 hex")
    return text


def _required_datetime(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True, init=False)
class OperationalAuthorizationProof:
    """Sealed proof that one exact signed authorization passed verification.

    The public constructor is disabled. ``_from_verified`` is intentionally
    private, but even a caller that reaches it cannot obtain a usable proof
    without a valid signature and matching externally supplied trust root:
    ``_validate`` re-verifies the bytes and every scope binding.
    """

    schema_version: str
    authorization_bundle: dict[str, Any]
    trust_root: dict[str, Any]
    authorization_id: str
    authorization_sha256: str
    authorization_mode: str
    target_mode: str
    operator_id: str
    venue: str
    scope_manifest_sha256: str
    deployment_sha256: str
    config_sha256: str
    valid_from: datetime
    valid_until: datetime
    verified_at: datetime
    proof_id: str
    action: str

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(
            "operational authorization proof must come from the signed verifier"
        )

    @classmethod
    def _from_verified(
        cls,
        *,
        authorization_bundle: Mapping[str, Any],
        trust_root: Mapping[str, Any],
        target_mode: str,
        operator_id: str,
        verified_at: datetime,
    ) -> "OperationalAuthorizationProof":
        # Lazy import avoids the control <-> receipt module cycle.
        from .m6_shadow_receipts import verify_shadow_authorization

        verified_at = _required_datetime(verified_at, "verified_at")
        authorization, authorization_sha256 = verify_shadow_authorization(
            authorization_bundle,
            trust_root,
            at=verified_at,
            expected_target_mode=target_mode,
            expected_operator_id=operator_id,
        )
        proof = object.__new__(cls)
        payload = {
            "schema_version": PROOF_SCHEMA_VERSION,
            "authorization_bundle": dict(authorization_bundle),
            "trust_root": dict(trust_root),
            "authorization_id": authorization["authorization_id"],
            "authorization_sha256": authorization_sha256,
            "authorization_mode": authorization["mode"],
            "target_mode": target_mode,
            "operator_id": operator_id,
            "venue": authorization["venue"],
            "scope_manifest_sha256": authorization["scope_manifest_sha256"],
            "deployment_sha256": authorization["deployment_sha256"],
            "config_sha256": authorization["config_sha256"],
            "valid_from": authorization["valid_from"],
            "valid_until": authorization["valid_until"],
            "verified_at": verified_at.isoformat(),
            "action": ACTION_NO_ORDER,
        }
        for name, value in payload.items():
            if name in {"valid_from", "valid_until", "verified_at"}:
                value = datetime.fromisoformat(value)
            object.__setattr__(proof, name, value)
        object.__setattr__(proof, "proof_id", _sha256(payload))
        proof._validate(at=verified_at)
        return proof

    @property
    def proof_sha256(self) -> str:
        return self.proof_id

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "authorization_bundle": self.authorization_bundle,
            "trust_root": self.trust_root,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256,
            "authorization_mode": self.authorization_mode,
            "target_mode": self.target_mode,
            "operator_id": self.operator_id,
            "venue": self.venue,
            "scope_manifest_sha256": self.scope_manifest_sha256,
            "deployment_sha256": self.deployment_sha256,
            "config_sha256": self.config_sha256,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "verified_at": self.verified_at.isoformat(),
            "action": self.action,
        }

    def _validate(self, *, at: datetime | None = None) -> None:
        if self.schema_version != PROOF_SCHEMA_VERSION:
            raise ValueError("unsupported operational authorization proof schema")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("operational authorization proof must remain no_order")
        if self.authorization_mode != MODE_SHADOW:
            raise ValueError(
                "operational authorization proof must come from a Shadow authorization"
            )
        if self.target_mode not in _AUTHORIZATION_PROOF_TARGET_MODES:
            raise ValueError("operational authorization proof target mode is not enabled")
        for label, value in (
            ("authorization_id", self.authorization_id),
            ("operator_id", self.operator_id),
            ("venue", self.venue),
        ):
            _required_text(value, label)
        for label, value in (
            ("authorization_sha256", self.authorization_sha256),
            ("scope_manifest_sha256", self.scope_manifest_sha256),
            ("deployment_sha256", self.deployment_sha256),
            ("config_sha256", self.config_sha256),
            ("proof_id", self.proof_id),
        ):
            _required_sha256(value, label)
        valid_from = _required_datetime(self.valid_from, "valid_from")
        valid_until = _required_datetime(self.valid_until, "valid_until")
        verified_at = _required_datetime(self.verified_at, "verified_at")
        if valid_from >= valid_until:
            raise ValueError("operational authorization proof validity window is invalid")
        if not valid_from <= verified_at <= valid_until:
            raise ValueError(
                "operational authorization proof was verified outside its validity window"
            )
        use_at = (
            datetime.now(timezone.utc)
            if at is None
            else _required_datetime(at, "authorization use time")
        )
        if not valid_from <= use_at <= valid_until:
            raise ValueError("operational authorization proof is outside its validity window")
        if use_at < verified_at:
            raise ValueError(
                "operational authorization proof cannot be used before verification"
            )

        from .m6_shadow_receipts import verify_shadow_authorization

        authorization, authorization_sha256 = verify_shadow_authorization(
            self.authorization_bundle,
            self.trust_root,
            at=use_at,
            expected_target_mode=self.target_mode,
            expected_operator_id=self.operator_id,
            expected_authorization_id=self.authorization_id,
            expected_deployment_sha256=self.deployment_sha256,
            expected_config_sha256=self.config_sha256,
        )
        # Every read, transition, advance and restart re-checks that the trust
        # root is still pinned.  A valid signature over a self-minted root is
        # not operational authorization.
        require_pinned_trust_root(self.trust_root)
        expected_fields = {
            "mode": self.authorization_mode,
            "authorization_id": self.authorization_id,
            "venue": self.venue,
            "scope_manifest_sha256": self.scope_manifest_sha256,
            "deployment_sha256": self.deployment_sha256,
            "config_sha256": self.config_sha256,
            "valid_from": self.valid_from.isoformat(),
            "valid_until": self.valid_until.isoformat(),
        }
        if authorization_sha256 != self.authorization_sha256:
            raise ValueError("operational authorization proof hash changed")
        if any(authorization.get(name) != value for name, value in expected_fields.items()):
            raise ValueError("operational authorization proof payload changed")
        if _sha256(self._payload()) != self.proof_id:
            raise ValueError("operational authorization proof id changed")

    def verify_for_transition(
        self,
        *,
        target_mode: str,
        operator_id: str,
        at: datetime,
    ) -> None:
        if self.target_mode != target_mode:
            raise ValueError("authorization proof target mode does not match transition")
        if self.operator_id != operator_id:
            raise ValueError("authorization proof operator does not match transition operator")
        self._validate(at=at)

    def as_dict(self, *, at: datetime | None = None) -> dict[str, Any]:
        self._validate(at=at)
        return {**self._payload(), "proof_id": self.proof_id}

    @classmethod
    def from_dict(
        cls,
        payload: object,
        *,
        at: datetime | None = None,
    ) -> "OperationalAuthorizationProof":
        if not isinstance(payload, Mapping) or set(payload) != _PROOF_FIELDS:
            raise ValueError("operational authorization proof schema differs")
        data = dict(payload)
        if data["schema_version"] != PROOF_SCHEMA_VERSION:
            raise ValueError("unsupported operational authorization proof schema")
        proof = object.__new__(cls)
        for name in (
            "schema_version",
            "authorization_id",
            "authorization_sha256",
            "authorization_mode",
            "target_mode",
            "operator_id",
            "venue",
            "scope_manifest_sha256",
            "deployment_sha256",
            "config_sha256",
            "proof_id",
            "action",
        ):
            object.__setattr__(proof, name, data[name])
        object.__setattr__(proof, "authorization_bundle", data["authorization_bundle"])
        object.__setattr__(proof, "trust_root", data["trust_root"])
        for name in ("valid_from", "valid_until", "verified_at"):
            try:
                value = datetime.fromisoformat(str(data[name]))
            except ValueError as error:
                raise ValueError(f"operational authorization proof {name} is invalid") from error
            object.__setattr__(proof, name, _required_datetime(value, name))
        proof._validate(at=at)
        return proof


@dataclass(frozen=True)
class ModeChange:
    from_mode: str
    to_mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str
    authorization_sha256: str
    authorization_proof: OperationalAuthorizationProof | None

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        if self.from_mode not in MODES or self.to_mode not in MODES:
            raise ValueError("unknown operational mode")
        if self.from_mode == self.to_mode:
            raise ValueError("operational mode change must alter the mode")
        changed_at = _required_datetime(self.changed_at, "operational control timestamp")
        object.__setattr__(self, "changed_at", changed_at)
        _required_text(self.reason, "operational control reason")
        _required_text(self.operator_id, "operational control operator")
        if self.to_mode not in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED}:
            if self.authorization_proof is None:
                raise ValueError(
                    "production mode transition requires a verified authorization proof"
                )
            self.authorization_proof.verify_for_transition(
                target_mode=self.to_mode,
                operator_id=self.operator_id,
                at=changed_at,
            )
        if self.authorization_proof is None:
            if self.authorization_id or self.authorization_sha256:
                raise ValueError(
                    "authorization id and hash cannot authorize without a verified proof"
                )
            return
        if (
            self.authorization_id != self.authorization_proof.authorization_id
            or self.authorization_sha256 != self.authorization_proof.authorization_sha256
        ):
            raise ValueError("authorization id or hash does not match its verified proof")
        self.authorization_proof._validate(at=changed_at)


@dataclass(frozen=True)
class OperationalControlState:
    mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str
    authorization_sha256: str
    authorization_proof: OperationalAuthorizationProof | None
    publish_allowed: bool
    new_review_allowed: bool
    source_read_allowed: bool
    history: tuple[ModeChange, ...]
    schema_version: str = SCHEMA_VERSION
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        self._validate(at=self.changed_at)

    def _validate(self, *, at: datetime | None = None) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported operational control schema")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("operational control must remain no_order")
        if self.mode not in MODES:
            raise ValueError(f"unknown operational mode: {self.mode}")
        changed_at = _required_datetime(self.changed_at, "operational control timestamp")
        object.__setattr__(self, "changed_at", changed_at)
        validate_at = (
            datetime.now(timezone.utc)
            if at is None
            else _required_datetime(at, "operational control validation time")
        )
        if validate_at < changed_at:
            raise ValueError("operational control state is from the future")
        _required_text(self.reason, "operational control reason")
        _required_text(self.operator_id, "operational control operator")
        if self.authorization_proof is None:
            if self.authorization_id or self.authorization_sha256:
                raise ValueError(
                    "authorization id and hash cannot authorize without a verified proof"
                )
        else:
            if (
                self.authorization_id != self.authorization_proof.authorization_id
                or self.authorization_sha256 != self.authorization_proof.authorization_sha256
            ):
                raise ValueError("state authorization does not match its verified proof")
            if self.mode in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED}:
                self.authorization_proof._validate(at=changed_at)
            else:
                self.authorization_proof.verify_for_transition(
                    target_mode=self.mode,
                    operator_id=self.operator_id,
                    at=validate_at,
                )
        if self.mode not in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED} and self.authorization_proof is None:
            raise ValueError("active operational mode requires a verified authorization proof")
        expected_permissions = _permissions_for(self.mode)
        actual_permissions = (
            self.publish_allowed,
            self.new_review_allowed,
            self.source_read_allowed,
        )
        if actual_permissions != expected_permissions:
            raise ValueError("operational permissions do not match the current mode")
        _validate_history(
            self.history,
            mode=self.mode,
            authorization_id=self.authorization_id,
            authorization_sha256=self.authorization_sha256,
            authorization_proof_id=(
                None if self.authorization_proof is None else self.authorization_proof.proof_id
            ),
            changed_at=self.changed_at,
            reason=self.reason,
            operator_id=self.operator_id,
        )

    def as_dict(self, *, at: datetime | None = None) -> dict[str, Any]:
        self._validate(at=at)
        validate_at = (
            datetime.now(timezone.utc)
            if at is None
            else _required_datetime(at, "operational control validation time")
        )
        proof_at = (
            self.changed_at
            if self.mode in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED}
            else validate_at
        )
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "mode": self.mode,
            "changed_at": self.changed_at.isoformat(),
            "reason": self.reason,
            "operator_id": self.operator_id,
            "authorization_id": self.authorization_id,
            "authorization_sha256": self.authorization_sha256,
            "authorization_proof": (
                None
                if self.authorization_proof is None
                else self.authorization_proof.as_dict(at=proof_at)
            ),
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
                    "authorization_proof": (
                        None
                        if item.authorization_proof is None
                        else item.authorization_proof.as_dict(at=item.changed_at)
                    ),
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
        authorization_proof=None,
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
    if not isinstance(current, OperationalControlState):
        raise ValueError("current operational state is invalid")
    changed_at = _required_datetime(changed_at, "operational control timestamp")
    if target_mode not in MODES:
        raise ValueError(f"unknown operational mode: {target_mode}")
    if target_mode == MODE_LIMITED_USE:
        raise ValueError("limited use has no enabled operational-control transition")
    if changed_at <= current.changed_at:
        raise ValueError("operational control time must move strictly forward")
    current._validate(at=changed_at)
    _required_text(reason, "operational control reason")
    _required_text(operator_id, "operational control operator")
    current_mode = current.mode
    if target_mode == current_mode:
        raise ValueError("operational mode change must alter the mode")
    if target_mode == MODE_STOPPED:
        if authorization is not None:
            raise ValueError("emergency stop must not consume an authorization proof")
        effective_proof = current.authorization_proof
        effective_authorization_id = current.authorization_id
        effective_authorization_sha256 = current.authorization_sha256
    else:
        if not isinstance(authorization, OperationalAuthorizationProof):
            raise ValueError(
                "production mode transition requires a verifier-issued authorization proof"
            )
        authorization.verify_for_transition(
            target_mode=target_mode,
            operator_id=operator_id,
            at=changed_at,
        )
        if current_mode == MODE_STOPPED:
            prior_proof_id = (
                None
                if current.authorization_proof is None
                else current.authorization_proof.proof_id
            )
            if (
                authorization.proof_id == prior_proof_id
                or authorization.authorization_id == current.authorization_id
                or authorization.authorization_sha256 == current.authorization_sha256
            ):
                raise ValueError("resuming from emergency stop requires a new authorization")
            if target_mode != MODE_OFFLINE_ENGINEERING:
                raise ValueError(
                    "resuming from emergency stop must return to offline engineering first"
                )
        elif target_mode == MODE_OFFLINE_ENGINEERING:
            raise ValueError("offline engineering is only an initial mode after stop")
        elif _MODE_ORDER[target_mode] != _MODE_ORDER[current_mode] + 1:
            raise ValueError(
                f"operational mode must advance one stage at a time: {current_mode} -> {target_mode}"
            )
        effective_proof = authorization
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
        authorization_proof=effective_proof,
    )
    state = OperationalControlState(
        mode=target_mode,
        changed_at=changed_at,
        reason=reason,
        operator_id=operator_id,
        authorization_id=effective_authorization_id,
        authorization_sha256=effective_authorization_sha256,
        authorization_proof=effective_proof,
        publish_allowed=publish_allowed,
        new_review_allowed=new_review_allowed,
        source_read_allowed=source_read_allowed,
        history=current.history + (change,),
    )
    state._validate(at=changed_at)
    return state


def apply_emergency_stop(
    current: OperationalControlState,
    *,
    reason: str,
    operator_id: str,
    changed_at: datetime,
) -> OperationalControlState:
    if current.mode == MODE_STOPPED:
        current._validate(at=changed_at)
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
    authorization_proof_id: str | None,
    changed_at: datetime,
    reason: str,
    operator_id: str,
) -> None:
    expected_mode = MODE_OFFLINE_ENGINEERING
    expected_authorization_id = ""
    expected_authorization_sha256 = ""
    expected_proof_id: str | None = None
    previous_changed_at: datetime | None = None
    for change in history:
        if not isinstance(change, ModeChange):
            raise ValueError("operational control history item is invalid")
        change._validate()
        if previous_changed_at is not None and change.changed_at <= previous_changed_at:
            raise ValueError("operational control history time must move forward")
        if change.from_mode != expected_mode:
            raise ValueError("operational control history is not contiguous")
        if change.to_mode == MODE_LIMITED_USE:
            raise ValueError("limited use has no enabled operational-control transition")
        if change.to_mode == MODE_STOPPED:
            change_proof_id = (
                None
                if change.authorization_proof is None
                else change.authorization_proof.proof_id
            )
            if (
                change_proof_id != expected_proof_id
                or change.authorization_id != expected_authorization_id
                or change.authorization_sha256 != expected_authorization_sha256
            ):
                raise ValueError("emergency stop must preserve the active authorization")
        elif expected_mode == MODE_STOPPED:
            if change.to_mode != MODE_OFFLINE_ENGINEERING:
                raise ValueError(
                    "resuming from emergency stop must return to offline engineering first"
                )
            if change.authorization_proof is None:
                raise ValueError("resuming from emergency stop requires a new authorization")
            if (
                change.authorization_proof.proof_id == expected_proof_id
                or change.authorization_id == expected_authorization_id
                or change.authorization_sha256 == expected_authorization_sha256
            ):
                raise ValueError("resuming from emergency stop requires a new authorization")
        elif change.to_mode == MODE_OFFLINE_ENGINEERING:
            raise ValueError("offline engineering is only an initial mode after stop")
        elif change.authorization_proof is None:
            raise ValueError("operational control history requires a verified authorization proof")
        elif _MODE_ORDER[change.to_mode] != _MODE_ORDER[expected_mode] + 1:
            raise ValueError("operational control history must advance one stage at a time")
        expected_mode = change.to_mode
        expected_authorization_id = change.authorization_id
        expected_authorization_sha256 = change.authorization_sha256
        expected_proof_id = (
            None
            if change.authorization_proof is None
            else change.authorization_proof.proof_id
        )
        previous_changed_at = change.changed_at

    if history:
        last = history[-1]
        last_proof_id = (
            None
            if last.authorization_proof is None
            else last.authorization_proof.proof_id
        )
        if (
            last.to_mode != mode
            or last.authorization_id != authorization_id
            or last.authorization_sha256 != authorization_sha256
            or last_proof_id != authorization_proof_id
            or last.changed_at != changed_at
            or last.reason != reason
            or last.operator_id != operator_id
        ):
            raise ValueError("operational control snapshot does not match its history")
    elif mode != MODE_OFFLINE_ENGINEERING or authorization_id or authorization_sha256:
        raise ValueError("historyless operational control state must be offline engineering")


def from_dict(
    payload: Mapping[str, Any],
    *,
    at: datetime | None = None,
) -> OperationalControlState:
    if not isinstance(payload, Mapping):
        raise ValueError("operational control state must be an object")
    data = dict(payload)
    if data.get("schema_version") == LEGACY_SCHEMA_VERSION:
        if (
            data.get("mode") != MODE_OFFLINE_ENGINEERING
            or data.get("authorization_id")
            or data.get("authorization_sha256")
            or data.get("history")
        ):
            raise ValueError(
                "legacy operational state cannot revalidate authorization; restart offline"
            )
        data["schema_version"] = SCHEMA_VERSION
        data["authorization_proof"] = None
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported operational control schema")
    if data.get("action") != ACTION_NO_ORDER:
        raise ValueError("operational control must remain no_order")
    permissions = data.get("permissions") or {}
    history_payload = data.get("history") or []
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
            authorization_proof=(
                None
                if item.get("authorization_proof") is None
                else OperationalAuthorizationProof.from_dict(
                    item["authorization_proof"],
                    at=datetime.fromisoformat(str(item["changed_at"])),
                )
            ),
        )
        for item in history_payload
    )
    proof_payload = data.get("authorization_proof")
    state_changed_at = datetime.fromisoformat(str(data["changed_at"]))
    state = OperationalControlState(
        mode=str(data["mode"]),
        changed_at=state_changed_at,
        reason=str(data["reason"]),
        operator_id=str(data["operator_id"]),
        authorization_id=str(data.get("authorization_id") or ""),
        authorization_sha256=str(data.get("authorization_sha256") or ""),
        authorization_proof=(
            None
            if proof_payload is None
            else OperationalAuthorizationProof.from_dict(proof_payload, at=state_changed_at)
        ),
        publish_allowed=bool(permissions.get("publish_allowed")),
        new_review_allowed=bool(permissions.get("new_review_allowed")),
        source_read_allowed=bool(permissions.get("source_read_allowed")),
        history=history,
        schema_version=SCHEMA_VERSION,
        action=ACTION_NO_ORDER,
    )
    state._validate(
        at=(
            datetime.now(timezone.utc)
            if at is None
            else _required_datetime(at, "operational control validation time")
        )
    )
    return state


def read_control_state(
    path: Path,
    *,
    at: datetime | None = None,
) -> OperationalControlState:
    return from_dict(json.loads(path.read_text(encoding="utf-8")), at=at)


def write_control_state(
    path: Path,
    state: OperationalControlState,
    *,
    at: datetime | None = None,
) -> OperationalControlState:
    validate_at = (
        datetime.now(timezone.utc)
        if at is None
        else _required_datetime(at, "operational control validation time")
    )
    state._validate(at=validate_at)
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        state.as_dict(at=validate_at),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ) + "\n"
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


__all__ = [
    "ACTION_NO_ORDER",
    "LEGACY_SCHEMA_VERSION",
    "MODE_LIMITED_USE",
    "MODE_OFFLINE_ENGINEERING",
    "MODE_SHADOW",
    "MODE_STAGING",
    "MODE_STOPPED",
    "MODES",
    "ModeChange",
    "OperationalAuthorizationProof",
    "OperationalControlState",
    "PROOF_SCHEMA_VERSION",
    "SCHEMA_VERSION",
    "apply_emergency_stop",
    "control_state_lock",
    "from_dict",
    "initial_state",
    "read_control_state",
    "transition",
    "write_control_state",
]
