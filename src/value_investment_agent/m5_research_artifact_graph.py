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
