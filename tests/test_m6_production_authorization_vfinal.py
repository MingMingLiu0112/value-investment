import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_vfinal_authorization_package_is_complete_but_not_authorized():
    package = json.loads((ROOT / "config/m6-production-authorization-vfinal.json").read_text(encoding="utf-8"))
    prepared = package["machine_prepared"]
    assert package["status"] == "READY_FOR_USER_REVIEW_NOT_AUTHORIZED"
    assert package["production_authorization_granted"] is False
    assert package["shadow_start_allowed"] is False
    assert package["action"] == "no_order"
    assert prepared["deployment_host"] == "47.100.97.88"
    assert prepared["database"]["bind"] == "127.0.0.1:5432"
    assert prepared["database"]["public_5432"] is False
    assert prepared["notification"]["external_delivery"] is False
    assert prepared["resources"]["concurrency"] == 1
    assert prepared["resources"]["minimum_free_disk_mb_before_write"] >= 2048
    assert prepared["shadow"]["minimum_consecutive_real_sessions"] == 20
    assert prepared["shadow"]["minimum_real_financial_or_capital_event"] == 1
    assert prepared["shadow"]["candidate_signers"] == 4
    assert "separately_pinned_event_admission" in prepared["shadow"]["event_observation"]
    assert all(value is None for value in package["user_to_authorize"].values())
