from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import os
from pathlib import Path

import pytest

from value_investment_agent.research_artifact_codecs import decode_artifact
from value_investment_agent.research_artifact_repository import (
    PostgresResearchArtifactRepository,
)
from value_investment_agent.research_artifacts import (
    ARTIFACT_VALUATION_RESULT,
    SCOPE_SECURITY,
    ResearchArtifactIdentity,
)
from value_investment_agent.research_runtime_import import (
    VALUATION_POINTERS,
    import_runtime_artifacts,
    resolve_pinned,
    semantic_parity_report,
)
from value_investment_agent.valuation_models.base import ValuationResult


ROOT = Path(__file__).resolve().parents[1]
TEST_DSN_ENV = "C3_TEST_POSTGRES_DSN"


@pytest.fixture(scope="module")
def repository():
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip(
            f"{TEST_DSN_ENV} is not set; disposable PostgreSQL integration is skipped"
        )
    repo = PostgresResearchArtifactRepository(dsn)
    repo.migrate()
    try:
        yield repo
    finally:
        repo.close()


def _valuation() -> ValuationResult:
    return ValuationResult(
        symbol="600519",
        model_type="residual_income_or_equity_value",
        valuation_date=date(2026, 9, 21),
        bear_value=Decimal("800"),
        base_value=Decimal("1000"),
        bull_value=Decimal("1200"),
        confidence="低",
        assumptions={"scope": "integration test"},
        sensitivities=[],
        evidence_refs=[{"id": "integration", "sha256": "a" * 64}],
        blockers=[],
        status="conditional_research_only",
        model_version="integration-v1",
    )


def _identity(
    available_at: datetime,
    *,
    as_of: date = date(2026, 9, 21),
) -> ResearchArtifactIdentity:
    return ResearchArtifactIdentity(
        scope_type=SCOPE_SECURITY,
        scope_key="600519",
        artifact_type=ARTIFACT_VALUATION_RESULT,
        schema_version="c3-v1",
        as_of=as_of,
        available_at=available_at,
    )


def test_postgres_typed_round_trip_and_hash_verification(repository):
    value = _valuation()
    stored = repository.save_object(
        value,
        identity=_identity(
            datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
        ),
        evidence_refs=value.evidence_refs,
        run_id="postgres-roundtrip",
    )

    loaded = repository.load_by_id(stored.artifact_id)
    assert repository.verify(loaded)["verified"] is True
    restored = decode_artifact(
        ARTIFACT_VALUATION_RESULT,
        loaded.envelope.payload_object(),
    )
    assert restored.to_json() == value.to_json()
    matches = repository.load_by_hash(
        loaded.envelope.payload_sha256,
        scope_key="600519",
        artifact_type=ARTIFACT_VALUATION_RESULT,
    )
    assert loaded.artifact_id in {item.artifact_id for item in matches}


def test_postgres_append_only_versions_and_monotonic_head(repository):
    older_available_at = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    newer_available_at = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)
    older = repository.save_object(
        _valuation(),
        identity=_identity(older_available_at),
        run_id="postgres-append-old",
    )
    newer = repository.save_object(
        _valuation(),
        identity=_identity(
            newer_available_at,
            as_of=date(2026, 9, 22),
        ),
        run_id="postgres-append-new",
    )

    assert repository.load_latest(
        SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
    ).artifact_id == newer.artifact_id
    assert older.artifact_id != newer.artifact_id
    versions = repository.list_versions(
        SCOPE_SECURITY, "600519", ARTIFACT_VALUATION_RESULT
    )
    assert {item.artifact_id for item in versions} >= {
        older.artifact_id,
        newer.artifact_id,
    }


def test_frozen_three_company_runtime_imports_into_disposable_postgres(repository):
    result = import_runtime_artifacts(
        repository,
        ROOT,
        run_id="ci-postgres-three-company-import",
    )

    assert len(result.stored) == 20
    assert result.all_hashes_matched is True
    assert set(result.missing) == {
        ("000333", "model_validity"),
        ("601088", "model_validity"),
    }
    valuations = {
        symbol: resolve_pinned(ROOT, pointer)[0]
        for symbol, pointer in VALUATION_POINTERS.items()
    }
    rows = semantic_parity_report(result, root=ROOT, valuations=valuations)
    assert all(row["hash_matched"] for row in rows)
    assert repository.load_latest(
        SCOPE_SECURITY, "600519", "valuation_result"
    )
    assert repository.load_latest(
        "review", "review", "fixed_sample_admission"
    )

