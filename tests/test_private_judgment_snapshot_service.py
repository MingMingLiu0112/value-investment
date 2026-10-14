"""Isolated service boundary: clients cannot inject recording-time judgments."""
from copy import deepcopy
import hashlib
import json

import pytest

from value_investment_agent.application.portfolio import judgment_snapshot
from value_investment_agent.application.portfolio.private_portfolio_service import PrivatePortfolioService
from test_private_ledger_candidate_fill import ledger, request, confirm


@pytest.mark.parametrize("decision", ["600887", "hotspot-600887"])
def test_service_overwrites_client_snapshot_and_confirm_preserves_server_capture(ledger, tmp_path, monkeypatch, decision):
    plan = {"symbol": "600887", "research_version": "TEST_ONLY-public-version", "decision_id": decision,
        "action": "no_order", "action_eligibility": False, "levels": {"entry": "TEST_ONLY"}}
    packet = {"research_version": "TEST_ONLY-global-version", "publication_id": "TEST_ONLY-publication",
        "content_sha256": "a" * 64, "value_price_conditions": {"600887": plan},
        "price_conditions": {"items": [{"symbol": "600887", "price_action_plan": plan}]}}
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (packet, None))
    body = request(ledger)
    forged = {"snapshot_sha256": "f" * 64, "plan": {"action_eligibility": True},
        "trade_time_availability_proven": True, "personal_risk_at_trade": "FAKE"}
    body["fill"].update(decision_id=decision, research_version=plan["research_version"], judgment_snapshot=forged)
    prepared, digest = ledger.prepare_fill(body, repository_root=tmp_path)
    snapshot = deepcopy(prepared["draft"]["fill"]["judgment_snapshot"])
    assert snapshot is not None and snapshot != forged
    assert snapshot["research_version"] == snapshot["plan"]["research_version"] == plan["research_version"]
    assert snapshot["research_version"] != packet["research_version"]
    assert snapshot["plan"]["action_eligibility"] is False
    assert snapshot["trade_time_availability_proven"] is False
    assert snapshot["current_source_reverified"] is False
    assert snapshot["personal_risk_at_trade"] is None
    unsigned = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
    assert snapshot["snapshot_sha256"] == hashlib.sha256(json.dumps(unsigned, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert ledger.portfolio_view()["cash_cny"] == "5000"
    # A new publication and mutations of the response cannot change the capture
    # saved in the immutable prepared record, including on an idempotent retry.
    plan["levels"]["entry"] = "NEW_PUBLICATION"
    prepared["draft"]["fill"]["judgment_snapshot"]["plan"]["action_eligibility"] = True
    assert ledger.prepare_fill(body, repository_root=tmp_path)[0]["draft"]["fill"]["judgment_snapshot"] == snapshot
    confirmation, _ = ledger.confirm_fill({"idempotency_key": "confirm", "expected_revision": len(ledger.records()),
        "prepared_record_sha256": digest, "confirmed_at": "2026-10-12T21:00:00+08:00",
        "confirmation_note": "TEST ONLY", "judgment_snapshot": forged})
    assert confirmation["trades"][0]["judgment_snapshot"] == snapshot
    assert PrivatePortfolioService(ledger.journal).portfolio_view()["trades"][0]["judgment_snapshot"] == snapshot
    assert body["fill"]["judgment_snapshot"] == forged


@pytest.mark.parametrize("mode", ["no_repository_root", "unavailable_packet", "wrong_version", "missing_plan"])
def test_unverified_client_snapshot_is_erased_and_stays_null_on_confirm(ledger, tmp_path, monkeypatch, mode):
    plan = {"symbol": "600887", "research_version": "TEST_ONLY-company-version", "action": "no_order"}
    packet = {"research_version": "TEST_ONLY-global-version", "publication_id": "TEST_ONLY-publication",
        "content_sha256": "a" * 64, "value_price_conditions": {} if mode == "missing_plan" else {"600887": plan}}
    monkeypatch.setattr(judgment_snapshot, "load_current_packet", lambda root: (None, "TEST_ONLY_UNAVAILABLE")
        if mode == "unavailable_packet" else (packet, None))
    body = request(ledger)
    body["fill"].update(decision_id="600887", research_version=packet["research_version"]
        if mode == "wrong_version" else plan["research_version"])
    body["fill"]["judgment_snapshot"] = {"snapshot_sha256": "f" * 64, "trade_time_availability_proven": True}
    prepared, digest = ledger.prepare_fill(body, repository_root=None if mode == "no_repository_root" else tmp_path)
    assert prepared["draft"]["fill"]["judgment_snapshot"] is None
    assert confirm(ledger, digest, "confirm-null")["trades"][0]["judgment_snapshot"] is None
    assert PrivatePortfolioService(ledger.journal).portfolio_view()["trades"][0]["judgment_snapshot"] is None
