"""Portable, read-only evidence for replaying one in-memory research run."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Sequence

from ...research_artifacts import (
    ARTIFACT_DECISION_RECOMMENDATION,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
    StoredResearchArtifact,
)


BUNDLE_SCHEMA = "research-decision-artifact-bundle-v1"


def export_artifact_bundle(artifacts: Sequence[StoredResearchArtifact]) -> dict[str, Any]:
    return {
        "schema_version": BUNDLE_SCHEMA,
        "artifacts": [
            {
                "artifact_id": item.artifact_id,
                "identity": item.envelope.identity.as_dict(),
                "canonical_payload": item.envelope.canonical_payload,
                "payload_sha256": item.envelope.payload_sha256,
                "evidence_refs": [dict(ref) for ref in item.envelope.evidence_refs],
                "run_id": item.envelope.run_id,
                "created_at": item.created_at.isoformat(),
            }
            for item in artifacts
        ],
    }


class ReadOnlyArtifactBundleRepository:
    """Load exact artifact ids from an exported bundle without mutable heads."""

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        if bundle.get("schema_version") != BUNDLE_SCHEMA:
            raise ValueError("Unknown research artifact bundle schema")
        rows = bundle.get("artifacts")
        if not isinstance(rows, list) or not rows:
            raise ValueError("Research artifact bundle requires artifacts")
        self._by_id: dict[str, StoredResearchArtifact] = {}
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError("Research artifact bundle row must be an object")
            raw_identity = row["identity"]
            if not isinstance(raw_identity, Mapping):
                raise ValueError("Research artifact identity must be an object")
            as_of = raw_identity.get("as_of")
            identity = ResearchArtifactIdentity(
                scope_type=str(raw_identity["scope_type"]),
                scope_key=str(raw_identity["scope_key"]),
                artifact_type=str(raw_identity["artifact_type"]),
                schema_version=str(raw_identity["schema_version"]),
                as_of=date.fromisoformat(str(as_of)) if as_of is not None else None,
                available_at=datetime.fromisoformat(str(raw_identity["available_at"])),
            )
            stored = StoredResearchArtifact(
                artifact_id=str(row["artifact_id"]),
                envelope=ResearchArtifactEnvelope(
                    identity=identity,
                    canonical_payload=str(row["canonical_payload"]),
                    payload_sha256=str(row["payload_sha256"]),
                    evidence_refs=tuple(dict(ref) for ref in row["evidence_refs"]),
                    run_id=str(row["run_id"]),
                ),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            if stored.artifact_id in self._by_id:
                raise ValueError("Duplicate research artifact bundle id")
            self._by_id[stored.artifact_id] = stored

    def load_by_id(self, artifact_id: str) -> StoredResearchArtifact:
        try:
            return self._by_id[artifact_id]
        except KeyError as error:
            raise KeyError(f"Unknown bundled research artifact id: {artifact_id}") from error

    def recommendation_artifact(self, payload: Mapping[str, Any]) -> StoredResearchArtifact:
        matches = [
            item for item in self._by_id.values()
            if item.envelope.identity.artifact_type == ARTIFACT_DECISION_RECOMMENDATION
            and item.envelope.payload_object() == dict(payload)
        ]
        if len(matches) != 1:
            raise ValueError("Decision payload requires exactly one matching bundled artifact")
        stored = matches[0]
        if stored.envelope.verify_payload() != stored.envelope.payload_sha256:
            raise ValueError("Bundled decision artifact hash mismatch")
        return stored
