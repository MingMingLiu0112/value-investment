from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from value_investment_agent.research_artifact_codecs import decode_artifact
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_VALUATION_RESULT,
    SCOPE_SECURITY,
    ResearchArtifactEnvelope,
    ResearchArtifactIdentity,
)
from value_investment_agent.valuation_models.base import ValuationResult


REF = {"id": "e-1", "sha256": "a" * 64}


def _identity(available_at: datetime, as_of: date = date(2026, 9, 21)) -> ResearchArtifactIdentity:
    return ResearchArtifactIdentity(
        scope_type=SCOPE_SECURITY,
        scope_key="600519",
        artifact_type=ARTIFACT_VALUATION_RESULT,
        schema_version="c3-v1",
        as_of=as_of,
        available_at=available_at,
    )


def _valuation(status: str = "not_ready") -> ValuationResult:
    return ValuationResult(
        symbol="600519",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2026, 9, 21),
        bear_value=None,
        base_value=None,
        bull_value=None,
        confidence="低",
        assumptions={},
        sensitivities=[],
        evidence_refs=[REF],
        blockers=["inputs_missing"],
        status=status,
        model_version="model-v1",
    )


def test_repository_save_is_append_only_and_idempotent():
    repository = InMemoryResearchArtifactRepository()
    envelope = ResearchArtifactEnvelope.build(
        identity=_identity(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)),
        payload={"symbol": "600519", "status": "not_ready"},
        run_id="run-1",
    )
    first = repository.save(envelope)
    second = repository.save(envelope)
    assert first.artifact_id == second.artifact_id
    assert repository.load_by_id(first.artifact_id) == first
    assert repository.load_latest("security", "600519", ARTIFACT_VALUATION_RESULT) == first
    assert len(
        repository.list_versions("security", "600519", ARTIFACT_VALUATION_RESULT)
    ) == 1

    newer = ResearchArtifactEnvelope.build(
        identity=_identity(
            datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
            as_of=date(2026, 9, 22),
        ),
        payload={"symbol": "600519", "status": "not_ready"},
        run_id="run-2",
    )
    latest = repository.save(newer)
    assert repository.load_latest(
        "security", "600519", ARTIFACT_VALUATION_RESULT
    ).artifact_id == latest.artifact_id
    assert len(
        repository.list_versions("security", "600519", ARTIFACT_VALUATION_RESULT)
    ) == 2


def test_repository_loads_by_hash_and_verifies_exact_payload():
    repository = InMemoryResearchArtifactRepository()
    envelope = ResearchArtifactEnvelope.build(
        identity=_identity(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)),
        payload={"symbol": "600519", "value": Decimal("1.25")},
        evidence_refs=[REF],
        run_id="run-1",
    )
    stored = repository.save(envelope)
    matches = repository.load_by_hash(envelope.payload_sha256, scope_key="600519")
    assert [item.artifact_id for item in matches] == [stored.artifact_id]
    assert repository.verify(stored)["verified"] is True


def test_typed_object_roundtrip_through_repository():
    repository = InMemoryResearchArtifactRepository()
    value = _valuation()
    stored = repository.save_object(
        value,
        identity=_identity(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)),
        evidence_refs=[REF],
        run_id="run-1",
    )
    restored_payload = repository.load_by_id(stored.artifact_id).envelope.payload_object()
    restored = decode_artifact(ARTIFACT_VALUATION_RESULT, restored_payload)
    assert restored.to_json() == value.to_json()


def test_older_replay_does_not_rewind_head():
    repository = InMemoryResearchArtifactRepository()
    later = repository.save(
        ResearchArtifactEnvelope.build(
            identity=_identity(datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)),
            payload={"symbol": "600519", "status": "not_ready"},
            run_id="run-2",
        )
    )
    older = repository.save(
        ResearchArtifactEnvelope.build(
            identity=_identity(datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)),
            payload={"symbol": "600519", "status": "not_ready"},
            run_id="run-1",
        )
    )
    assert repository.load_latest(
        "security", "600519", ARTIFACT_VALUATION_RESULT
    ).artifact_id == later.artifact_id
    assert older.artifact_id != later.artifact_id


def test_missing_head_fails_closed():
    repository = InMemoryResearchArtifactRepository()
    with pytest.raises(KeyError, match="No research artifact head"):
        repository.load_latest("security", "600519", ARTIFACT_VALUATION_RESULT)
