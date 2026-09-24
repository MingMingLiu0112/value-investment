from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _require_real_artifacts() -> None:
    required = (
        "runtime/m3-checkpoint-b-human-review-20260924-v1/checkpoint-b-packet.json",
        "runtime/company-research/000651-m1-dossier-20260923T004117Z/evidence.json",
        "runtime/company-research/600741-m1-dossier-20260923T004123Z/evidence.json",
        "runtime/company-research/600887-m1-dossier-20260923T004120Z/evidence.json",
    )
    if any(not (ROOT / item).is_file() for item in required):
        pytest.skip("M3 Checkpoint B detail inputs are not present in clean CI")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "m3_checkpoint_b_review_detail_builder",
        ROOT / "scripts" / "build_m3_checkpoint_b_review_detail.py",
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def test_review_detail_binds_frozen_dossiers_and_remains_pending() -> None:
    _require_real_artifacts()
    builder = _load_builder()
    packet = builder.build_detail_packet(
        generated_at=datetime(
            2026,
            9,
            24,
            21,
            30,
            tzinfo=timezone(timedelta(hours=8)),
        )
    )

    assert packet["action"] == "no_order"
    assert packet["checkpoint_b_status"] == "PENDING_HUMAN_REVIEW"
    assert packet["base_packet"]["sha256"] == (
        "fab538fb283b55b449d6c52be908216cbe2df06880a2c66848901371a15c7eb4"
    )
    assert [card["symbol"] for card in packet["cards"]] == [
        "000651",
        "600741",
        "600887",
    ]
    for card in packet["cards"]:
        assert card["action"] == "no_order"
        assert card["system_status"] == "INSUFFICIENT_RESEARCH"
        assert card["strongest_blocker"]
        assert card["counter_evidence"]
        assert card["thesis_breakers"]
        assert card["next_events"]
        assert card["reopen_condition"]
        assert card["research_gaps"]
        assert card["evidence_sources"]
        assert card["dossier"]["sha256"] == builder.PINNED_SHA256[
            builder.DOSSIERS[card["symbol"]]
        ]

    markdown = builder.render_markdown(packet)
    assert "M3 Checkpoint B 复核明细" in markdown
    assert "不签收" in markdown
    assert "action=no_order" in markdown
    assert "000651" in markdown
    assert "600741" in markdown
    assert "600887" in markdown
    assert "BUY/ADD" in markdown
    assert "{'kind':" not in markdown


def test_review_detail_rejects_tampered_dossier() -> None:
    _require_real_artifacts()
    builder = _load_builder()
    original_path = builder.DOSSIERS["000651"]
    with tempfile.TemporaryDirectory(
        prefix="m3-review-detail-tamper-",
        dir=ROOT / "runtime",
    ) as temp_dir:
        tampered = Path(temp_dir) / "tampered.json"
        tampered.write_bytes(original_path.read_bytes() + b"\n")
        builder.DOSSIERS["000651"] = tampered
        builder.PINNED_SHA256[tampered] = builder.PINNED_SHA256[original_path]
        try:
            with pytest.raises(ValueError, match="changed"):
                builder.build_detail_packet(
                    generated_at=datetime(
                        2026,
                        9,
                        24,
                        21,
                        30,
                        tzinfo=timezone(timedelta(hours=8)),
                    )
                )
        finally:
            builder.DOSSIERS["000651"] = original_path
            builder.PINNED_SHA256.pop(tampered, None)
