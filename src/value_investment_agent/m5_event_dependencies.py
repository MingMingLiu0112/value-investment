"""M5 dependency invalidation and bounded recalculation plans."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .investment_decision import ACTION_NO_ORDER
from .m5_event_core import (
    M5_EVENT_SCHEMA,
    _digest,
    _required_int,
    _required_refs,
    _required_text,
    ChangeEvent,
    EVENT_TYPE_CAPITAL_ALLOCATION_CHANGE,
    EVENT_TYPE_DIVIDEND_CHANGE,
    EVENT_TYPE_MATERIAL_ANNOUNCEMENT,
    EVENT_TYPE_MODEL_STALE,
    EVENT_TYPE_NEW_FINANCIAL_REPORT,
    EVENT_TYPE_POSITION_RISK_CHANGED,
    EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED,
    EVENT_TYPE_SOURCE_SCAN_FAILED,
    EVENT_TYPE_SOURCE_SCAN_RECOVERED,
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED,
    EVENT_TYPE_THESIS_WEAKENED,
    EVENT_TYPE_VALUATION_ZONE_CHANGED,
)


KIND_FACTS = "financial_facts"
KIND_VALUATION_INPUTS = "valuation_inputs"
KIND_DISTRIBUTION_HISTORY = "distribution_history"
KIND_MODEL_VALIDITY = "model_validity"
KIND_THESIS = "research_thesis"
KIND_ENTRY_CONSISTENCY = "entry_consistency"
KIND_DECISION_REVIEW = "decision_review"
KIND_PRICE_ATTRACTIVENESS = "price_attractiveness"
KIND_CURRENT_STATUS = "current_research_status"
KIND_PORTFOLIO_RISK = "portfolio_risk"
KIND_POSITION_GUIDANCE = "position_guidance"
KIND_DIVIDEND_SUSTAINABILITY = "dividend_sustainability"
KIND_SOURCE_HEALTH = "source_health"
KIND_VALUATION_RESULT = "valuation_result"
KIND_PRICE_BRIDGE = "price_bridge"

DEPENDENCY_KINDS = frozenset(
    {
        KIND_FACTS,
        KIND_VALUATION_INPUTS,
        KIND_DISTRIBUTION_HISTORY,
        KIND_MODEL_VALIDITY,
        KIND_THESIS,
        KIND_ENTRY_CONSISTENCY,
        KIND_DECISION_REVIEW,
        KIND_PRICE_ATTRACTIVENESS,
        KIND_CURRENT_STATUS,
        KIND_PORTFOLIO_RISK,
        KIND_POSITION_GUIDANCE,
        KIND_DIVIDEND_SUSTAINABILITY,
        KIND_SOURCE_HEALTH,
        KIND_VALUATION_RESULT,
        KIND_PRICE_BRIDGE,
    }
)

_EVENT_POLICY: dict[str, tuple[str, ...]] = {
    EVENT_TYPE_NEW_FINANCIAL_REPORT: (
        KIND_FACTS,
        KIND_VALUATION_INPUTS,
        KIND_DISTRIBUTION_HISTORY,
        KIND_MODEL_VALIDITY,
        KIND_DIVIDEND_SUSTAINABILITY,
    ),
    EVENT_TYPE_MATERIAL_ANNOUNCEMENT: (
        KIND_MODEL_VALIDITY,
        KIND_THESIS,
        KIND_DECISION_REVIEW,
        KIND_VALUATION_INPUTS,
    ),
    EVENT_TYPE_DIVIDEND_CHANGE: (
        KIND_DISTRIBUTION_HISTORY,
        KIND_DIVIDEND_SUSTAINABILITY,
        KIND_POSITION_GUIDANCE,
    ),
    EVENT_TYPE_CAPITAL_ALLOCATION_CHANGE: (
        KIND_FACTS,
        KIND_DISTRIBUTION_HISTORY,
        KIND_VALUATION_INPUTS,
        KIND_THESIS,
    ),
    EVENT_TYPE_VALUATION_ZONE_CHANGED: (KIND_PRICE_ATTRACTIVENESS, KIND_CURRENT_STATUS),
    EVENT_TYPE_PRICE_ATTRACTIVENESS_CHANGED: (KIND_PRICE_ATTRACTIVENESS, KIND_CURRENT_STATUS),
    EVENT_TYPE_THESIS_WEAKENED: (KIND_THESIS, KIND_DECISION_REVIEW, KIND_ENTRY_CONSISTENCY),
    EVENT_TYPE_THESIS_BREAKER_TRIGGERED: (
        KIND_THESIS,
        KIND_DECISION_REVIEW,
        KIND_ENTRY_CONSISTENCY,
        KIND_CURRENT_STATUS,
    ),
    EVENT_TYPE_MODEL_STALE: (KIND_MODEL_VALIDITY, KIND_PRICE_BRIDGE, KIND_CURRENT_STATUS),
    EVENT_TYPE_POSITION_RISK_CHANGED: (KIND_PORTFOLIO_RISK, KIND_POSITION_GUIDANCE),
    EVENT_TYPE_SOURCE_SCAN_FAILED: (KIND_SOURCE_HEALTH,),
    EVENT_TYPE_SOURCE_SCAN_RECOVERED: (KIND_SOURCE_HEALTH,),
}


@dataclass(frozen=True)
class DependencyNode:
    node_id: str
    kind: str
    symbol: str
    inputs: tuple[str, ...]
    version: str
    evidence_refs: tuple[dict[str, Any], ...]
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _required_text(self.node_id, "node_id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        if self.symbol not in {"SYSTEM", "*"} and not (
            len(self.symbol) == 6 and self.symbol.isdigit()
        ):
            raise ValueError("Dependency symbol must be SYSTEM, * or six digits")
        object.__setattr__(
            self,
            "inputs",
            tuple(_required_text(item, "input") for item in self.inputs),
        )
        if any(item == self.node_id for item in self.inputs):
            raise ValueError("Dependency node cannot depend on itself")
        object.__setattr__(self, "version", _required_text(self.version, "version"))
        object.__setattr__(self, "evidence_refs", _required_refs(self.evidence_refs))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Dependency node must remain no_order")

    def as_policy(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "symbol": self.symbol,
            "inputs": list(self.inputs),
            "version": self.version,
            "evidence_refs": [dict(item) for item in self.evidence_refs],
            "action": self.action,
        }


@dataclass(frozen=True)
class DependencyInvalidationItem:
    node_id: str
    kind: str
    depth: int
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_id", _required_text(self.node_id, "node_id"))
        object.__setattr__(self, "kind", _required_text(self.kind, "kind"))
        object.__setattr__(self, "depth", _required_int(self.depth, "depth"))
        if self.depth < 0:
            raise ValueError("Invalidation depth cannot be negative")
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))

    def as_policy(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "depth": self.depth,
            "reason": self.reason,
        }


class DependencyGraph:
    """Static dependency graph used to invalidate only affected artifacts."""

    def __init__(
        self,
        nodes: Iterable[DependencyNode],
        *,
        schema_version: str = M5_EVENT_SCHEMA,
    ) -> None:
        self.schema_version = schema_version
        self._nodes = tuple(nodes)
        by_id = {node.node_id: node for node in self._nodes}
        if len(by_id) != len(self._nodes):
            raise ValueError("Dependency graph contains duplicate node ids")
        for node in self._nodes:
            for input_id in node.inputs:
                if input_id not in by_id:
                    raise ValueError(f"Dependency input does not exist: {input_id}")
        self._dependents: dict[str, list[str]] = {
            node.node_id: [] for node in self._nodes
        }
        for node in self._nodes:
            for input_id in node.inputs:
                self._dependents[input_id].append(node.node_id)
        self._assert_acyclic()

    def nodes(self) -> tuple[DependencyNode, ...]:
        return self._nodes

    def node(self, node_id: str) -> DependencyNode:
        for item in self._nodes:
            if item.node_id == node_id:
                return item
        raise ValueError(f"Dependency node does not exist: {node_id}")

    def direct_nodes(
        self,
        event: ChangeEvent,
        *,
        kinds: Sequence[str] | None = None,
    ) -> tuple[DependencyNode, ...]:
        selected = tuple(kinds) if kinds is not None else _EVENT_POLICY.get(event.event_type, ())
        if any(kind not in DEPENDENCY_KINDS for kind in selected):
            raise ValueError("Unknown dependency kind in direct-node policy")
        return tuple(
            node
            for node in self._nodes
            if node.kind in selected
            and (
                node.symbol == event.symbol
                or node.symbol == "*"
                or (event.symbol == "SYSTEM" and node.symbol == "SYSTEM")
            )
        )

    def invalidate(
        self,
        event: ChangeEvent,
        *,
        direct_kinds: Sequence[str] | None = None,
        max_depth: int = 4,
        max_nodes: int = 20,
    ) -> "DependencyInvalidation":
        selected = tuple(direct_kinds) if direct_kinds is not None else None
        if selected is not None and any(
            kind not in DEPENDENCY_KINDS for kind in selected
        ):
            raise ValueError("Unknown dependency kind in invalidation policy")
        max_depth = _required_int(max_depth, "max_depth")
        max_nodes = _required_int(max_nodes, "max_nodes")
        if max_depth < 0:
            raise ValueError("max_depth cannot be negative")
        if max_nodes <= 0:
            raise ValueError("max_nodes must be positive")
        direct = self.direct_nodes(event, kinds=selected)
        visited: dict[str, DependencyInvalidationItem] = {}
        for node in direct:
            visited[node.node_id] = DependencyInvalidationItem(
                node_id=node.node_id,
                kind=node.kind,
                depth=0,
                reason=f"event_type={event.event_type}",
            )
        queue = [(node.node_id, 0) for node in direct]
        pointer = 0
        while pointer < len(queue):
            node_id, depth = queue[pointer]
            pointer += 1
            if depth >= max_depth:
                continue
            for dependent_id in self._dependents.get(node_id, ()):
                if dependent_id in visited:
                    continue
                parent = visited[node_id]
                visited[dependent_id] = DependencyInvalidationItem(
                    node_id=dependent_id,
                    kind=self.node(dependent_id).kind,
                    depth=depth + 1,
                    reason=f"depends_on={parent.node_id}",
                )
                queue.append((dependent_id, depth + 1))
        affected = tuple(
            sorted(
                visited.values(),
                key=lambda item: (item.depth, item.node_id),
            )
        )
        truncated = len(affected) > max_nodes
        kept = affected[:max_nodes] if truncated else affected
        deferred = tuple(item.node_id for item in affected[max_nodes:]) if truncated else ()
        return DependencyInvalidation(
            invalidation_id="m5-invalidation-" + _digest(
                "invalidation",
                event.event_id,
                self.schema_version,
                max_depth,
                max_nodes,
                tuple(selected) if selected is not None else (),
            )[:32],
            event_id=event.event_id,
            event_type=event.event_type,
            symbol=event.symbol,
            policy_version=self.schema_version,
            affected_nodes=kept,
            truncated=truncated,
            deferred_node_ids=deferred,
            reason=(
                f"Materiality policy {selected} followed through at most "
                f"{max_depth} dependency levels"
                if selected is not None
                else f"Direct policy {_EVENT_POLICY.get(event.event_type, ())} followed "
                f"through at most {max_depth} dependency levels"
            ),
        )

    def _assert_acyclic(self) -> None:
        state: dict[str, int] = {}

        def visit(node_id: str) -> None:
            state[node_id] = 1
            node = self.node(node_id)
            for input_id in node.inputs:
                marker = state.get(input_id, 0)
                if marker == 1:
                    raise ValueError(f"Dependency graph contains a cycle at {input_id}")
                if marker == 0:
                    visit(input_id)
            state[node_id] = 2

        for node in self._nodes:
            if state.get(node.node_id, 0) == 0:
                visit(node.node_id)

    def as_policy(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "nodes": [node.as_policy() for node in self._nodes],
        }


@dataclass(frozen=True)
class DependencyInvalidation:
    invalidation_id: str
    event_id: str
    event_type: str
    symbol: str
    policy_version: str
    affected_nodes: tuple[DependencyInvalidationItem, ...]
    truncated: bool
    deferred_node_ids: tuple[str, ...]
    reason: str
    action: str = ACTION_NO_ORDER

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "invalidation_id",
            _required_text(self.invalidation_id, "invalidation_id"),
        )
        object.__setattr__(self, "event_id", _required_text(self.event_id, "event_id"))
        object.__setattr__(self, "event_type", _required_text(self.event_type, "event_type"))
        object.__setattr__(self, "symbol", _required_text(self.symbol, "symbol"))
        object.__setattr__(
            self,
            "policy_version",
            _required_text(self.policy_version, "policy_version"),
        )
        object.__setattr__(
            self,
            "affected_nodes",
            tuple(
                item
                if isinstance(item, DependencyInvalidationItem)
                else DependencyInvalidationItem(**item)
                for item in self.affected_nodes
            ),
        )
        object.__setattr__(
            self,
            "deferred_node_ids",
            tuple(_required_text(item, "deferred_node_id") for item in self.deferred_node_ids),
        )
        if self.truncated and not self.deferred_node_ids:
            raise ValueError("Truncated invalidation must record deferred nodes")
        if not self.truncated and self.deferred_node_ids:
            raise ValueError("Non-truncated invalidation cannot defer nodes")
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        if self.action != ACTION_NO_ORDER:
            raise ValueError("Dependency invalidation must remain no_order")

    def recalculation_queue(self) -> tuple[DependencyInvalidationItem, ...]:
        return tuple(
            sorted(
                self.affected_nodes,
                key=lambda item: (item.depth, item.node_id),
            )
        )

    def affected_kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.kind for item in self.affected_nodes}))

    def as_policy(self) -> dict[str, Any]:
        return {
            "invalidation_id": self.invalidation_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "symbol": self.symbol,
            "policy_version": self.policy_version,
            "affected_nodes": [item.as_policy() for item in self.affected_nodes],
            "truncated": self.truncated,
            "deferred_node_ids": list(self.deferred_node_ids),
            "reason": self.reason,
            "action": self.action,
        }


def dependency_node_from_payload(payload: Mapping[str, Any]) -> DependencyNode:
    if not isinstance(payload, Mapping):
        raise ValueError("Dependency node must be an object")
    data = dict(payload)
    return DependencyNode(
        node_id=_required_text(data["node_id"], "node_id"),
        kind=_required_text(data["kind"], "kind"),
        symbol=_required_text(data["symbol"], "symbol"),
        inputs=tuple(str(item) for item in data.get("inputs") or ()),
        version=_required_text(data["version"], "version"),
        evidence_refs=_required_refs(data.get("evidence_refs")),
        action=str(data.get("action", ACTION_NO_ORDER)),
    )


def dependency_graph_from_payload(payload: Mapping[str, Any]) -> DependencyGraph:
    if not isinstance(payload, Mapping):
        raise ValueError("Dependency graph must be an object")
    data = dict(payload)
    return DependencyGraph(
        (
            dependency_node_from_payload(item)
            for item in data.get("nodes") or ()
        ),
        schema_version=_required_text(
            data.get("schema_version", M5_EVENT_SCHEMA),
            "schema_version",
        ),
    )
