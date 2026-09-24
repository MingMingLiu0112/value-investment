from types import SimpleNamespace

import pytest

from value_investment_agent.m5_research_artifact_graph import (
    build_research_artifact_dependency_graph,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_CURRENT_RESEARCH_STATUS,
    ARTIFACT_DIVIDEND_RESEARCH,
    ARTIFACT_MODEL_VALIDITY,
    ARTIFACT_PRICE_BRIDGE,
    ARTIFACT_RESEARCH_CASE,
    ARTIFACT_RESEARCH_GATE,
    ARTIFACT_VALUATION_RESULT,
)


def _candidate(artifact_type: str):
    return SimpleNamespace(
        symbol="600519",
        artifact_type=artifact_type,
        source_sha256=("a" * 63) + str(len(artifact_type) % 10),
        evidence_refs=({"id": f"evidence-{artifact_type}"},),
    )


def _candidates():
    return tuple(
        _candidate(item)
        for item in (
            ARTIFACT_RESEARCH_CASE,
            ARTIFACT_RESEARCH_GATE,
            ARTIFACT_VALUATION_RESULT,
            ARTIFACT_MODEL_VALIDITY,
            ARTIFACT_PRICE_BRIDGE,
            ARTIFACT_DIVIDEND_RESEARCH,
            ARTIFACT_CURRENT_RESEARCH_STATUS,
        )
    )


def test_graph_is_hash_pinned_and_reaches_current_status():
    graph = build_research_artifact_dependency_graph(_candidates(), symbol="600519")

    nodes = graph.nodes()
    assert len(nodes) == 7
    assert all(node.version.startswith("a") for node in nodes)
    status = next(node for node in nodes if node.kind == "current_research_status")
    assert len(status.inputs) == 5


def test_graph_refuses_missing_required_upstream_artifact():
    candidates = tuple(
        item for item in _candidates() if item.artifact_type != ARTIFACT_MODEL_VALIDITY
    )

    with pytest.raises(ValueError, match="missing upstream artifacts"):
        build_research_artifact_dependency_graph(candidates, symbol="600519")
