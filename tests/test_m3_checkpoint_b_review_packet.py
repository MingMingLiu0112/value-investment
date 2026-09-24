from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _require_real_artifacts() -> None:
    required = (
        "A股价值投资_M3决策卡候选_20260924.xlsx",
        "A股价值投资_M3决策卡候选_20260924.manifest.json",
        "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.xlsx",
        "A股价值投资_Agent前端智能跟踪模板_M3决策复核候选_20260924.candidate.manifest.json",
        "A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.xlsx",
        "A股价值投资_Agent前端智能跟踪模板_M3历史链叠加候选_20260924.candidate.manifest.json",
        "A股价值投资_M3历史链候选_20260924.xlsx",
        "A股价值投资_M3历史链候选_20260924.manifest.json",
        "A股价值投资_Agent前端智能跟踪模板.xlsx",
    )
    if any(not (ROOT / item).is_file() for item in required):
        pytest.skip("M3 Checkpoint B workbook artifacts are not present in clean CI")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "m3_checkpoint_b_review_builder",
        ROOT / "scripts" / "build_m3_checkpoint_b_review_packet.py",
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def test_m3_checkpoint_b_review_packet_is_read_only_and_fail_closed():
    _require_real_artifacts()
    builder = _load_builder()
    packet = builder.build_packet(
        generated_at=datetime(
            2026,
            9,
            24,
            20,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
    )

    assert packet["action"] == "no_order"
    assert packet["checkpoint_b_status"] == "PENDING_HUMAN_REVIEW"
    assert packet["overall_product_status"] == "PARTIAL"
    assert packet["strict_contemporaneous_rule_pit"] == "NOT_PROVEN"
    assert packet["m2_governance"]["status"] == "HUMAN_PASS"
    assert [row["symbol"] for row in packet["cards"]] == [
        "000651",
        "600741",
        "600887",
    ]
    assert all(row["action"] == "no_order" for row in packet["cards"])
    assert all(
        packet["machine_gates"][name]["status"] == "PENDING_HUMAN_REVIEW"
        for name in ("decision_card", "original_workbook", "history_overlay")
    )

    markdown = builder.render_markdown(packet)
    assert "代理不能替用户签收 Checkpoint B" in markdown
    assert "strict_contemporaneous_rule_pit=NOT_PROVEN" in markdown
    assert "000651" in markdown
    assert "600887" in markdown


def test_m3_checkpoint_b_review_packet_rejects_tampered_workbook():
    _require_real_artifacts()
    builder = _load_builder()
    original_path = builder.DECISION_WORKBOOK
    with tempfile.TemporaryDirectory(
        prefix="m3-checkpoint-b-tamper-",
        dir=ROOT / "runtime",
    ) as temp_dir:
        tampered = Path(temp_dir) / "tampered.xlsx"
        tampered.write_bytes(original_path.read_bytes() + b"tamper")
        builder.PINNED_SHA256[tampered] = builder.PINNED_SHA256[original_path]
        builder.DECISION_WORKBOOK = tampered
        try:
            with pytest.raises(ValueError, match="changed"):
                builder.build_packet(
                    generated_at=datetime(
                        2026,
                        9,
                        24,
                        20,
                        30,
                        tzinfo=timezone(timedelta(hours=8)),
                    )
                )
        finally:
            builder.DECISION_WORKBOOK = original_path
            builder.PINNED_SHA256.pop(tampered, None)
