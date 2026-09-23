from __future__ import annotations

from datetime import datetime, timezone
import hashlib

import pytest

from value_investment_agent.m3_decision_application import (
    build_nonpersonal_decision_card_collection,
)
from value_investment_agent.m3_decision_card_workbook import (
    EVIDENCE_SHEET,
    MISSING_SHEET,
    OVERVIEW_SHEET,
    SOURCE_SHEET,
    build_decision_card_workbook,
    write_decision_card_workbook,
)


GENERATED_AT = datetime(2026, 9, 23, 11, 42, 28, tzinfo=timezone.utc)
NAMES = {
    "000651": "格力电器",
    "600741": "华域汽车",
    "600887": "伊利股份",
}


def _run(symbol: str) -> dict:
    return {
        "run_id": f"{symbol}-m1-run",
        "symbol": symbol,
        "status": "COMPLETED_WITH_BLOCKERS",
        "action": "no_order",
        "pre_decision_eligibility": {
            "schema_version": "post-m1-predecision-eligibility-v1",
            "symbol": symbol,
            "decision_as_of": "2026-09-22",
            "status": "NOT_ELIGIBLE",
            "approval_status": "REJECTED_NEEDS_REWORK",
            "model_validity_status": "STALE",
            "price_bridge_status": "STALE_MODEL",
            "event_review_watermark": "2026-09-22",
            "blockers": ["research_gate_not_ready"],
            "evidence_refs": [
                {
                    "id": f"{symbol}-filing",
                    "kind": "official_issuer_filing",
                    "source_url": f"https://example.com/{symbol}.pdf",
                    "sha256": "a" * 64,
                }
            ],
            "action": "no_order",
        },
        "gate": {"conclusion": "估值未就绪", "blockers": ["research_gate_not_ready"]},
        "human_approval": {
            "symbol": symbol,
            "status": "REJECTED_NEEDS_REWORK",
            "blockers": ["research_gate_not_ready"],
            "action": "no_order",
        },
        "valuation": {
            "symbol": symbol,
            "model_type": "fixture",
            "valuation_date": "2026-09-22",
            "confidence": "低",
            "status": "conditional_research_only",
        },
        "model_validity": {"symbol": symbol, "status": "STALE", "blockers": []},
        "price_bridge": {
            "symbol": symbol,
            "bridge_status": "STALE_MODEL",
            "blockers": [],
        },
        "price_attractiveness": {
            "symbol": symbol,
            "status": "NOT_ASSESSABLE",
            "blockers": [],
        },
        "current_research_status": {
            "symbol": symbol,
            "research_conclusion": "估值未就绪",
            "blockers": [],
        },
    }


def _collection():
    return build_nonpersonal_decision_card_collection(
        [_run("000651"), _run("600741"), _run("600887")],
        generated_at=GENERATED_AT,
        source_run_id="fixture-m1-run",
    )


def _all_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_workbook_displays_negative_cards_and_missing_inputs_without_signals():
    workbook = build_decision_card_workbook(
        _collection(),
        security_names=NAMES,
    )

    assert workbook.sheetnames == [
        OVERVIEW_SHEET,
        MISSING_SHEET,
        SOURCE_SHEET,
        EVIDENCE_SHEET,
    ]
    overview = workbook[OVERVIEW_SHEET]
    assert overview["A5"].value == "000651"
    assert overview["B5"].value == "格力电器"
    assert overview["D5"].value == "研究证据不足"
    assert overview["F5"].value == "未提交"
    assert overview["G5"].value == "缺失"
    assert overview["H5"].value == "本卡不需要"
    assert overview["I5"].value == "无"
    assert overview["A7"].value == "600887"

    text = _all_text(workbook)
    assert "action=no_order" in text
    assert "全部卡片均要求人工复核" in text
    assert "研究与估值前置条件未完成" in text
    assert "用户尚未提供个人组合输入" in text
    assert "买入" not in text
    assert "加仓" not in text
    assert "减仓" not in text
    assert "目标仓位" not in text
    assert "BUY" not in text
    assert "ADD" not in text
    assert workbook[EVIDENCE_SHEET]["E5"].hyperlink.target == "https://example.com/000651.pdf"


def test_writer_is_hash_pinned_and_never_overwrites(tmp_path):
    output = tmp_path / "m3-candidate.xlsx"
    result = write_decision_card_workbook(
        _collection(),
        output=output,
        root=tmp_path,
        security_names=NAMES,
    )

    target = tmp_path / result["workbook_path"]
    assert target.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    assert result["card_count"] == 3
    assert result["positive_review_count"] == 0
    assert result["action"] == "no_order"

    with pytest.raises(ValueError, match="already exists"):
        write_decision_card_workbook(
            _collection(),
            output=output,
            root=tmp_path,
            security_names=NAMES,
        )
