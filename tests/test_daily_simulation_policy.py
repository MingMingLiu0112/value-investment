import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from value_investment_agent.daily_simulation_policy import (
    IMPLEMENTED_STATUS,
    POLICY_VERSION,
    build_policy,
    validate_policy,
)


ROOT = Path(__file__).resolve().parents[1]


def execution_contract() -> dict:
    return {
        "symbol": "600519",
        "contract_version": "current-next-session-paper-execution-v1",
        "observed_session": "2026-09-21",
        "valid_session": "2026-09-22",
        "price_limit_down": "1000.00",
        "price_limit_up": "1400.00",
        "slippage_bps": "10",
        "liquidity_budget_cny": "500000.00",
        "execution_ready": True,
        "blockers": [],
        "trade_approved": False,
        "live_eligible": False,
    }


def test_policy_binds_framework_rules_to_one_dated_session_pair():
    policy = build_policy(
        execution_contract=execution_contract(),
        execution_contract_ref={"path": "runtime/contract.json", "sha256": "a" * 64},
        observed_session="2026-09-21",
        valid_session="2026-09-22",
    )
    assert policy["policy_version"] == POLICY_VERSION
    assert policy["observed_session"] == "2026-09-21"
    assert policy["valid_session"] == "2026-09-22"
    assert policy["execution_ready"] is True
    assert policy["implementation_status"] == IMPLEMENTED_STATUS
    assert policy["real_fill_verified"] is False
    assert policy["trade_approved"] is False
    assert policy["live_eligible"] is False
    assert policy["rules"]["information_boundary"]["prohibited"]
    assert policy["rules"]["fill_assumption"]["label"].startswith("A simulated fill")


def test_policy_rejects_a_stale_or_approved_execution_contract():
    contract = execution_contract()
    contract["valid_session"] = "2026-09-21"
    with pytest.raises(ValueError, match="follow the observed session"):
        build_policy(
            execution_contract=contract,
            execution_contract_ref={"path": "runtime/contract.json", "sha256": "a" * 64},
            observed_session="2026-09-21",
            valid_session="2026-09-21",
        )
    contract = execution_contract()
    contract["trade_approved"] = True
    with pytest.raises(ValueError, match="incompatible"):
        build_policy(
            execution_contract=contract,
            execution_contract_ref={"path": "runtime/contract.json", "sha256": "a" * 64},
            observed_session="2026-09-21",
            valid_session="2026-09-22",
        )


def test_policy_validation_rejects_approval_boundary_crossing():
    policy = build_policy(
        execution_contract=execution_contract(),
        execution_contract_ref={"path": "runtime/contract.json", "sha256": "a" * 64},
        observed_session="2026-09-21",
        valid_session="2026-09-22",
    )
    validate_policy(policy)
    policy["real_fill_verified"] = True
    with pytest.raises(ValueError, match="verified real fill"):
        validate_policy(policy)
    policy["real_fill_verified"] = False
    policy["trade_approved"] = True
    with pytest.raises(ValueError, match="approval boundary"):
        validate_policy(policy)


def test_latest_policy_pointer_binds_the_real_execution_contract():
    pointer_path = ROOT / "runtime/strategy-validation/moutai-daily-simulation-policy-latest.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    policy_path = ROOT / pointer["path"] / "evidence.json"
    assert hashlib.sha256(policy_path.read_bytes()).hexdigest() == pointer["sha256"]
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    assert policy["observed_session"] == "2026-09-21"
    assert policy["valid_session"] == "2026-09-22"

    contract_ref = policy["execution_contract"]
    contract_path = ROOT / contract_ref["path"]
    assert hashlib.sha256(contract_path.read_bytes()).hexdigest() == contract_ref["sha256"]
    contract_pointer = json.loads(
        (ROOT / "runtime/strategy-validation/moutai-current-execution-contract-latest.json").read_text(encoding="utf-8")
    )
    assert contract_ref["sha256"] == contract_pointer["sha256"]
    validate_policy(policy)
