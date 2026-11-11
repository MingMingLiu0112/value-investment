"""Unsigned review packets must never become strategy validation or release."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import pytest
from hotspot_retained_originals import require_retained_originals

from value_investment_agent.application.hotspot import validation_evidence

ROOT = Path(__file__).resolve().parents[1]


def synthetic_validation_report(root):
    """Empty schema fixture for rejection mechanics, never market evidence."""
    source = root / "isolated-source.json"
    source.write_text(json.dumps(dict(fixture="ISOLATED_SCHEMA_ONLY", action="no_order")), encoding="utf-8")
    binding = dict(path=source.name, sha256=sha256(source.read_bytes()).hexdigest())
    report = dict(schema_version=validation_evidence.SCHEMA_VERSION, action="no_order",
        trade_intent="NO_TRADE", strategy_validation="NOT_PROVEN", rule_pit_status="NOT_PROVEN",
        source_report_rule_version="hotspot-dated-sector-liquidity-ranking-v2",
        replayed_rule_version="hotspot-dated-sector-liquidity-ranking-v3",
        rule_version="hotspot-dated-sector-liquidity-ranking-v3",
        rule_extension_status="RETROSPECTIVE_RESEARCH_EXTENSION", future_rule_version_used=True,
        classification_pit="NOT_PROVEN", prospective_oos_admitted=False,
        formal_eligibility=False, portfolio_eligibility=None, selection_trade_date="2026-10-16",
        candidate_pool=[], pool_structure_status=[], case_structure_evidence=[],
        summary=dict(pool_count=0, pool_industry_count=0, pool_assessed_count=0,
            pool_unassessed_count=0, case_count=0, conflict_or_rejected_count=0,
            structure_qualified_observation_count=0), incomplete_live_attempt=None,
        source_files=dict(selection_report=binding, current_price_conditions=binding, cases={}))
    report["evidence_sha256"] = validation_evidence._recomputed_digest(report, "evidence_sha256")
    return report


def real_handoff():
    require_retained_originals(ROOT,
        ROOT / "runtime/hotspot-daily-selection/561a1e66bf424d4e87426fbf1f080106/report.json",
        ROOT / "config/archive/price-conditions-20261017-e65444f2.json",
        ROOT / "runtime/hotspot-current-price-cases/601318-2026-10-15-ca32740c2d9b45ebb82eb4ff594fa651/case.json")
    return validation_evidence.build_hotspot_review_handoff(
        root=ROOT, evaluated_at=datetime.now(timezone.utc),
        selection_report_path=ROOT / "runtime/hotspot-daily-selection/561a1e66bf424d4e87426fbf1f080106/report.json",
        selection_report_sha256="c2ef47a982ea85f04ed4d5e6324f9beda00e0f80f55cd4b19590d1c96d53f4f1",
        current_price_conditions_path=ROOT / "config/archive/price-conditions-20261017-e65444f2.json",
        historical_case_paths=[ROOT / "runtime/hotspot-current-price-cases/601318-2026-10-15-ca32740c2d9b45ebb82eb4ff594fa651/case.json"])


def test_review_handoff_rejects_naive_cutoff_before_reading_sources(tmp_path):
    with pytest.raises(ValueError, match="timezone"):
        validation_evidence.build_hotspot_review_handoff(
            root=tmp_path, evaluated_at=datetime(2026, 10, 21))


def test_real_handoff_rebuilds_originals_without_signing_or_publishing():
    pointer = ROOT / "config/current-price-conditions.json"
    require_retained_originals(ROOT, pointer)
    before = pointer.read_bytes()
    result = real_handoff()
    assert pointer.read_bytes() == before
    assert result["namespace"] == "ACTUAL"
    assert result["status"] == "PENDING_INDEPENDENT_REVIEW"
    assert result["strategy_validation"] == "NOT_PROVEN"
    assert result["formal_release_status"] == "NOT_REQUESTED"
    assert result["formal_eligibility"] is result["risk_review_eligible"] is False
    assert result["authorization_requirements"]["signature"] is None
    assert result["authorization_requirements"]["reviewer_id"] is None
    assert {row["gap"] for row in result["validation_requirements"]} == {
        "STRICT_PIT", "COST_AND_EXECUTION", "OOS_AND_STABILITY"}
    assert all(row["status"] == "PENDING_REVIEW" for row in result["review_requirements"])
    assert result["evidence_sha256"] == validation_evidence._recomputed_digest(result, "evidence_sha256")
    assert result["validation_evidence"]["future_rule_version_used"] is True
    for binding in result["source_bindings"]:
        assert sha256((ROOT / binding["path"]).read_bytes()).hexdigest() == binding["sha256"]


@pytest.mark.parametrize("namespace", ["TEST_ONLY", "SIMULATED"])
def test_isolated_handoff_rejects_test_evidence_even_if_rebound(monkeypatch, tmp_path, namespace):
    report = synthetic_validation_report(tmp_path)
    source = tmp_path / "source.json"
    source.write_text(json.dumps({"nested": {"namespace": namespace}}), encoding="utf-8")
    binding = dict(path="source.json", sha256=sha256(source.read_bytes()).hexdigest())
    report["source_files"] = dict(selection_report=binding, current_price_conditions=binding, cases={})
    report["evidence_sha256"] = validation_evidence._recomputed_digest(report, "evidence_sha256")
    monkeypatch.setattr(validation_evidence, "build_hotspot_structure_validation", lambda **kwargs: report)
    with pytest.raises(ValueError, match="TEST_ONLY"):
        validation_evidence.build_hotspot_review_handoff(root=tmp_path, evaluated_at=datetime.now(timezone.utc))


def test_isolated_handoff_rejects_changed_source(monkeypatch, tmp_path):
    report = synthetic_validation_report(tmp_path)
    report["source_files"]["selection_report"]["sha256"] = "0" * 64
    report["evidence_sha256"] = validation_evidence._recomputed_digest(report, "evidence_sha256")
    monkeypatch.setattr(validation_evidence, "build_hotspot_structure_validation", lambda **kwargs: report)
    with pytest.raises(ValueError, match="source hash mismatch"):
        validation_evidence.build_hotspot_review_handoff(root=tmp_path, evaluated_at=datetime.now(timezone.utc))
