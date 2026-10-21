"""Isolated held-decision gaps must never masquerade as external approval waits."""
from copy import deepcopy

import pytest

from test_held_continuity import NOW, plan, position, project
from test_private_ips_policy import service
from value_investment_agent.application.portfolio.held_continuity import review_held_continuity


@pytest.mark.parametrize("coverage", ["COMPLETE", "UNKNOWN"])
@pytest.mark.parametrize("sleeve,schema", [
    ("CORE_VALUE", "value-action-plan-v1"),
    ("HOTSPOT_SATELLITE", "price-action-plan-independent-v2"),
])
def test_public_actual_entry_and_pass_flags_do_not_prove_private_ownership(coverage, sleeve, schema):
    source = plan("300364", schema_version=schema, strategy=sleeve,
        announcement_coverage_status=coverage, formal_eligibility=True,
        entry_thesis={"entry_type": "ACTUAL", "entry_id": "public-example",
                      "symbol": "300364", "confirmed_at": NOW.isoformat()},
        investment_consistency_review={"entry_id": "public-example", "status": "CONSISTENT"},
        event_materiality={"status": "PASS"},
        decision_assessment_status="COMPLETE", code_gaps=[])
    original = deepcopy(source)
    row = project([position("300364", sleeve)], lambda _: source,
                  risk={"engine": {"status": "PASS"}, "blockers": []})["items"][0]
    assert row["decision_assessment_status"] == "UNASSESSABLE"
    gaps = {gap["code"]: gap for gap in row["code_gaps"]}
    assert gaps == {}
    assert "AUTHENTICATED_PERSONAL_ENTRY_SUBJECT_REQUIRED" in row["data_gaps"]
    assert "OWNED_ENTRY_DEPENDENCIES_REQUIRED" in row["data_gaps"]
    assert row["actionable_decision"]["decision_action"] == "UNASSESSABLE"
    assert ("ANNOUNCEMENT_COVERAGE_UNKNOWN" in row["data_gaps"]) == (coverage == "UNKNOWN")
    assert row["formal_eligibility"] is False
    assert row["personal_sell_permission"] is False
    assert row["position_guidance"] is None and row["action"] == "no_order"
    assert "INVALIDATION_OR_EXIT_REVIEW" in row["review_reasons"]
    assert source == original


def test_missing_plan_keeps_code_gap_separate_from_current_evidence_gap():
    row = project([position("300364")], lambda _: None)["items"][0]
    assert row["decision_assessment_status"] == "UNASSESSABLE"
    assert "CURRENT_STRATEGY_PLAN_UNAVAILABLE" in row["data_gaps"]
    assert "TEST_ONLY_RISK_GAP" in row["data_gaps"]
    assert row["review_reasons"] == []


def test_isolated_confirmed_journal_reports_adapter_gap_without_writes(service, tmp_path):
    before = service.journal.path.read_bytes()
    result = review_held_continuity(service.journal, repository_root=tmp_path,
        generated_at=NOW, plan_provider=lambda _: None)
    assert result["items"][0]["decision_assessment_status"] == "UNASSESSABLE"
    assert result["revision"] == len(service.records())
    assert service.journal.path.read_bytes() == before


def test_no_holdings_does_not_fabricate_a_decision_gap():
    result = project([], lambda _: pytest.fail("No plan needed without holdings"))
    assert result["items"] == []
    assert result["status"] == "NO_HELD_SECURITIES"
