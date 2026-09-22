"""Three-company replay tests use a self-contained frozen runtime fixture."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

import pytest

from fixed_sample_runtime_fixture import write_fixed_sample_runtime_fixture
from value_investment_agent.research_artifact_repository import (
    InMemoryResearchArtifactRepository,
)
from value_investment_agent.research_e2e_replay import (
    EXPECTED_REPLAY_SEMANTICS,
    MOUTAI_CURRENT_MODEL_POINTER,
    run_three_company_replay,
)
from value_investment_agent.research_runtime_import import resolve_pinned


NOW = datetime(2026, 9, 22, 3, 0, tzinfo=timezone.utc)


def _run(root: Path, *, run_id: str = "fixture-replay"):
    repository = InMemoryResearchArtifactRepository()
    result = run_three_company_replay(
        repository,
        root=root,
        run_id=run_id,
        now_utc=lambda: NOW,
    )
    return repository, result


def test_self_contained_frozen_replay_matches_required_semantics():
    with tempfile.TemporaryDirectory(prefix="c3-replay-") as directory:
        root = Path(directory)
        write_fixed_sample_runtime_fixture(root)
        repository, result = _run(root)

        assert result.all_semantics_matched is True
        assert result.action == "no_order"
        assert result.aggregate_review.action == "no_order"
        assert result.aggregate_review.production_valuation_available is False

        by_symbol = {item.symbol: item for item in result.companies}
        assert set(by_symbol) == {"600519", "000333", "601088"}
        for symbol, expected in EXPECTED_REPLAY_SEMANTICS.items():
            actual = by_symbol[symbol]
            assert actual.profile_id == expected["profile_id"]
            assert actual.valuation_status == expected["valuation_status"]
            assert actual.confidence == expected["confidence"]
            assert actual.model_validity_present is expected["model_validity_present"]
            assert actual.bridge_status == expected["bridge_status"]
            assert actual.cash_return_status == expected["cash_return_status"]
            assert actual.decision == expected["decision"]
            assert actual.bounded_value_judgment == expected["bounded_value_judgment"]
            assert actual.action == expected["action"]
            assert actual.semantics_matched is True

        outcomes = {
            symbol: result.batch_result.results_by_symbol[symbol].outcome
            for symbol in by_symbol
        }
        moutai = outcomes["600519"].valuation
        assert moutai.bear_value < moutai.base_value < moutai.bull_value
        assert outcomes["000333"].valuation.bear_value is None
        assert outcomes["601088"].valuation.bear_value is None
        assert by_symbol["601088"].current_normalized_distinct is True

        for symbol, source in {
            "600519": "runtime/valuation-results/600519-current-equity-stage-b-latest.json",
            "000333": "runtime/valuation-results/000333-fcff-stage-b-latest.json",
            "601088": "runtime/valuation-results/601088-cyclical-stage-b-latest.json",
        }.items():
            _, pin = resolve_pinned(root, source)
            assert by_symbol[symbol].source_sha256 == pin.sha256

        restored = repository.load_by_id(result.aggregate_review_artifact_id)
        assert repository.verify(restored)["verified"] is True
        receipt = json.loads(json.dumps(result.as_policy()))
        assert receipt["all_semantics_matched"] is True
        assert receipt["action"] == "no_order"


def test_duplicate_overlapping_evidence_refs_are_merged_without_losing_contract():
    with tempfile.TemporaryDirectory(prefix="c3-replay-") as directory:
        root = Path(directory)
        write_fixed_sample_runtime_fixture(root)
        _, result = _run(root)

        midea = result.batch_result.results_by_symbol["000333"].outcome.valuation
        ref_ids = [ref["id"] for ref in midea.evidence_refs]
        assert len(ref_ids) == len(set(ref_ids))
        assert "e-1" in ref_ids


def test_replay_fails_closed_when_a_hash_verified_input_changes():
    with tempfile.TemporaryDirectory(prefix="c3-replay-") as directory:
        root = Path(directory)
        write_fixed_sample_runtime_fixture(root)
        pointer = root / MOUTAI_CURRENT_MODEL_POINTER
        pin = json.loads(pointer.read_text(encoding="utf-8"))
        evidence = root / pin["path"] / "evidence.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        payload["facts"]["parent_equity_cny"] = "999"
        evidence.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ValueError, match="hash changed"):
            _run(root)
