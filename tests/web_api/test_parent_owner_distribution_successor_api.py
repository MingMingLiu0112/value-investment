"""TEST_ONLY v2 successor projection and routing; no F2 or approval."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from value_investment_agent.application.product import first_research_input_view_v1 as view
from value_investment_agent.application.product import parent_owner_distribution_successor_view_v2 as successor_view
from web_api.test_held_continuity_api import client_for


NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def bound(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(json.dumps(value, sort_keys=True).encode())
    return {"path": path, "sha256": sha256(target.read_bytes()).hexdigest()}


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


def case(root):
    predecessor = {"path": "runtime/TEST_ONLY-prior.json", "sha256": "a" * 64}
    spec = bound(root, "runtime/TEST_ONLY-owner-spec.json", dict(
        research_as_of="2026-11-18", computed_at=NOW.isoformat()))
    receipt = bound(root, "runtime/TEST_ONLY-owner-receipt.json", dict(
        schema_version="parent-owner-distribution-successor-receipt-v2",
        symbol="600887", action="no_order", spec_binding=spec,
        predecessor_binding=predecessor, input_descriptor_sha256="d" * 64))
    bound(root, view.REGISTRY, dict(schema_version=view.SCHEMA,
        action="no_order", cases={"600887": {"receipt": receipt}}))
    distribution = dict(period_year=2026, paid_date="2026-06-05",
        per_share_cny="0.9", eligible_shares="100", total_cny="90",
        scope="PARENT_STANDALONE_OWNER_DISTRIBUTION", currency="CNY",
        classification="FACT")
    evidence = {
        "original": {"path": "runtime/TEST_ONLY-original.pdf", "sha256": "b" * 64},
        "reconciliation": {"path": "runtime/TEST_ONLY-ledger.json", "sha256": "c" * 64},
    }
    calculations = {}
    scenarios = {}
    for name, value in (("bear", "1"), ("base", "2"), ("bull", "3")):
        rows = [{"year": 2026, "scheduled_owner_distribution_cny": "90",
                 "conditional_distribution_cny": "10",
                 "total_owner_distribution_cny": "100"}]
        calculations[name] = {"annual_rows": rows}
        scenarios[name] = {"years": [{"year": 2026}], "calculation": calculations[name]}
    result = dict(
        symbol="600887", action="no_order", formal_eligibility=False,
        successor_adopted=False, main_range_adopted=False,
        predecessor_binding=predecessor, input_descriptor_sha256="d" * 64,
        research_case={"symbol": "600887"},
        valuation={"valuation_date": "2026-09-30", "bear_value": "1",
                   "base_value": "2", "bull_value": "3",
                   "assumptions": {"scenario_calculations": calculations}},
        compiled={"scenarios": scenarios}, distribution=distribution,
        distribution_evidence=evidence,
        research_result={"blockers": ["ECONOMIC_RESEARCH_NOT_APPROVED"]},
        source_bindings=[*evidence.values()], package={"sources": []})
    return receipt, result


def test_v2_successor_api_exposes_distributions_and_blocks_f2(tmp_path, monkeypatch):
    receipt, result = case(tmp_path)
    calls = []
    monkeypatch.setattr(successor_view, "replay_parent_owner_distribution_successor",
        lambda **kwargs: (calls.append(kwargs), deepcopy(result))[1])
    monkeypatch.setattr(view, "replay_first_research_input", lambda **_:
        (_ for _ in ()).throw(AssertionError("legacy replay must not see v2 successor")))
    client, _ = client_for(tmp_path, tmp_path / "TEST_ONLY-private.jsonl", monkeypatch)
    before = files(tmp_path)
    response = client.get("/api/v1/first-research-inputs/600887")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["receipt_schema_version"] == "parent-owner-distribution-successor-receipt-v2"
    assert body["scenario_valuations"] == {"bear": "1", "base": "2", "bull": "3"}
    row = body["owner_distributions"]["base"][0]
    assert row == {"year": 2026, "scheduled_owner_distribution_cny": "90",
                   "conditional_owner_distribution_cny": "10",
                   "total_owner_distribution_cny": "100"}
    assert body["implemented_distribution"] == result["distribution"]
    assert body["distribution_evidence"] == result["distribution_evidence"]
    assert body["direct_cash_alignment"]["reason_codes"] == [
        "F2_ALIGNMENT_NOT_IMPLEMENTED_FOR_OWNER_DISTRIBUTION_V2"]
    assert body["e2_quote_alignment"]["reason"] == (
        "F2_ALIGNMENT_NOT_IMPLEMENTED_FOR_OWNER_DISTRIBUTION_V2")
    assert body["successor_update"]["reason"] == (
        "DISPLAYED_RECEIPT_IS_OWNER_DISTRIBUTION_SUCCESSOR_V2")
    assert body["condition_price"] is None and body["current_price"] is None
    assert body["main_range_adopted"] is False
    assert body["formal_eligibility"] is False and body["action"] == "no_order"
    assert len(calls) == 1 and calls[0]["receipt_binding"] == receipt
    assert files(tmp_path) == before


def test_v2_successor_identity_fails_closed(tmp_path, monkeypatch):
    _, result = case(tmp_path)
    monkeypatch.setattr(successor_view, "replay_parent_owner_distribution_successor",
        lambda **_: deepcopy(result))
    result["symbol"] = "000333"
    before = files(tmp_path)
    rejected = view.read_first_research_input(root=tmp_path, symbol="600887", now=NOW)
    assert rejected["status"] == "UNASSESSABLE"
    assert rejected["reason"] == "OWNER_DISTRIBUTION_PUBLIC_IDENTITY_OR_ADOPTION_INVALID"
    assert rejected["formal_eligibility"] is False
    assert files(tmp_path) == before
