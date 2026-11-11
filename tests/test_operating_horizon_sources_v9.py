"""The older issuer stress is a critique input, not a D2 cash fact."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v9 as mod


NOW = datetime(2026, 11, 11, tzinfo=timezone.utc)


def _proposal(tmp_path):
    source = tmp_path / "official.pdf"
    source.write_bytes(b"TEST_ONLY_OFFICIAL_BYTES")
    proposal = {
        "schema_version": "joint-capital-cash-path-proposal-v4",
        "symbol": "600887", "action": "no_order",
        "status": "NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW",
        "assumptions_approved": False, "g3_approved": False, "price_admitted": False,
        "joint_historical": {"currency": "CNY"},
        "generated_at": "2026-10-28T00:00:00+00:00",
        "source_bindings": [{"path": "official.pdf",
                             "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}],
        "choices": [{"id": "DAIRY_FUNDING_PRESSURE", "joint_drivers": {
            scenario: {"years": [{"year": 1, **{
                key: ("0.6" if key.endswith("_ratio") else "1000000")
                for key in mod.TERMS}}]}
            for scenario in ("bear", "base", "bull")}}],
    }
    path = tmp_path / "proposal.json"
    path.write_text(json.dumps(proposal), encoding="utf-8")
    selection = {"proposal_path": "proposal.json",
                 "proposal_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                 "choice_id": "DAIRY_FUNDING_PRESSURE"}
    return proposal, selection, source, path


def test_old_stress_is_bound_and_remains_unapproved(tmp_path):
    _, selection, _, _ = _proposal(tmp_path)
    row = mod._prior(tmp_path, selection,
                     {"symbol": "600887", "financial_basis": "2026-06-30"}, NOW)
    assert row["forecast_year"] == 2027
    assert row["scenario_first_year"]["base"]["accessible_profit_ratio"] == "0.6"
    assert row["scope"] == "OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY"
    assert "neither official facts" in row["limitation"]


@pytest.mark.parametrize("change, expected", [
    ("source", "SOURCE_CHANGED"),
    ("proposal", "PROPOSAL_CHANGED"),
    ("approval", "PROPOSAL_CHANGED"),
])
def test_old_stress_rejects_changed_provenance(tmp_path, change, expected):
    proposal, selection, source, path = _proposal(tmp_path)
    if change == "source":
        source.write_bytes(b"OTHER")
    elif change == "proposal":
        path.write_bytes(b"{}")
    else:
        proposal["assumptions_approved"] = True
        path.write_text(json.dumps(proposal), encoding="utf-8")
        selection["proposal_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        expected = "IDENTITY_OR_APPROVAL_INVALID"
    with pytest.raises(ValueError, match="V9_CRITIQUE_" + expected):
        mod._prior(tmp_path, selection,
                   {"symbol": "600887", "financial_basis": "2026-06-30"}, NOW)
