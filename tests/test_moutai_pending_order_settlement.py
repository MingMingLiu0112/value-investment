import importlib.util
import json
from pathlib import Path

import pytest

from value_investment_agent.virtual_account import ORDER_TERMS_VERSION, VirtualAccount


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_pending_settlement", ROOT / "scripts" / "settle_moutai_pending_paper_order.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def frozen_order() -> dict:
    return {"order_id": "test-001", "side": "buy", "requested_quantity": 100,
            "submitted_on": "2026-09-18", "decision_state": "proposed_entry",
            "execution_terms": {"version": ORDER_TERMS_VERSION, "valid_session": "2026-09-21",
                                "limit_price": "100", "cash_budget_cny": "10000",
                                "liquidity_budget_cny": "50000", "liquidity_as_of": "2026-09-18",
                                "slippage_bps": "10", "basis_id": "synthetic-test-basis"}}


def opening() -> dict:
    return {"symbol": "600519", "session": "2026-09-21", "opening_price_cny": "90",
            "close_price_cny": "91", "execution_ready": True, "price_limit_down": "80",
            "price_limit_up": "110", "security_status": "tradable", "corporate_action_status": "none",
            "evidence_refs": [{"path": "runtime/synthetic-source.json", "sha256": "a" * 64}]}


def fee_policy() -> dict:
    return {"policy_version": "sse-current-paper-fees-v1", "exchange": "SSE",
            "valid_session": "2026-09-21", "execution_ready": True, "broker_invoice_verified": False,
            "source_manifest": {"path": "fees-manifest.json", "sha256": None},
            "commission_scenario": {"rate": "0.0003", "minimum_cny": "5"}}


def test_settlement_fills_only_a_bounded_order_with_complete_opening_evidence(tmp_path):
    state = tmp_path / "state.json"
    account = VirtualAccount()
    account.pending_order = frozen_order()
    state.write_text(json.dumps(account.to_dict()), encoding="utf-8")
    evidence = tmp_path / "opening.json"
    evidence.write_text(json.dumps(opening()), encoding="utf-8")
    policy = tmp_path / "fee.json"
    manifest = tmp_path / "fees-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    payload = fee_policy()
    payload["source_manifest"]["sha256"] = MODULE.digest(manifest)
    policy.write_text(json.dumps(payload), encoding="utf-8")
    original_root = MODULE.ROOT
    MODULE.ROOT = tmp_path
    try:
        result = MODULE.settle(state, evidence, policy, tmp_path / "result")
    finally:
        MODULE.ROOT = original_root
    assert result["fill"]["quantity"] == 100
    assert result["fill"]["price"] == "90.09"
    assert result["ending_shares"] == 100


def test_settlement_refuses_missing_market_status_before_touching_state(tmp_path):
    state = tmp_path / "state.json"
    account = VirtualAccount()
    account.pending_order = frozen_order()
    state.write_text(json.dumps(account.to_dict()), encoding="utf-8")
    evidence = opening()
    evidence.pop("corporate_action_status")
    opening_path = tmp_path / "opening.json"
    opening_path.write_text(json.dumps(evidence), encoding="utf-8")
    policy = tmp_path / "fee.json"
    manifest = tmp_path / "fees-manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    payload = fee_policy()
    payload["source_manifest"]["sha256"] = MODULE.digest(manifest)
    policy.write_text(json.dumps(payload), encoding="utf-8")
    original_root = MODULE.ROOT
    MODULE.ROOT = tmp_path
    try:
        with pytest.raises(ValueError, match="incomplete"):
            MODULE.settle(state, opening_path, policy, tmp_path / "result")
    finally:
        MODULE.ROOT = original_root
    assert VirtualAccount.from_dict(json.loads(state.read_text(encoding="utf-8"))).pending_order["order_id"] == "test-001"
