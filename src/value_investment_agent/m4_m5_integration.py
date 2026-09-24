"""M4/M5 joint read model for portfolio artifacts and event invalidation.

This module does not recalculate portfolio risk, position ceilings, dividend
income or an investment decision. It projects already-computed M4 baselines
through the bounded M5 dependency invalidation result so the user can see which
portfolio artifacts need recalculation and which event caused the pause.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
    NAMESPACE_SIMULATED,
    SEVERITY_CRITICAL,
)
from .m5_event_dependencies import DEPENDENCY_KINDS, DependencyGraph
from .m5_event_run import M5EventRunReceipt


SCHEMA_VERSION = "m4-m5-integration-v1"

STATUS_READY = "READY"
STATUS_PARTIAL = "PARTIAL"
STATUS_PAUSED = "PAUSED"
STATUS_NEGATIVE = "NEGATIVE"
INTEGRATION_STATUSES = frozenset(
    {STATUS_READY, STATUS_PARTIAL, STATUS_PAUSED, STATUS_NEGATIVE}
)
VALID_BASELINE_STATUSES = frozenset({STATUS_READY, STATUS_PARTIAL})

_FORBIDDEN_PUBLIC_KEYS = {
    "buy",
    "sell",
    "target_weight",
    "position_size",
    "order_quantity",
    "proposed_entry",
    "live_eligible",
}


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _required_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value


def _reject_public_execution_keys(value: Mapping[str, Any]) -> None:
    forbidden = sorted(_FORBIDDEN_PUBLIC_KEYS & set(value))
    if forbidden:
        raise ValueError(f"Integration payload contains execution keys: {', '.join(forbidden)}")


@dataclass(frozen=True)
class M4M5ArtifactDefinition:
    """Identity and dependency nodes for one portfolio or research artifact."""

    artifact_id: str
    kind: str
    symbol: str
    node_ids: tuple[str, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _required_text(self.artifact_id, "artifact_id"),
        )
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        if self.kind not in DEPENDENCY_KINDS:
            raise ValueError(f"Unknown integration artifact kind: {self.kind}")
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        object.__setattr__(
            self,
            "node_ids",
            tuple(_required_text(item, "node_id") for item in self.node_ids),
        )
        if not self.node_ids or len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("Integration artifact requires unique dependency nodes")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Integration artifact definition must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "symbol": self.symbol,
            "node_ids": list(self.node_ids),
            "action": self.action,
        }


@dataclass(frozen=True)
class M4M5ArtifactState:
    """Read-only projection of baseline and event invalidation state."""

    artifact_id: str
    kind: str
    symbol: str
    baseline_status: str
    invalidated_node_ids: tuple[str, ...]
    deferred_node_ids: tuple[str, ...]
    triggering_event_ids: tuple[str, ...]
    status: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _required_text(self.artifact_id, "artifact_id"),
        )
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        if self.baseline_status not in VALID_BASELINE_STATUSES:
            raise ValueError("Unknown integration baseline status")
        if self.status not in INTEGRATION_STATUSES:
            raise ValueError("Unknown integration artifact status")
        object.__setattr__(
            self,
            "invalidated_node_ids",
            tuple(_required_text(item, "invalidated_node_id") for item in self.invalidated_node_ids),
        )
        object.__setattr__(
            self,
            "deferred_node_ids",
            tuple(_required_text(item, "deferred_node_id") for item in self.deferred_node_ids),
        )
        object.__setattr__(
            self,
            "triggering_event_ids",
            tuple(_required_text(item, "triggering_event_id") for item in self.triggering_event_ids),
        )
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Integration artifact state must remain no_order")
        if self.status == STATUS_NEGATIVE and not self.triggering_event_ids:
            raise ValueError("NEGATIVE integration artifact requires a triggering event")
        if self.status == STATUS_PAUSED and not self.invalidated_node_ids:
            raise ValueError("PAUSED integration artifact requires invalidated nodes")

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "symbol": self.symbol,
            "baseline_status": self.baseline_status,
            "invalidated_node_ids": list(self.invalidated_node_ids),
            "deferred_node_ids": list(self.deferred_node_ids),
            "triggering_event_ids": list(self.triggering_event_ids),
            "status": self.status,
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload


@dataclass(frozen=True)
class M4M5IntegrationResult:
    """Immutable joint M4/M5 read result."""

    result_id: str
    namespace: str
    generated_at: datetime
    receipt: M5EventRunReceipt
    graph: DependencyGraph
    artifacts: tuple[M4M5ArtifactState, ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "result_id", _required_text(self.result_id, "result_id"))
        if self.namespace != NAMESPACE_SIMULATED:
            raise ValueError("Public M4/M5 integration accepts SIMULATED only")
        object.__setattr__(
            self,
            "generated_at",
            _required_datetime(self.generated_at, "generated_at"),
        )
        if not isinstance(self.receipt, M5EventRunReceipt):
            raise ValueError("receipt must be an M5EventRunReceipt")
        if not isinstance(self.graph, DependencyGraph):
            raise ValueError("graph must be a DependencyGraph")
        if self.action != ACTION_NO_ORDER:
            raise ValueError("M4/M5 integration must remain no_order")

    def artifact(self, artifact_id: str) -> M4M5ArtifactState:
        for artifact in self.artifacts:
            if artifact.artifact_id == artifact_id:
                return artifact
        raise ValueError(f"Unknown integration artifact: {artifact_id}")

    def affected_artifact_count(self) -> int:
        return sum(
            artifact.status in {STATUS_PAUSED, STATUS_NEGATIVE}
            or bool(artifact.deferred_node_ids)
            for artifact in self.artifacts
        )

    def as_policy(self) -> dict[str, Any]:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "result_id": self.result_id,
            "namespace": self.namespace,
            "generated_at": self.generated_at.isoformat(),
            "receipt": self.receipt.as_policy(),
            "graph": self.graph.as_policy(),
            "artifacts": [artifact.as_policy() for artifact in self.artifacts],
            "action": self.action,
        }
        _reject_public_execution_keys(payload)
        return payload


def integration_artifact_definition_from_payload(
    payload: Mapping[str, Any],
) -> M4M5ArtifactDefinition:
    data = dict(payload)
    return M4M5ArtifactDefinition(
        artifact_id=str(data["artifact_id"]),
        kind=str(data["kind"]),
        symbol=str(data["symbol"]),
        node_ids=tuple(str(item) for item in data.get("node_ids") or ()),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def _events_by_id(receipt: M5EventRunReceipt) -> dict[str, Any]:
    return {event.event_id: event for event in receipt.active_events}


def _invalidations_by_node(
    receipt: M5EventRunReceipt,
    events: Mapping[str, Any],
) -> dict[str, tuple[Any, ...]]:
    result: dict[str, dict[str, Any]] = {}
    for invalidation in receipt.invalidations:
        event = events.get(invalidation.event_id)
        if event is None:
            raise ValueError(f"Invalidation references an inactive event: {invalidation.event_id}")
        for item in invalidation.affected_nodes:
            result.setdefault(item.node_id, {})[event.event_id] = event
    return {
        node_id: tuple(events.values())
        for node_id, events in result.items()
    }


def _node_matches_event_symbol(node_symbol: str, event_symbol: str) -> bool:
    if node_symbol == "*":
        return True
    if event_symbol == "SYSTEM":
        return node_symbol == "SYSTEM"
    return node_symbol == event_symbol


def _validate_invalidation(
    *,
    invalidation: Any,
    event: Any,
    graph: DependencyGraph,
    graph_nodes: Mapping[str, Any],
) -> None:
    if invalidation.event_id != event.event_id:
        raise ValueError("Invalidation event identity does not match its event")
    if invalidation.event_type != event.event_type:
        raise ValueError("Invalidation event type does not match its event")
    if invalidation.symbol != event.symbol:
        raise ValueError("Invalidation symbol does not match its event")
    if invalidation.policy_version != graph.schema_version:
        raise ValueError("Invalidation policy version does not match the graph")
    items = invalidation.affected_nodes
    node_ids = tuple(item.node_id for item in items)
    if len(node_ids) != len(set(node_ids)):
        raise ValueError("Invalidation contains duplicate affected nodes")
    deferred_ids = tuple(invalidation.deferred_node_ids)
    if len(deferred_ids) != len(set(deferred_ids)):
        raise ValueError("Invalidation contains duplicate deferred nodes")
    if set(node_ids) & set(deferred_ids):
        raise ValueError("Affected and deferred invalidation nodes overlap")
    if invalidation.truncated != bool(deferred_ids):
        raise ValueError("Invalidation truncation flag does not match deferred nodes")
    for item in items:
        node = graph_nodes.get(item.node_id)
        if node is None:
            raise ValueError("Invalidation references a node outside the graph")
        if item.kind != node.kind:
            raise ValueError("Invalidation node kind does not match the graph")
        if not _node_matches_event_symbol(node.symbol, event.symbol):
            raise ValueError("Invalidation crosses event and graph symbols")
    for node_id in deferred_ids:
        node = graph_nodes.get(node_id)
        if node is None:
            raise ValueError("Deferred invalidation references a node outside the graph")
        if not _node_matches_event_symbol(node.symbol, event.symbol):
            raise ValueError("Deferred invalidation crosses event and graph symbols")


def _status_for(
    baseline_status: str,
    events: tuple[Any, ...],
    invalidated_node_ids: tuple[str, ...],
    deferred_node_ids: tuple[str, ...],
) -> str:
    if any(
        event.event_type == EVENT_TYPE_THESIS_BREAKER_TRIGGERED
        or event.severity == SEVERITY_CRITICAL
        for event in events
    ):
        return STATUS_NEGATIVE
    if invalidated_node_ids:
        return STATUS_PAUSED
    if deferred_node_ids:
        return STATUS_PARTIAL
    return baseline_status


def _symbol_is_compatible(artifact_symbol: str, node_symbol: str) -> bool:
    if node_symbol == "*":
        return True
    if artifact_symbol == "*":
        return node_symbol in {"*", "SYSTEM"}
    return artifact_symbol == node_symbol


def build_m4_m5_integration(
    *,
    receipt: M5EventRunReceipt,
    graph: DependencyGraph,
    artifacts: Sequence[M4M5ArtifactDefinition],
    baseline_statuses: Mapping[str, str],
    generated_at: datetime,
) -> M4M5IntegrationResult:
    """Project bounded event invalidations onto M4 and research artifacts."""

    generated_at = _required_datetime(generated_at, "generated_at")
    if receipt.namespace != NAMESPACE_SIMULATED:
        raise ValueError("Public M4/M5 integration requires a simulated receipt")
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("M4/M5 integration receipt must remain no_order")
    if generated_at < receipt.generated_at:
        raise ValueError("M4/M5 integration cannot precede its receipt")

    graph_nodes = {node.node_id: node for node in graph.nodes()}
    definitions = tuple(artifacts)
    if not definitions:
        raise ValueError("M4/M5 integration requires artifact definitions")
    if len({item.artifact_id for item in definitions}) != len(definitions):
        raise ValueError("M4/M5 integration artifact ids must be unique")
    for definition in definitions:
        missing = sorted(set(definition.node_ids) - set(graph_nodes))
        if missing:
            raise ValueError(
                f"Integration artifact {definition.artifact_id} references missing nodes: {', '.join(missing)}"
            )
        for node_id in definition.node_ids:
            node = graph_nodes[node_id]
            if node.kind != definition.kind:
                raise ValueError(
                    f"Integration artifact {definition.artifact_id} maps {node_id} "
                    f"to kind {node.kind}, expected {definition.kind}"
                )
            if not _symbol_is_compatible(definition.symbol, node.symbol):
                raise ValueError(
                    f"Integration artifact {definition.artifact_id} maps {node_id} "
                    f"to symbol {node.symbol}, expected {definition.symbol}"
                )
        if definition.artifact_id not in baseline_statuses:
            raise ValueError(
                f"Missing baseline status for integration artifact {definition.artifact_id}"
            )

    events = _events_by_id(receipt)
    invalidations = _invalidations_by_node(receipt, events)
    states: list[M4M5ArtifactState] = []
    deferred_by_node: dict[str, list[Any]] = {}
    for invalidation in receipt.invalidations:
        event = events.get(invalidation.event_id)
        if event is None:
            raise ValueError(
                f"Invalidation references an inactive event: {invalidation.event_id}"
            )
        _validate_invalidation(
            invalidation=invalidation,
            event=event,
            graph=graph,
            graph_nodes=graph_nodes,
        )
        for node_id in invalidation.deferred_node_ids:
            deferred_by_node.setdefault(node_id, []).append(event)
    for definition in definitions:
        baseline = str(baseline_statuses[definition.artifact_id])
        if baseline not in VALID_BASELINE_STATUSES:
            raise ValueError(
                f"Invalid baseline status for integration artifact {definition.artifact_id}: {baseline}"
            )
        invalidated_nodes = tuple(
            node_id for node_id in definition.node_ids if node_id in invalidations
        )
        deferred_nodes = tuple(
            node_id for node_id in definition.node_ids if node_id in deferred_by_node
        )
        relevant_events: list[Any] = []
        for node_id in invalidated_nodes:
            relevant_events.extend(invalidations[node_id])
        for node_id in deferred_nodes:
            relevant_events.extend(deferred_by_node[node_id])
        event_catalog = {
            event.event_id: event
            for event in relevant_events
        }
        relevant_events = list(event_catalog.values())
        states.append(
            M4M5ArtifactState(
                artifact_id=definition.artifact_id,
                kind=definition.kind,
                symbol=definition.symbol,
                baseline_status=baseline,
                invalidated_node_ids=invalidated_nodes,
                deferred_node_ids=deferred_nodes,
                triggering_event_ids=tuple(
                    event.source_event_id for event in relevant_events
                ),
                status=_status_for(
                    baseline,
                    tuple(relevant_events),
                    invalidated_nodes,
                    deferred_nodes,
                ),
                action=ACTION_NO_ORDER,
            )
        )

    identity_payload = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": receipt.receipt_id,
        "state_sha256": receipt.state_sha256,
        "generated_at": generated_at.isoformat(),
        "graph": graph.as_policy(),
        "artifacts": [artifact.as_policy() for artifact in states],
    }
    result_id = "m4m5-" + hashlib.sha256(
        json.dumps(
            identity_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()[:32]
    return M4M5IntegrationResult(
        result_id=result_id,
        namespace=NAMESPACE_SIMULATED,
        generated_at=generated_at,
        receipt=receipt,
        graph=graph,
        artifacts=tuple(states),
        action=ACTION_NO_ORDER,
    )
