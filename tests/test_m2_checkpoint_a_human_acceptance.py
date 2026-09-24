from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _require_real_artifacts() -> None:
    required = (
        "runtime/m2-channel-verification-20260924-v2/report.json",
        "runtime/m2-channel-verification-20260924-v2/manifest.json",
        "runtime/m2-checkpoint-a-human-resubmission-20260924-v2/receipt.json",
        "runtime/m5-disclosure-review-20260923T213249Z/600887/announcements/2026-09-24/1225578520.pdf",
        "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.xlsx",
        "A股价值投资_Agent前端智能跟踪模板_M7每日工作台候选_v3_20260924.m7-daily-workbench-manifest.json",
    )
    if any(not (ROOT / item).exists() for item in required):
        pytest.skip("M2 Checkpoint A human-acceptance artifacts are not present in clean CI")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "checkpoint_a_acceptance_builder",
        ROOT / "scripts" / "build_m2_checkpoint_a_human_acceptance.py",
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def test_real_checkpoint_a_human_acceptance_is_append_only_and_no_order():
    _require_real_artifacts()
    builder = _load_builder()

    packet = builder.build_acceptance_packet(
        generated_at=datetime(
            2026,
            9,
            24,
            19,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        ),
        reviewed_at=date(2026, 9, 24),
    )

    receipt = packet["human_receipt"]
    assert packet["action"] == "no_order"
    assert packet["m2_acceptance_status"] == "DONE"
    assert packet["human_checkpoint_a_status"] == "HUMAN_PASS"
    assert packet["overall_product_status"] == "PARTIAL"
    assert receipt["sequence"] == 2
    assert receipt["previous_receipt_sha256"] == builder.PREVIOUS_RECEIPT_SHA256
    assert packet["previous_receipt"]["sha256"] == builder.PREVIOUS_RECEIPT_SHA256
    assert {item["id"] for item in packet["backlog"]} == {
        "BL-20260924-001",
        "BL-20260924-002",
    }
    assert all(item["blocking"] is False for item in packet["backlog"])
    assert "M2 Checkpoint A: verify true second-stage semantics in M7 v3" not in (
        packet["pending_human_items"]
    )
