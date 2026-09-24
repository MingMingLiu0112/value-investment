"""Explicit authorization for an offline ACTUAL M5 receipt.

This is intentionally narrower than M6 production authorization: it permits a
local append-only research receipt only.  It never authorizes a scheduler,
notification target, database migration, broker connection or order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import re

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import _required_datetime, _required_text
from .m5_event_core import NAMESPACE_ACTUAL, NAMESPACE_SIMULATED


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
USER_CONFIRMED_DELEGATED_REVIEW = "USER_CONFIRMED_DELEGATED_REVIEW"


@dataclass(frozen=True)
class M5ActualOfflineAuthorization:
    authorization_id: str
    review_provenance: str
    review_sha256: str
    queue_sha256: str
    dependency_graph_sha256: str
    authorized_at: datetime
    scheduler_enabled: bool = False
    notification_enabled: bool = False
    production_database_write: bool = False
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorization_id", _required_text(self.authorization_id, "authorization_id"))
        if self.review_provenance != USER_CONFIRMED_DELEGATED_REVIEW:
            raise ValueError("Actual offline authorization requires user-confirmed review provenance")
        for field in ("review_sha256", "queue_sha256", "dependency_graph_sha256"):
            value = _required_text(getattr(self, field), field).lower()
            if not _SHA256.fullmatch(value):
                raise ValueError(f"{field} must be SHA-256 hex")
            object.__setattr__(self, field, value)
        object.__setattr__(self, "authorized_at", _required_datetime(self.authorized_at, "authorized_at"))
        if not all(isinstance(value, bool) for value in (self.scheduler_enabled, self.notification_enabled, self.production_database_write)):
            raise ValueError("Actual offline authorization operation flags must be boolean")
        if self.scheduler_enabled or self.notification_enabled or self.production_database_write:
            raise ValueError("Actual offline authorization cannot enable production operations")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Actual offline authorization must remain no_order")

    def as_policy(self) -> dict:
        return {
            "authorization_id": self.authorization_id,
            "review_provenance": self.review_provenance,
            "review_sha256": self.review_sha256,
            "queue_sha256": self.queue_sha256,
            "dependency_graph_sha256": self.dependency_graph_sha256,
            "authorized_at": self.authorized_at.isoformat(),
            "scheduler_enabled": self.scheduler_enabled,
            "notification_enabled": self.notification_enabled,
            "production_database_write": self.production_database_write,
            "action": self.action,
        }


def actual_offline_authorization_from_payload(payload: object) -> M5ActualOfflineAuthorization:
    if not isinstance(payload, dict):
        raise ValueError("Actual offline authorization must be an object")
    data = dict(payload)
    authorization = M5ActualOfflineAuthorization(
        authorization_id=_required_text(data["authorization_id"], "authorization_id"),
        review_provenance=_required_text(data["review_provenance"], "review_provenance"),
        review_sha256=_required_text(data["review_sha256"], "review_sha256"),
        queue_sha256=_required_text(data["queue_sha256"], "queue_sha256"),
        dependency_graph_sha256=_required_text(data["dependency_graph_sha256"], "dependency_graph_sha256"),
        authorized_at=_required_datetime(datetime.fromisoformat(str(data["authorized_at"])), "authorized_at"),
        scheduler_enabled=data["scheduler_enabled"],
        notification_enabled=data["notification_enabled"],
        production_database_write=data["production_database_write"],
        action=str(data.get("action", ACTION_NO_ORDER)),
    )
    if set(data) != set(authorization.as_policy()):
        raise ValueError("Actual offline authorization keys do not match the schema")
    return authorization


def graph_sha256(graph: object) -> str:
    """Hash the exact serialized dependency graph used by a run."""
    if not hasattr(graph, "as_policy"):
        raise ValueError("Actual offline authorization requires a dependency graph")
    payload = graph.as_policy()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def require_actual_offline_authorization(
    *,
    namespace: str,
    authorization: M5ActualOfflineAuthorization | None,
    graph: object,
) -> None:
    if namespace == NAMESPACE_SIMULATED:
        if authorization is not None:
            raise ValueError("Simulated M5 runs cannot carry actual authorization")
        return
    if namespace != NAMESPACE_ACTUAL:
        raise ValueError("Unknown M5 run namespace")
    if authorization is None:
        raise ValueError("ACTUAL offline M5 runs require explicit authorization")
    if authorization.dependency_graph_sha256 != graph_sha256(graph):
        raise ValueError("Actual offline authorization dependency graph hash does not match")
