from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

import pytest

from value_investment_agent.investment_decision import (
    ACTION_NO_ORDER,
    CONSISTENCY_BROKEN,
    COMPARISON_BROKEN,
    COMPARISON_NEGATIVE,
    COMPARISON_NEUTRAL,
    DIMENSION_RETURN_DRIVER,
    DIMENSION_THESIS,
    ENTRY_TYPE_ACTUAL,
    ENTRY_TYPE_SIMULATED,
    HUMAN_CONFIRM_BUY,
    HUMAN_CONFIRM_HOLD,
    HUMAN_CONFIRM_REDUCE,
    STATUS_HOLD,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_MANUAL_REDUCE_REVIEW,
)
from value_investment_agent.m3_history_read_model import (
    M3_HISTORY_INPUT_SCHEMA,
    M3_HISTORY_SCHEMA,
    PUBLIC_NAMESPACE,
    build_decision_history_collection,
    build_history_chain_from_payloads,
)
from value_investment_agent.m3_history_workbook import (
    CONSISTENCY_SHEET,
    ENTRY_SHEET,
    JOURNAL_SHEET,
    OVERVIEW_SHEET,
    SOURCE_SHEET,
    build_history_workbook,
    write_history_workbook,
)


GENERATED_AT = datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc)
SYMBOL = "600887"
NAMES = {SYMBOL: "伊利股份"}


def _entry_payload() -> dict:
    return {
        "schema_version": "m3-investment-decision-v1",
        "entry_id": f"{SYMBOL}-sim-entry-v1",
        "symbol": SYMBOL,
        "confirmed_at": "2026-09-01T02:00:00+00:00",
        "entry_type": ENTRY_TYPE_SIMULATED,
        "entry_date": "2026-09-01",
        "entry_price": "20",
        "review_id": f"{SYMBOL}-buy-review-v1",
        "bundle_id": f"{SYMBOL}-buy-bundle-v1",
        "thesis": "模拟：长期消费品牌仍具有稳定现金生成能力",
        "return_driver": "模拟：产品结构改善带动盈利能力",
        "mispricing_hypothesis": "市场低估了盈利韧性",
        "bear_value": "16",
        "base_value": "20",
        "bull_value": "24",
        "confidence": "中",
        "dividend_thesis": "模拟：分红能力与经营现金相匹配",
        "hold_logic": "只要论点未破坏且估值未极端高估",
        "risks": ["需求下降"],
        "counter_evidence": ["行业竞争加剧"],
        "breakers": ["现金流持续恶化"],
        "catalysts": ["年度报告"],
        "reasons_to_add": ["证据增强且组合容量允许"],
        "reasons_not_to_add": ["论点削弱时不加仓"],
        "reasons_to_reduce": ["原回报驱动明显减弱"],
        "reasons_to_exit": ["原始论点被证实破坏"],
        "reconstructed_note": "",
        "action": ACTION_NO_ORDER,
    }


def _journal_payloads() -> list[dict]:
    return [
        {
            "schema_version": "m3-investment-decision-v1",
            "journal_id": f"{SYMBOL}-journal-buy-v1",
            "symbol": SYMBOL,
            "decision_at": "2026-09-01T02:05:00+00:00",
            "review_id": f"{SYMBOL}-buy-review-v1",
            "review_status": STATUS_MANUAL_BUY_REVIEW,
            "system_reason": "模拟系统理由：研究链完整，但最终决定由人工完成",
            "human_decision": HUMAN_CONFIRM_BUY,
            "human_reason": "模拟人工理由：认可原始论点",
            "entry_id": f"{SYMBOL}-sim-entry-v1",
            "confirmed_price": "20",
            "namespace": ENTRY_TYPE_SIMULATED,
            "previous_journal_id": None,
            "action": ACTION_NO_ORDER,
        },
        {
            "schema_version": "m3-investment-decision-v1",
            "journal_id": f"{SYMBOL}-journal-hold-v1",
            "symbol": SYMBOL,
            "decision_at": "2026-09-15T02:05:00+00:00",
            "review_id": f"{SYMBOL}-hold-review-v1",
            "review_status": STATUS_HOLD,
            "system_reason": "模拟系统理由：尚无破坏性证据",
            "human_decision": HUMAN_CONFIRM_HOLD,
            "human_reason": "模拟人工理由：继续观察",
            "entry_id": f"{SYMBOL}-sim-entry-v1",
            "confirmed_price": None,
            "namespace": ENTRY_TYPE_SIMULATED,
            "previous_journal_id": None,
            "action": ACTION_NO_ORDER,
        },
        {
            "schema_version": "m3-investment-decision-v1",
            "journal_id": f"{SYMBOL}-journal-reduce-v1",
            "symbol": SYMBOL,
            "decision_at": "2026-09-24T02:05:00+00:00",
            "review_id": f"{SYMBOL}-reduce-review-v1",
            "review_status": STATUS_MANUAL_REDUCE_REVIEW,
            "system_reason": "模拟系统理由：原始回报驱动出现减弱证据",
            "human_decision": HUMAN_CONFIRM_REDUCE,
            "human_reason": "模拟人工理由：按减仓条件执行",
            "entry_id": f"{SYMBOL}-sim-entry-v1",
            "confirmed_price": "22",
            "namespace": ENTRY_TYPE_SIMULATED,
            "previous_journal_id": None,
            "action": ACTION_NO_ORDER,
        },
    ]


def _consistency_payloads() -> list[dict]:
    return [
        {
            "schema_version": "m3-investment-decision-v1",
            "review_id": f"{SYMBOL}-consistency-20260923",
            "symbol": SYMBOL,
            "entry_id": f"{SYMBOL}-sim-entry-v1",
            "as_of": "2026-09-23",
            "status": "WEAKENED",
            "comparisons": [
                {
                    "dimension": DIMENSION_RETURN_DRIVER,
                    "original_value": "产品结构改善",
                    "current_value": "改善速度低于预期",
                    "impact": COMPARISON_NEGATIVE,
                    "change_reason": "模拟新证据",
                    "evidence_refs": [{"id": "sim-evidence-1"}],
                },
                {
                    "dimension": DIMENSION_THESIS,
                    "original_value": "长期品牌韧性",
                    "current_value": "长期品牌韧性",
                    "impact": COMPARISON_NEUTRAL,
                    "change_reason": "",
                    "evidence_refs": [],
                },
            ],
            "blockers": [],
            "evidence_refs": [{"id": "sim-evidence-1"}],
            "action": ACTION_NO_ORDER,
        },
        {
            "schema_version": "m3-investment-decision-v1",
            "review_id": f"{SYMBOL}-consistency-20260924",
            "symbol": SYMBOL,
            "entry_id": f"{SYMBOL}-sim-entry-v1",
            "as_of": "2026-09-24",
            "status": CONSISTENCY_BROKEN,
            "comparisons": [
                {
                    "dimension": DIMENSION_RETURN_DRIVER,
                    "original_value": "产品结构改善",
                    "current_value": "驱动已破坏",
                    "impact": COMPARISON_BROKEN,
                    "change_reason": "模拟新证据",
                    "evidence_refs": [{"id": "sim-evidence-2"}],
                }
            ],
            "blockers": ["sim-breaker"],
            "evidence_refs": [{"id": "sim-evidence-2"}],
            "action": ACTION_NO_ORDER,
        },
    ]


def _chain():
    return build_history_chain_from_payloads(
        entry_payload=_entry_payload(),
        journal_payloads=_journal_payloads(),
        consistency_payloads=_consistency_payloads(),
    )


def _collection():
    return build_decision_history_collection(
        generated_at=GENERATED_AT,
        source_id="simulated-m3-history-v1",
        chains=[_chain()],
    )


def _all_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for sheet in workbook
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_history_chain_orders_journals_and_preserves_source_hashes():
    chain = _chain()

    assert chain.symbol == SYMBOL
    assert chain.namespace == PUBLIC_NAMESPACE
    assert [item.journal_id for item in chain.journals] == [
        f"{SYMBOL}-journal-buy-v1",
        f"{SYMBOL}-journal-hold-v1",
        f"{SYMBOL}-journal-reduce-v1",
    ]
    assert chain.latest_journal.human_decision == HUMAN_CONFIRM_REDUCE
    assert chain.latest_consistency.status == CONSISTENCY_BROKEN
    assert chain.entry.source_sha256 == chain.entry.source_sha256.lower()
    assert all(item.source_sha256 for item in chain.journals)
    assert all(item.source_sha256 for item in chain.consistency_reviews)
    assert len(json.loads(_collection().to_json())["chains"]) == 1


def test_public_history_rejects_actual_namespace():
    payload = _entry_payload()
    payload["entry_type"] = ENTRY_TYPE_ACTUAL

    with pytest.raises(ValueError, match="must be simulated"):
        build_history_chain_from_payloads(
            entry_payload=payload,
            journal_payloads=_journal_payloads(),
        )


def test_public_history_rejects_journal_bound_to_another_entry():
    payloads = _journal_payloads()
    payloads[0]["entry_id"] = f"{SYMBOL}-other-entry-v1"

    with pytest.raises(ValueError, match="does not match the frozen entry"):
        build_history_chain_from_payloads(
            entry_payload=_entry_payload(),
            journal_payloads=payloads,
        )


def test_public_history_rejects_duplicate_journal_ids():
    payloads = _journal_payloads()
    payloads[1]["journal_id"] = payloads[0]["journal_id"]

    with pytest.raises(ValueError, match="journal ids must be unique"):
        build_history_chain_from_payloads(
            entry_payload=_entry_payload(),
            journal_payloads=payloads,
        )


def test_public_history_rejects_correction_that_precedes_predecessor():
    payloads = _journal_payloads()
    payloads[2]["previous_journal_id"] = payloads[1]["journal_id"]
    payloads[2]["decision_at"] = "2026-09-10T02:05:00+00:00"

    with pytest.raises(ValueError, match="cannot precede its predecessor"):
        build_history_chain_from_payloads(
            entry_payload=_entry_payload(),
            journal_payloads=payloads,
        )


def test_public_history_rejects_duplicate_consistency_review_ids():
    payloads = _consistency_payloads()
    payloads[1]["review_id"] = payloads[0]["review_id"]

    with pytest.raises(ValueError, match="review ids must be unique"):
        build_history_chain_from_payloads(
            entry_payload=_entry_payload(),
            journal_payloads=_journal_payloads(),
            consistency_payloads=payloads,
        )


def test_workbook_displays_simulated_chain_without_order_or_position_columns():
    workbook = build_history_workbook(_collection(), security_names=NAMES)

    assert workbook.sheetnames == [
        OVERVIEW_SHEET,
        ENTRY_SHEET,
        JOURNAL_SHEET,
        CONSISTENCY_SHEET,
        SOURCE_SHEET,
    ]
    text = _all_text(workbook)
    assert "模拟演示链路" in text
    assert "action=no_order" not in text
    assert "no_order" in text
    assert "原始论点一致性复核" in text
    assert "目标仓位" not in text
    assert "下单" not in text
    assert "自动卖出" not in text
    assert workbook[OVERVIEW_SHEET]["A5"].value == SYMBOL
    assert workbook[OVERVIEW_SHEET]["G5"].value == "确认减仓"
    assert workbook[OVERVIEW_SHEET]["H5"].value == "已破坏"


def test_writer_is_hash_pinned_and_never_overwrites(tmp_path):
    result = write_history_workbook(
        _collection(),
        output=tmp_path / "m3-history.xlsx",
        root=tmp_path,
        security_names=NAMES,
    )

    target = tmp_path / result["workbook_path"]
    assert target.exists()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == result["workbook_sha256"]
    assert result["chain_count"] == 1
    assert result["namespace"] == PUBLIC_NAMESPACE
    assert result["action"] == ACTION_NO_ORDER

    with pytest.raises(ValueError, match="already exists"):
        write_history_workbook(
            _collection(),
            output=tmp_path / "m3-history.xlsx",
            root=tmp_path,
            security_names=NAMES,
        )
