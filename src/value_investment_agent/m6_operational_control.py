"""Versioned operational control and emergency-stop contract for M6.

This module is an offline policy engine. It records the allowed
staging/shadow/limited-use mode and provides an atomic emergency-stop state
without connecting to production, publishing a workbook or creating an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "m6-operational-control-v1"
ACTION_NO_ORDER = "no_order"

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


@dataclass(frozen=True)
class ModeChange:
    from_mode: str
    to_mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str


@dataclass(frozen=True)
class OperationalControlState:
    mode: str
    changed_at: datetime
    reason: str
    operator_id: str
    authorization_id: str
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
        if self.mode not in {MODE_OFFLINE_ENGINEERING, MODE_STOPPED} and not self.authorization_id.strip():
            raise ValueError("production mode transition requires an authorization id")
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


def transition(
    current: OperationalControlState,
    *,
    target_mode: str,
    reason: str,
    operator_id: str,
    authorization_id: str,
    changed_at: datetime,
) -> OperationalControlState:
    if target_mode not in MODES:
        raise ValueError(f"unknown operational mode: {target_mode}")
    if changed_at.tzinfo is None:
        raise ValueError("operational control timestamp must be timezone-aware")
    if not reason.strip() or not operator_id.strip():
        raise ValueError("operational control reason and operator are required")
    if target_mode != MODE_STOPPED and not authorization_id.strip():
        raise ValueError("production mode transition requires an authorization id")
    current_mode = current.mode
    if target_mode == MODE_STOPPED:
        pass
    elif current_mode == MODE_STOPPED:
        if authorization_id == current.authorization_id:
            raise ValueError("resuming from emergency stop requires a new authorization id")
        if target_mode != MODE_OFFLINE_ENGINEERING:
            raise ValueError("resuming from emergency stop must return to offline engineering first")
    elif target_mode == MODE_OFFLINE_ENGINEERING:
        raise ValueError("offline engineering is only an initial mode after stop")
    elif _MODE_ORDER[target_mode] != _MODE_ORDER[current_mode] + 1:
        raise ValueError(
            f"operational mode must advance one stage at a time: {current_mode} -> {target_mode}"
        )

    effective_authorization_id = (
        current.authorization_id if target_mode == MODE_STOPPED else authorization_id
    )
    publish_allowed, new_review_allowed, source_read_allowed = _permissions_for(target_mode)
    change = ModeChange(
        from_mode=current_mode,
        to_mode=target_mode,
        changed_at=changed_at,
        reason=reason,
        operator_id=operator_id,
        authorization_id=effective_authorization_id,
    )
    return OperationalControlState(
        mode=target_mode,
        changed_at=changed_at,
        reason=reason,
        operator_id=operator_id,
        authorization_id=effective_authorization_id,
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
    return transition(
        current,
        target_mode=MODE_STOPPED,
        reason=reason,
        operator_id=operator_id,
        authorization_id="",
        changed_at=changed_at,
    )


def from_dict(payload: Mapping[str, Any]) -> OperationalControlState:
    permissions = payload.get("permissions") or {}
    history_payload = payload.get("history") or []
    if not isinstance(history_payload, list):
        raise ValueError("operational control history must be a list")
    history = tuple(
        ModeChange(
            from_mode=str(item["from_mode"]),
            to_mode=str(item["to_mode"]),
            changed_at=datetime.fromisoformat(str(item["changed_at"])),
            reason=str(item["reason"]),
            operator_id=str(item["operator_id"]),
            authorization_id=str(item.get("authorization_id") or ""),
        )
        for item in history_payload
    )
    return OperationalControlState(
        mode=str(payload["mode"]),
        changed_at=datetime.fromisoformat(str(payload["changed_at"])),
        reason=str(payload["reason"]),
        operator_id=str(payload["operator_id"]),
        authorization_id=str(payload.get("authorization_id") or ""),
        publish_allowed=bool(permissions.get("publish_allowed")),
        new_review_allowed=bool(permissions.get("new_review_allowed")),
        source_read_allowed=bool(permissions.get("source_read_allowed")),
        history=history,
        schema_version=str(payload.get("schema_version") or SCHEMA_VERSION),
        action=str(payload.get("action") or ACTION_NO_ORDER),
    )


def read_control_state(path: Path) -> OperationalControlState:
    return from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_control_state(path: Path, state: OperationalControlState) -> OperationalControlState:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.as_dict(), ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)
    return state
