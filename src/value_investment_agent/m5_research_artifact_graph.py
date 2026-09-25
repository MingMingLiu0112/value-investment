"""Build a bounded M5 dependency graph from pinned research artifacts.

The adapter deliberately accepts the immutable runtime-import candidates rather
than filenames or mutable ``latest`` pointers.  It represents recalculation
dependencies, not a new valuation model or a claim that a recalculation has
already produced a replacement value.
"""
from __future__ import annotations

from typing import Iterable

from .m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_DIVIDEND_SUSTAINABILITY,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_PRICE_BRIDGE,
    KIND_THESIS,
    KIND_VALUATION_INPUTS,
    KIND_VALUATION_RESULT,
    DependencyGraph,
    DependencyNode,
)
from .research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_FINANCIAL_FACTS,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_RESULT,
)
from .research_runtime_import import RuntimeArtifactCandidate
from .research_input import ResearchInputDescriptor, descriptor_sha256
from .m5_event_run import M5EventRunReceipt
from .valuation_assumptions import STATUS_READY
from .valuation_router import ROUTE_SUPPORTED, route_profile


_KIND_BY_ARTIFACT = {
    ARTIFACT_FINANCIAL_FACTS: KIND_FACTS,
    ARTIFACT_RESEARCH_CASE: KIND_THESIS,
    ARTIFACT_RESEARCH_GATE: KIND_DECISION_REVIEW,
    ARTIFACT_VALUATION_RESULT: KIND_VALUATION_RESULT,
    ARTIFACT_MODEL_VALIDITY: KIND_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE: KIND_PRICE_BRIDGE,
    ARTIFACT_DIVIDEND_RESEARCH: KIND_DIVIDEND_SUSTAINABILITY,
    ARTIFACT_CURRENT_RESEARCH_STATUS: KIND_CURRENT_STATUS,
}

_UPSTREAM_TYPES = {
    ARTIFACT_RESEARCH_GATE: (ARTIFACT_RESEARCH_CASE,),
    ARTIFACT_VALUATION_RESULT: (ARTIFACT_RESEARCH_CASE,),
    ARTIFACT_MODEL_VALIDITY: (ARTIFACT_VALUATION_RESULT,),
    ARTIFACT_PRICE_BRIDGE: (ARTIFACT_VALUATION_RESULT, ARTIFACT_MODEL_VALIDITY),
    ARTIFACT_DIVIDEND_RESEARCH: (ARTIFACT_RESEARCH_CASE,),
    ARTIFACT_CURRENT_RESEARCH_STATUS: (
        ARTIFACT_RESEARCH_GATE,
        ARTIFACT_VALUATION_RESULT,
        ARTIFACT_MODEL_VALIDITY,
        ARTIFACT_PRICE_BRIDGE,
        ARTIFACT_DIVIDEND_RESEARCH,
    ),
}


def _node_id(candidate: RuntimeArtifactCandidate) -> str:
    return f"artifact:{candidate.symbol}:{candidate.artifact_type}:{candidate.source_sha256}"


def build_research_artifact_dependency_graph(
    candidates: Iterable[RuntimeArtifactCandidate],
    *,
    symbol: str,
) -> DependencyGraph:
    """Return a graph for one security from hash-pinned imported artifacts.

    Unknown artifact types are intentionally excluded. Required upstream types
    must exist exactly once; callers cannot silently run a partial graph.
    """
    selected = tuple(
        candidate
        for candidate in candidates
        if candidate.symbol == symbol and candidate.artifact_type in _KIND_BY_ARTIFACT
    )
    by_type = {candidate.artifact_type: candidate for candidate in selected}
    if len(by_type) != len(selected):
        raise ValueError("Research artifact graph has duplicate artifact types")
    if not by_type:
        raise ValueError("Research artifact graph has no supported artifacts")

    nodes: list[DependencyNode] = []
    for artifact_type, candidate in sorted(by_type.items()):
        upstream = _UPSTREAM_TYPES.get(artifact_type, ())
        missing = tuple(item for item in upstream if item not in by_type)
        if missing:
            raise ValueError(
                f"Research artifact graph is missing upstream artifacts for {artifact_type}: {missing}"
            )
        nodes.append(
            DependencyNode(
                node_id=_node_id(candidate),
                kind=_KIND_BY_ARTIFACT[artifact_type],
                symbol=symbol,
                inputs=tuple(_node_id(by_type[item]) for item in upstream),
                version=candidate.source_sha256,
                evidence_refs=candidate.evidence_refs,
            )
        )
    return DependencyGraph(nodes)


def attach_valuation_input_descriptor(
    *, graph: DependencyGraph, descriptor: ResearchInputDescriptor,
    receipt: M5EventRunReceipt,
) -> DependencyGraph:
    """Register complete event-bound model inputs without promoting pending research."""
    if receipt.namespace != "ACTUAL" or receipt.action != "no_order":
        raise ValueError("Valuation inputs require an ACTUAL no-order receipt")
    if (descriptor.input_sha256 is None
        or descriptor.input_sha256 != descriptor_sha256(descriptor)
        or descriptor.blockers or not getattr(descriptor.facts, "verified", False)
        or getattr(descriptor.facts, "blockers", ())
        or descriptor.assumptions is None
        or descriptor.assumptions.status != STATUS_READY
        or descriptor.assumptions.blockers):
        raise ValueError("Valuation input descriptor is incomplete or not hash-bound")
    route = route_profile(descriptor.profile_id, descriptor.requested_model)
    if route.status != ROUTE_SUPPORTED or not isinstance(descriptor.facts, route.facts_contract):
        raise ValueError("Valuation input model route does not accept these facts")
    preflight = route.build_model().value(descriptor.facts, descriptor.research_case)
    if (preflight.status == "not_ready"
        or preflight.blockers
        or any(value is None for value in (
            preflight.bear_value, preflight.base_value, preflight.bull_value,
        ))):
        raise ValueError("Valuation input model preflight remains not ready")
    if descriptor.point_in_time.available_at < receipt.generated_at:
        raise ValueError("Valuation inputs precede the ACTUAL event receipt")
    if {event.symbol for event in receipt.active_events} != {descriptor.symbol}:
        raise ValueError("Valuation input security does not match ACTUAL events")
    facts_nodes = [node for node in graph.nodes()
                   if node.symbol == descriptor.symbol and node.kind == KIND_FACTS]
    thesis_nodes = [node for node in graph.nodes()
                    if node.symbol == descriptor.symbol and node.kind == KIND_THESIS]
    if len(facts_nodes) != 1 or len(thesis_nodes) != 1:
        raise ValueError("Valuation inputs require exactly one facts and thesis node")
    if any(node.symbol == descriptor.symbol and node.kind == KIND_VALUATION_INPUTS
           for node in graph.nodes()):
        raise ValueError("Valuation inputs already have a dependency node")
    source_hashes = {source.sha256 for source in descriptor.sources}
    source_locations = {(source.sha256, source.location) for source in descriptor.sources}
    if facts_nodes[0].version not in source_hashes or receipt.state_sha256 not in source_hashes:
        raise ValueError("Valuation inputs are not bound to facts and ACTUAL receipt bytes")
    for event in receipt.active_events:
        pdf_refs = [ref for ref in event.evidence_refs
                    if ref.get("sha256") and ref.get("source_url")]
        if (len(pdf_refs) != 1
            or (pdf_refs[0]["sha256"], pdf_refs[0]["source_url"]) not in source_locations):
            raise ValueError("Valuation inputs do not cover every ACTUAL event PDF")
    evidence_refs = tuple({"id": source.id, "sha256": source.sha256,
                           "source_url": source.location}
                          for source in descriptor.sources)
    node = DependencyNode(
        node_id=f"descriptor:{descriptor.symbol}:valuation_inputs:{descriptor.input_sha256}",
        kind=KIND_VALUATION_INPUTS, symbol=descriptor.symbol,
        inputs=(facts_nodes[0].node_id, thesis_nodes[0].node_id),
        version=descriptor.input_sha256, evidence_refs=evidence_refs,
    )
    return DependencyGraph((*graph.nodes(), node))
