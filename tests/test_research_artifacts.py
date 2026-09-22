from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import json

import pytest

from value_investment_agent.research_artifacts import (
    ARTIFACT_VALUATION_RESULT,
    SCOPE_BATCH,
    SCOPE_SECURITY,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    canonicalize_artifact_payload,
    parse_stored_artifact_payload,
    sha256_text,
)


def _identity(
    *,
    artifact_type: str = ARTIFACT_VALUATION_RESULT,
    scope_type: str = SCOPE_SECURITY,
    scope_key: str = "600519",
    as_of: date | None = date(2026, 9, 21),
) -> ResearchArtifactIdentity:
    return ResearchArtifactIdentity(
        scope_type=scope_type,
        scope_key=scope_key,
        artifact_type=artifact_type,
        schema_version="c3-artifact-v1",
        as_of=as_of,
        available_at=datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc),
    )


def test_canonical_payload_is_deterministic_and_sorts_keys():
    first = {
        "symbol": "600519",
        "value": Decimal("1.20"),
        "when": date(2026, 9, 21),
        "nested": {"b": 2, "a": 1},
    }
    second = {
        "nested": {"a": 1, "b": 2},
        "when": date(2026, 9, 21),
        "value": Decimal("1.20"),
        "symbol": "600519",
    }

    left = canonicalize_artifact_payload(first)
    right = canonicalize_artifact_payload(second)
    assert left == right
    assert sha256_text(left) == sha256_text(right)
    assert json.loads(left)["value"] == "1.20"


def test_envelope_builds_and_verifies_immutable_payload():
    envelope = ResearchArtifactEnvelope.build(
        identity=_identity(),
        payload={"symbol": "600519", "status": "conditional_research_only"},
        evidence_refs=[{"id": "evidence-1", "sha256": "a" * 64}],
        run_id="run-1",
    )
    assert envelope.payload_sha256 == envelope.verify_payload()
    assert len(envelope.natural_key()) == 64


def test_envelope_rejects_identity_conflicts_and_unknown_schema():
    with pytest.raises(ValueError, match="scope"):
        _identity(artifact_type=ARTIFACT_VALUATION_RESULT, scope_type=SCOPE_BATCH)
    with pytest.raises(ValueError, match="six-digit"):
        _identity(scope_key="600519.SH")
    with pytest.raises(ValueError, match="schema version"):
        ResearchArtifactIdentity(
            scope_type=SCOPE_SECURITY,
            scope_key="600519",
            artifact_type=ARTIFACT_VALUATION_RESULT,
            schema_version=" ",
            as_of=date(2026, 9, 21),
            available_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        )


def test_canonicalization_rejects_non_json_and_non_finite_numbers():
    with pytest.raises(ValueError, match="Unsupported"):
        canonicalize_artifact_payload({"value": object()})
    with pytest.raises(ValueError, match="finite"):
        canonicalize_artifact_payload({"value": Decimal("NaN")})
    with pytest.raises(ValueError, match="nonempty"):
        canonicalize_artifact_payload({})


def test_evidence_ids_must_be_named_and_unique():
    with pytest.raises(ValueError, match="named ids"):
        ResearchArtifactEnvelope.build(
            identity=_identity(),
            payload={"symbol": "600519"},
            evidence_refs=[{"sha256": "a" * 64}],
            run_id="run-1",
        )
    with pytest.raises(ValueError, match="unique"):
        ResearchArtifactEnvelope.build(
            identity=_identity(),
            payload={"symbol": "600519"},
            evidence_refs=[
                {"id": "same", "sha256": "a" * 64},
                {"id": "same", "sha256": "b" * 64},
            ],
            run_id="run-1",
        )


def test_hash_is_not_silently_accepted_when_payload_changes():
    original = ResearchArtifactEnvelope.build(
        identity=_identity(),
        payload={"symbol": "600519", "status": "not_ready"},
        run_id="run-1",
    )
    forged = object.__new__(ResearchArtifactEnvelope)
    object.__setattr__(forged, "identity", original.identity)
    object.__setattr__(forged, "canonical_payload", canonicalize_artifact_payload(
        {"symbol": "600519", "status": "ready"}
    ))
    object.__setattr__(forged, "payload_sha256", original.payload_sha256)
    object.__setattr__(forged, "evidence_refs", ())
    object.__setattr__(forged, "run_id", "run-1")
    with pytest.raises(ValueError, match="does not match"):
        ResearchArtifactEnvelope.__post_init__(forged)


def test_stored_payload_parser_recomputes_hash_before_returning_object():
    from value_investment_agent.research_artifacts import StoredResearchArtifact

    envelope = ResearchArtifactEnvelope.build(
        identity=_identity(),
        payload={"symbol": "600519", "values": [1, 2, 3]},
        run_id="run-1",
    )
    stored = StoredResearchArtifact(
        artifact_id="00000000-0000-0000-0000-000000000001",
        envelope=envelope,
        created_at=datetime(2026, 9, 21, 12, 1, tzinfo=timezone.utc),
    )
    assert parse_stored_artifact_payload(stored)["values"] == [1, 2, 3]
