from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path

import pytest

from value_investment_agent.human_milestone_review import (
    ACTION_NO_ORDER,
    M2_CHECKPOINT_A_V2_PACKET_SCHEMA,
    M5HumanMaterialityBinding,
    HumanMilestoneReviewReceipt,
    canonical_digest,
    load_human_milestone_receipt,
    write_human_milestone_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
REVIEWED_AT = date(2026, 9, 24)

DECISIONS = {
    "M2_CHECKPOINT_A": "NOT_APPROVED_PENDING_VERIFICATION_V2",
    "M3_NEGATIVE_CARDS": "PASS",
    "M3_CHECKPOINT_B": "PARTIAL_NOT_APPROVED",
    "M5_1225578520": "NOT_MATERIAL",
    "M7_SEMANTIC_STRUCTURE": "PASS",
    "M4_PRIVATE_INPUT": "PENDING",
    "M6_AUTHORIZATION": "PENDING",
    "M7_FINAL_UX": "PENDING",
}


def _binding() -> M5HumanMaterialityBinding:
    return M5HumanMaterialityBinding(
        symbol="600887",
        announcement_id="1225578520",
        human_decision="NOT_MATERIAL",
        pdf_path="runtime/m5/1225578520.pdf",
        pdf_sha256="7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c",
        reviewed_at=REVIEWED_AT,
    )


def _receipt(sequence: int = 1) -> HumanMilestoneReviewReceipt:
    return HumanMilestoneReviewReceipt(
        receipt_id=f"human-review-v2-{sequence}",
        sequence=sequence,
        reviewed_at=REVIEWED_AT,
        review_scope="M2/M3/M5/M7 user-perspective review",
        decisions=DECISIONS,
        m5_bindings=(_binding(),),
    )


def test_receipt_round_trip_preserves_narrow_human_decisions(tmp_path: Path):
    receipt = _receipt()
    policy = receipt.as_policy()
    assert policy["action"] == ACTION_NO_ORDER
    assert policy["decisions"]["M2_CHECKPOINT_A"] == "NOT_APPROVED_PENDING_VERIFICATION_V2"
    assert policy["decisions"]["M5_1225578520"] == "NOT_MATERIAL"
    assert policy["decisions"]["M7_FINAL_UX"] == "PENDING"
    assert canonical_digest(policy) == receipt.sha256()

    path = tmp_path / "receipt.json"
    path.write_text(receipt.to_json(), encoding="utf-8")
    loaded = load_human_milestone_receipt(path)
    assert loaded.as_policy() == policy


def test_receipt_rejects_overall_checkpoint_pass():
    decisions = dict(DECISIONS)
    decisions["M2_CHECKPOINT_A"] = "PASS"
    with pytest.raises(ValueError, match="M2_CHECKPOINT_A"):
        HumanMilestoneReviewReceipt(
            receipt_id="bad",
            sequence=1,
            reviewed_at=REVIEWED_AT,
            review_scope="bad",
            decisions=decisions,
        )


def test_m5_binding_is_hash_bound_and_not_an_order():
    binding = _binding()
    assert binding.pdf_sha256 == "7c669db8bb3b5a362ecad92c6a96745a3b5039a3288f5e13b498e9e72971111c"
    assert binding.human_decision == "NOT_MATERIAL"
    with pytest.raises(ValueError, match="SHA-256"):
        M5HumanMaterialityBinding(
            symbol="600887",
            announcement_id="1225578520",
            human_decision="NOT_MATERIAL",
            pdf_path="runtime/m5/1225578520.pdf",
            pdf_sha256="g" * 64,
            reviewed_at=REVIEWED_AT,
        )


def test_receipt_writes_append_only_and_binds_predecessor(tmp_path: Path):
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first_output = write_human_milestone_receipt(_receipt(1), first_dir)
    first_path = Path(first_output["path"])

    second = HumanMilestoneReviewReceipt(
        receipt_id="human-review-v2-2",
        sequence=2,
        reviewed_at=REVIEWED_AT,
        review_scope="M2/M3/M5/M7 user-perspective review",
        decisions=DECISIONS,
        m5_bindings=(_binding(),),
        previous_receipt_sha256=first_output["sha256"],
    )
    second_output = write_human_milestone_receipt(second, second_dir, first_path)
    assert load_human_milestone_receipt(Path(second_output["path"])).sequence == 2

    with pytest.raises(ValueError, match="already exists"):
        write_human_milestone_receipt(_receipt(1), first_dir)
    broken = HumanMilestoneReviewReceipt(
        receipt_id="human-review-v2-3",
        sequence=3,
        reviewed_at=REVIEWED_AT,
        review_scope="M2/M3/M5/M7 user-perspective review",
        decisions=DECISIONS,
        m5_bindings=(_binding(),),
        previous_receipt_sha256="0" * 64,
    )
    with pytest.raises(ValueError, match="predecessor"):
        write_human_milestone_receipt(broken, tmp_path / "broken", first_path)


def _require_real_artifacts() -> None:
    required = (
        "runtime/m2-channel-verification-20260924-v2/report.json",
        "runtime/m2-channel-verification-20260924-v2/manifest.json",
        "runtime/m5-disclosure-review-20260923T213249Z/600887/announcements/2026-09-24/1225578520.pdf",
        "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx",
        "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.m7-daily-workbench-manifest.json",
    )
    if any(not (ROOT / item).exists() for item in required):
        pytest.skip("M2 Checkpoint A v2 real artifacts are not present in clean CI")


def test_real_checkpoint_a_packet_stays_pending_human_review():
    _require_real_artifacts()
    spec = importlib.util.spec_from_file_location(
        "checkpoint_a_builder",
        ROOT / "scripts" / "build_m2_checkpoint_a_v2_human_packet.py",
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    packet = builder.build_packet(
        generated_at=datetime(2026, 9, 24, 18, 0, tzinfo=timezone(timedelta(hours=8))),
        reviewed_at=REVIEWED_AT,
    )
    totals = packet["verification"]["totals"]
    assert packet["schema_version"] == M2_CHECKPOINT_A_V2_PACKET_SCHEMA
    assert packet["machine_acceptance_status"] == "CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION"
    assert packet["human_checkpoint_a_status"] == "NOT_APPROVED_PENDING_VERIFICATION_V2"
    assert totals["VERIFIED_FOR_DEEP_RESEARCH"] == 0
    assert totals["REJECTED_AFTER_VERIFICATION"] == 13
    assert totals["INSUFFICIENT_EVIDENCE"] == 5
    assert packet["verification"]["v1_status"] == "SEMANTICALLY_SUPERSEDED"
    assert packet["verification"]["pit_status"] == "PASS"
    assert packet["m5_human_materiality"]["binding"]["human_decision"] == "NOT_MATERIAL"
    assert "Checkpoint A=PASS" in packet["forbidden_interpretations"]
    assert packet["action"] == ACTION_NO_ORDER
