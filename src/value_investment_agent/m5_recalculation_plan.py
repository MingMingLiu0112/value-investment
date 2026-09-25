"""Derive fail-closed bounded recalculation work from an M5 receipt.

The plan is read-only.  It never recalculates a model or changes a decision;
it makes the prerequisite chain explicit so an invalidated valuation cannot be
mistaken for a refreshed one.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping

from .investment_decision import ACTION_NO_ORDER
from .m5_event_dependencies import DEPENDENCY_KINDS, DependencyGraph
from .m5_event_run import M5EventRunReceipt


PLAN_SCHEMA = "m5-bounded-recalculation-plan-v1"
STATUS_BLOCKED_GRAPH_GAP = "BLOCKED_GRAPH_GAP"
STATUS_EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
STATUS_REVIEW_REQUIRED = "REVIEW_REQUIRED"
TASK_STATUSES = frozenset({
    STATUS_BLOCKED_GRAPH_GAP,
    STATUS_EVIDENCE_REQUIRED,
    STATUS_REVIEW_REQUIRED,
})


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _sha(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoundedRecalculationTask:
    task_id: str
    symbol: str
    event_ids: tuple[str, ...]
    dependency_kind: str
    node_ids: tuple[str, ...]
    status: str
    blockers: tuple[str, ...]
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "task_id", _text(self.task_id, "task_id"))
        object.__setattr__(self, "symbol", _text(self.symbol, "symbol"))
        object.__setattr__(self, "event_ids", tuple(_text(item, "event_id") for item in self.event_ids))
        object.__setattr__(self, "dependency_kind", _text(self.dependency_kind, "dependency_kind"))
        if self.dependency_kind not in DEPENDENCY_KINDS:
            raise ValueError("Unknown dependency kind")
        object.__setattr__(self, "node_ids", tuple(_text(item, "node_id") for item in self.node_ids))
        if self.status not in TASK_STATUSES:
            raise ValueError("Unknown recalculation task status")
        object.__setattr__(self, "blockers", tuple(_text(item, "blocker") for item in self.blockers))
        object.__setattr__(self, "evidence_refs", tuple(dict(item) for item in self.evidence_refs))
        if not self.event_ids or not self.evidence_refs:
            raise ValueError("Recalculation task requires event and evidence bindings")
        if self.status == STATUS_BLOCKED_GRAPH_GAP and self.node_ids:
            raise ValueError("Graph-gap task cannot claim a dependency node")
        if self.status != STATUS_BLOCKED_GRAPH_GAP and not self.node_ids:
            raise ValueError("Mapped recalculation task requires dependency nodes")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Recalculation task must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "symbol": self.symbol,
            "event_ids": list(self.event_ids),
            "dependency_kind": self.dependency_kind,
            "node_ids": list(self.node_ids),
            "status": self.status,
            "blockers": list(self.blockers),
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class BoundedRecalculationPlan:
    plan_id: str
    generated_at: datetime
    receipt_id: str
    receipt_sha256: str
    graph_sha256: str
    tasks: tuple[BoundedRecalculationTask, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "plan_id", _text(self.plan_id, "plan_id"))
        if self.generated_at.tzinfo is None:
            raise ValueError("generated_at must include a timezone")
        object.__setattr__(self, "receipt_id", _text(self.receipt_id, "receipt_id"))
        object.__setattr__(self, "receipt_sha256", _text(self.receipt_sha256, "receipt_sha256"))
        object.__setattr__(self, "graph_sha256", _text(self.graph_sha256, "graph_sha256"))
        object.__setattr__(self, "tasks", tuple(self.tasks))
        if not self.tasks:
            raise ValueError("Recalculation plan requires at least one task")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Recalculation plan must remain no_order")

    @property
    def blocked(self) -> bool:
        return any(task.status == STATUS_BLOCKED_GRAPH_GAP for task in self.tasks)

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": PLAN_SCHEMA,
            "plan_id": self.plan_id,
            "generated_at": self.generated_at.isoformat(),
            "receipt_id": self.receipt_id,
            "receipt_sha256": self.receipt_sha256,
            "graph_sha256": self.graph_sha256,
            "tasks": [item.as_policy() for item in self.tasks],
            "blocked": self.blocked,
            "action": self.action,
        }


def build_bounded_recalculation_plan(
    *, receipt: M5EventRunReceipt, graph: DependencyGraph, generated_at: datetime,
) -> BoundedRecalculationPlan:
    """Expose the exact evidence prerequisite for every invalidated kind."""
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("Receipt must remain no_order")
    if generated_at.tzinfo is None or generated_at < receipt.generated_at:
        raise ValueError("Plan cannot precede its receipt")
    nodes_by_kind: dict[tuple[str, str], list[str]] = {}
    for node in graph.nodes():
        nodes_by_kind.setdefault((node.symbol, node.kind), []).append(node.node_id)
    event_by_id = {event.event_id: event for event in receipt.active_events}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for invalidation in receipt.invalidations:
        event = event_by_id.get(invalidation.event_id)
        if event is None:
            raise ValueError("Invalidation references inactive event")
        direct = event.current_state.get("direct_dependency_kinds") or ()
        for kind in direct:
            kind = _text(kind, "direct dependency kind")
            if kind not in DEPENDENCY_KINDS:
                raise ValueError("Event contains unknown direct dependency kind")
            key = (event.symbol, kind)
            entry = grouped.setdefault(key, {"events": {}, "refs": {}})
            entry["events"][event.event_id] = event
            for ref in event.evidence_refs:
                entry["refs"][str(ref["id"])] = dict(ref)
    tasks = []
    for (symbol, kind), entry in sorted(grouped.items()):
        node_ids = tuple(sorted(
            (*nodes_by_kind.get((symbol, kind), ()), *nodes_by_kind.get(("*", kind), ()))
        ))
        event_ids = tuple(sorted(entry["events"]))
        status = STATUS_EVIDENCE_REQUIRED if kind == "financial_facts" else STATUS_REVIEW_REQUIRED
        blockers: tuple[str, ...] = ()
        if not node_ids:
            status = STATUS_BLOCKED_GRAPH_GAP
            blockers = (f"missing_dependency_node:{kind}",)
        task_payload = {"receipt_id": receipt.receipt_id, "symbol": symbol, "kind": kind, "events": event_ids}
        tasks.append(BoundedRecalculationTask(
            task_id="m5-recalc-" + _sha(task_payload)[:32], symbol=symbol,
            event_ids=event_ids, dependency_kind=kind, node_ids=node_ids,
            status=status, blockers=blockers,
            evidence_refs=tuple(entry["refs"].values()),
        ))
    receipt_sha = receipt.state_sha256
    graph_sha = _sha(graph.as_policy())
    identity = {"receipt_id": receipt.receipt_id, "receipt_sha256": receipt_sha, "graph_sha256": graph_sha, "tasks": [item.as_policy() for item in tasks]}
    return BoundedRecalculationPlan(
        plan_id="m5-recalc-plan-" + _sha(identity)[:32], generated_at=generated_at,
        receipt_id=receipt.receipt_id, receipt_sha256=receipt_sha,
        graph_sha256=graph_sha, tasks=tuple(tasks),
    )


def bounded_recalculation_plan_from_payload(payload: Mapping[str, Any]) -> BoundedRecalculationPlan:
    if payload.get("schema_version") != PLAN_SCHEMA:
        raise ValueError("Unsupported recalculation plan schema")
    tasks = tuple(BoundedRecalculationTask(
        task_id=item["task_id"], symbol=item["symbol"],
        event_ids=tuple(item["event_ids"]), dependency_kind=item["dependency_kind"],
        node_ids=tuple(item["node_ids"]), status=item["status"],
        blockers=tuple(item["blockers"]), evidence_refs=tuple(item["evidence_refs"]),
        action=item["action"],
    ) for item in payload["tasks"])
    plan = BoundedRecalculationPlan(
        plan_id=payload["plan_id"], generated_at=datetime.fromisoformat(payload["generated_at"]),
        receipt_id=payload["receipt_id"], receipt_sha256=payload["receipt_sha256"],
        graph_sha256=payload["graph_sha256"], tasks=tasks, action=payload["action"],
    )
    if dict(payload) != plan.as_policy():
        raise ValueError("Recalculation plan payload is not canonical")
    return plan
