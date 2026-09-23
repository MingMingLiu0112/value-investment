from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.m2_acceptance_audit import (
    DEFAULT_POLICY_PATH,
    DONE,
    PARTIAL,
    PENDING_HUMAN_REVIEW,
    _audit_ac1,
    _audit_ac12,
    _reject_execution_keys,
    _verify_pinned_json,
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


def test_ac1_reports_done_only_when_local_and_ci_are_green():
    policy = load_acceptance_policy(DEFAULT_POLICY_PATH)
    test_result = {
        "passed": True,
        "passed_count": 2149,
        "skipped_count": 6,
        "output_tail": "",
    }
    git_state = {"head": "afc804b4966b0f6e4b0610b6d2d6af2c6e90df31"}

    result = _audit_ac1(
        policy,
        test_result,
        {"status": "success"},
        git_state,
    )

    assert result["status"] == DONE
    assert all(item["passed"] for item in result["checks"])
    assert result["blockers"] == []


def test_ac12_preserves_human_review_boundary_without_runtime_evidence():
    criteria = {
        "ac1_stabilization_and_offline_green": {
            "status": DONE,
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac6_point_in_time_version_hash_replay": {
            "status": DONE,
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac8_substantive_research_or_rejection": {
            "status": PENDING_HUMAN_REVIEW,
            "human_review": ["review reports"],
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac9_stratified_false_positive_review": {
            "status": PENDING_HUMAN_REVIEW,
            "human_review": ["review samples"],
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac10_original_excel_usability": {
            "status": PENDING_HUMAN_REVIEW,
            "human_review": ["open WPS workbook"],
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac11_authorization_and_resource_boundary": {
            "status": DONE,
            "evidence": {"action": ACTION_NO_ORDER},
        },
    }

    result = _audit_ac12(criteria)

    assert result["status"] == PENDING_HUMAN_REVIEW
    assert result["blockers"] == []
    assert result["evidence"]["pending_human_review"] == [
        "ac8_substantive_research_or_rejection",
        "ac9_stratified_false_positive_review",
        "ac10_original_excel_usability",
    ]
    assert result["evidence"]["next_action"]


def test_ac12_blocks_on_any_partial_machine_criterion():
    criteria = {
        "ac1_stabilization_and_offline_green": {
            "status": PARTIAL,
            "evidence": {"action": ACTION_NO_ORDER},
        },
        "ac8_substantive_research_or_rejection": {
            "status": PENDING_HUMAN_REVIEW,
            "human_review": ["review reports"],
            "evidence": {"action": ACTION_NO_ORDER},
        },
    }

    result = _audit_ac12(criteria)

    assert result["status"] == PENDING_HUMAN_REVIEW
    assert result["blockers"] == ["M2 machine evidence is incomplete"]
