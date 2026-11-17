"""An old cash stress is a challengeable input, never a new financial fact."""
from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.application.research.agent_review import operating_horizon_sources_v4 as mod


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _fixture(root):
    source = root / "older-source.txt"
    source.write_bytes(b"TEST_ONLY_OLDER_SOURCE")
    terms = dict(target_payout_ratio="0.8", accessible_profit_ratio="0.7",
        reserve_ratio="0.1", net_maintenance_cash_cny="100", operating_wc_cash_cny="50",
        commitment_cash_cny="200")
    proposal = dict(schema_version="joint-capital-cash-path-proposal-v4", symbol="123456",
        action="no_order", status="NEUTRAL_VALUATION_PROPOSAL_PENDING_REVIEW",
        assumptions_approved=False, g3_approved=False, price_admitted=False,
        generated_at="2026-10-28T00:00:00+00:00",
        joint_historical=dict(currency="CNY"),
        source_bindings=[dict(path="older-source.txt", sha256=_sha(source.read_bytes()))],
        choices=[dict(id="FUNDING_PRESSURE", joint_drivers={
            scenario: dict(years=[dict(year=1, **terms)]) for scenario in ("bear", "base", "bull")})])
    prior = root / "older-proposal.json"
    prior.write_text(json.dumps(proposal), encoding="utf-8")
    config = root / mod.CONFIG
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(dict(schema_version="operating-prior-stress-selection-v1",
        action="no_order", cases={"123456": dict(proposal_path="older-proposal.json",
        proposal_sha256=_sha(prior.read_bytes()), choice_id="FUNDING_PRESSURE")})), encoding="utf-8")
    return source, prior


def test_prior_stress_is_source_bound_and_not_a_valuation(tmp_path, monkeypatch):
    source, _ = _fixture(tmp_path)
    base = dict(symbol="123456", issuer_name="TEST_ONLY", financial_basis="2026-06-30",
        source_binding=dict(path="runtime/operating-horizon-sources-v3/test.json", sha256="a" * 64),
        prior_conditional_hypothesis=None, evidence=[], supplemental_sources=[],
        snapshot_fingerprint="b" * 64, action="no_order")
    monkeypatch.setattr(mod.v3, "build_operating_horizon_source_context", lambda **kwargs: base)
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    current = mod.build_operating_horizon_source_context(root=tmp_path, symbol="123456", now=now)
    replay = mod.build_operating_horizon_source_context(root=tmp_path, symbol="123456", now=now,
                                                        binding=current["source_binding"])
    assert current == replay
    assert current["evidence"] == []
    assert current["prior_conditional_hypothesis"]["scenario_first_year"]["base"]["commitment_cash_cny"] == "200"
    assert current["prior_conditional_hypothesis"]["scope"] == "OLDER_UNAPPROVED_CONDITIONAL_STRESS_FOR_CRITICAL_REVIEW_ONLY"
    assert "valuation" not in current["prior_conditional_hypothesis"]
    source.write_bytes(b"TAMPERED")
    with pytest.raises(ValueError, match="PRIOR_STRESS_SOURCE_CHANGED"):
        mod.build_operating_horizon_source_context(root=tmp_path, symbol="123456", now=now,
                                                   binding=current["source_binding"])


def test_prior_stress_rejects_foreign_or_approved_proposal(tmp_path):
    _, prior = _fixture(tmp_path)
    selected, _ = mod._selection(tmp_path, "123456")
    base = dict(symbol="123456", financial_basis="2026-06-30")
    now = datetime(2026, 11, 11, tzinfo=timezone.utc)
    assert mod._prior(tmp_path, selected, base, now)["forecast_year"] == 2027
    proposal = json.loads(prior.read_text(encoding="utf-8"))
    proposal["g3_approved"] = True
    prior.write_text(json.dumps(proposal), encoding="utf-8")
    selected["proposal_sha256"] = _sha(prior.read_bytes())
    with pytest.raises(ValueError, match="PRIOR_STRESS_IDENTITY_OR_APPROVAL_INVALID"):
        mod._prior(tmp_path, selected, base, now)
