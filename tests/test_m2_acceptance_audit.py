from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m2_acceptance_audit import (
    DEFAULT_POLICY_PATH,
    DONE,
    PENDING_HUMAN_REVIEW,
    _reject_execution_keys,
    _verify_pinned_json,
    audit,
    load_acceptance_policy,
    write_receipt,
)
from value_investment_agent.m2_opportunity_discovery import ACTION_NO_ORDER


ROOT = Path(__file__).resolve().parents[1]


def test_default_policy_pins_m2_evidence_and_stays_no_order():
    policy = load_acceptance_policy(DEFAULT_POLICY_PATH)

    assert policy.action == ACTION_NO_ORDER
    assert policy.stage == "M2"
    assert policy.minimum_universe_count == 5000
    assert policy.max_allowed_skips == 30
    assert len(policy.pit_snapshots) == 2


def test_execution_keys_are_rejected_in_audit_policy():
    with pytest.raises(ValueError, match="Execution key"):
        _reject_execution_keys({"target_weight": 1})


def test_pinned_evidence_rejects_any_byte_change(tmp_path: Path):
    evidence = tmp_path / "evidence.json"
    evidence.write_text('{"value": 1}\n', encoding="utf-8")
    expected = hashlib.sha256(evidence.read_bytes()).hexdigest()

    assert _verify_pinned_json(tmp_path, "evidence.json", expected) == {"value": 1}

    evidence.write_text('{"value": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Pinned evidence changed"):
        _verify_pinned_json(tmp_path, "evidence.json", expected)


def test_write_receipt_uses_versioned_path_and_pointer(tmp_path: Path):
    payload = {
        "schema_version": "m2-acceptance-audit-v1",
        "status": PENDING_HUMAN_REVIEW,
        "action": ACTION_NO_ORDER,
    }

    output = write_receipt(payload, root=tmp_path)

    receipt_path = tmp_path / output["receipt_path"]
    pointer_path = tmp_path / output["pointer_path"]
    assert receipt_path.is_file()
    assert pointer_path.is_file()
    assert json.loads(receipt_path.read_text(encoding="utf-8")) == payload
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    assert pointer["sha256"] == hashlib.sha256(receipt_path.read_bytes()).hexdigest()


def test_machine_audit_preserves_human_review_boundary(monkeypatch):
    import value_investment_agent.m2_acceptance_audit as auditor

    monkeypatch.setattr(
        auditor,
        "_run_pytest",
        lambda root: {
            "passed": True,
            "passed_count": 2144,
            "skipped_count": 6,
            "returncode": 0,
            "output_tail": "",
            "duration_seconds": 1.0,
        },
    )

    result = audit(
        ROOT,
        run_tests=True,
        ci_evidence={"status": "success"},
    )

    assert result["status"] == PENDING_HUMAN_REVIEW
    assert result["criteria"]["ac1_stabilization_and_offline_green"]["status"] == DONE
    assert result["criteria"]["ac6_point_in_time_version_hash_replay"]["status"] == DONE
    assert (
        result["criteria"]["ac8_substantive_research_or_rejection"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert (
        result["criteria"]["ac9_stratified_false_positive_review"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert (
        result["criteria"]["ac10_original_excel_usability"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert (
        result["criteria"]["ac12_user_outcome_and_stage_boundary"]["status"]
        == PENDING_HUMAN_REVIEW
    )
    assert result["summary"]["partial"] == []
