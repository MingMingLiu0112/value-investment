from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from openpyxl import load_workbook
import pytest

from value_investment_agent.m7_daily_workbench import (
    ACTION_NO_ORDER,
    HIDDEN_SHEETS,
    SCHEMA_VERSION,
    VISIBLE_SHEETS,
    build_daily_workbench,
    write_daily_workbench,
)

ROOT = Path(__file__).resolve().parents[1]


def _packet() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": "2026-09-24T02:00:00+00:00",
        "as_of": "2026-09-24",
        "action": ACTION_NO_ORDER,
        "m2": {
            "status": "PENDING_HUMAN_REVIEW",
            "acceptance_status": "CHECKPOINT_A_READY_FOR_HUMAN_RESUBMISSION",
            "verification_version": "v2",
            "v1_status": "SEMANTICALLY_SUPERSEDED",
            "pit_status": "PASS",
            "lead_count": 18,
            "verified_count": 0,
            "rejected_count": 13,
            "insufficient_count": 5,
            "unsupported_count": 0,
            "verified_symbols": [],
            "verified_channels": [],
            "verification_channel_counts": {
                "quality": {
                    "total_leads": 0,
                    "verified": 0,
                    "rejected": 0,
                    "insufficient": 0,
                    "unsupported": 0,
                },
                "dividend_cash_return": {
                    "total_leads": 6,
                    "verified": 0,
                    "rejected": 3,
                    "insufficient": 3,
                    "unsupported": 0,
                },
                "value": {
                    "total_leads": 6,
                    "verified": 0,
                    "rejected": 5,
                    "insufficient": 1,
                    "unsupported": 0,
                },
                "cyclical": {
                    "total_leads": 6,
                    "verified": 0,
                    "rejected": 5,
                    "insufficient": 1,
                    "unsupported": 0,
                },
            },
            "channel_counts": {
                "quality": 0,
                "dividend_cash_return": 50,
                "value": 50,
                "cyclical": 50,
            },
            "budget_by_channel": {
                "quality": 0,
                "dividend_cash_return": 369,
                "value": 351,
                "cyclical": 1535,
            },
            "budget_excluded_count": 2255,
            "quality": {
                "universe_count": 5568,
                "evidence_count": 873,
                "pass_count": 0,
                "data_gap_count": 4672,
                "coverage_status": "COVERAGE_LIMITED",
            },
            "value_disclaimer": (
                "市场估值线索：PE/PB/隐含 ROE 初筛。"
                "尚未验证 FCF Yield、EV/EBIT、正常化盈利和资产负债表质量。"
            ),
            "rows": [
                {
                    "symbol": "002327",
                    "name": "富安娜",
                    "channel": "dividend_cash_return",
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reason": "股息通道仍缺多财年普通股息、自由现金流覆盖与可持续性证据。",
                    "evidence_count": 16,
                },
                {
                    "symbol": "002867",
                    "name": "周大生",
                    "channel": "dividend_cash_return",
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reason": "普通股息与特别股息不可归一为多年可持续股息。",
                    "evidence_count": 18,
                },
                {
                    "symbol": "600011",
                    "name": "华能国际",
                    "channel": "dividend_cash_return",
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reason": "股息覆盖与正常化现金回报仍缺必要财年证据。",
                    "evidence_count": 14,
                },
                {
                    "symbol": "000913",
                    "name": "钱江摩托",
                    "channel": "cyclical",
                    "status": "REJECTED_AFTER_VERIFICATION",
                    "reason": "低 PE/PB 不能替代正常化盈利与周期位置证据。",
                    "evidence_count": 36,
                },
                {
                    "symbol": "000151",
                    "name": "中成股份",
                    "channel": "value",
                    "status": "INSUFFICIENT_EVIDENCE",
                    "reason": "正常化收益与资产负债表质量证据不足。",
                    "evidence_count": 0,
                },
            ],
        },
        "m3": {
            "status": "PARTIAL",
            "checkpoint_b_status": "NOT_APPROVED_YET",
            "positive_price_safety": (
                "只有 RESEARCH_ATTRACTIVE 可形成正向价格复核；"
                "其余价格状态不得产生 BUY/ADD。"
            ),
            "negative_cards": [
                {
                    "symbol": "000651",
                    "name": "格力电器",
                    "status": "INSUFFICIENT_RESEARCH",
                    "reason_kind": "RESEARCH_INCOMPLETE",
                    "blockers": ["research_gate_not_ready", "model_validity_stale"],
                }
            ],
            "simulated_history_status": "SIMULATED / PASS_AS_STRUCTURE_ONLY",
            "historical_replay": {
                "symbol": "600519",
                "replay_date": "2024-06-21",
                "final_decision": "WAIT",
                "valuation_approved": False,
                "trade_approved": False,
                "blockers": ["valuation_approved_false", "trade_approved_false"],
                "future_facts_used": False,
                "future_rule_version_used": True,
                "then_known_facts": {"source_id": "cninfo:1219506510"},
                "then_known_quote": {"close_cny": "1471.00"},
                "rule": {"rule_version": "moutai-pe-mid-paper-contract-v2-2025-extension"},
            },
        },
        "m4": {
            "status": "ENGINEERING_DONE_SIMULATED",
            "decision_binding_status": "ENGINEERING_DONE",
            "private_input_status": "PENDING_USER_PRIVATE_INPUT",
            "new_capacity_available": False,
            "required_inputs": ["真实 IPS", "真实持仓"],
            "simulated_engineering_status": "SIMULATED",
        },
        "m5": {
            "status": "ENGINEERING_DONE_OFFLINE",
            "continuous_ops_status": "NOT_READY",
            "current_candidates": 24,
            "carried_forward": 23,
            "pending_human_review": 1,
            "hash_conflicts": 0,
            "superseded_pending": 0,
            "pending_items": [
                {
                    "symbol": "600887",
                    "announcement_id": "1225578520",
                    "title": "员工持股计划完成股票购买公告",
                    "source_url": "https://example.invalid/announcement.PDF",
                    "current_source_sha256": "a" * 64,
                }
            ],
        },
        "m6": {
            "status": "PREFLIGHT_DONE",
            "engineering_status": "DONE",
            "operational_status": "NOT_STARTED",
            "blockers": ["no real restore drill"],
        },
        "audit": {
            "action": ACTION_NO_ORDER,
            "audit_workbook": "A股价值投资_Agent前端智能跟踪模板_M7统一工作台候选_v2_20260924.xlsx",
            "audit_workbook_sha256": "b" * 64,
            "canonical_workbook": "A股价值投资_Agent前端智能跟踪模板.xlsx",
            "canonical_workbook_sha256": "c" * 64,
            "production_actions": "NONE",
            "artifacts": [
                {
                    "label": "M2 通道验证报告",
                    "path": "runtime/m2-channel-verification-20260924-v1/report.json",
                    "sha256": "d" * 64,
                    "action": ACTION_NO_ORDER,
                }
            ],
        },
        "stage_statuses": {
            "m2": ["M2", "ENGINEERING_DONE", "PARTIAL", "PENDING_HUMAN_REVIEW"],
            "m7": ["M7", "DISPLAY_ENGINEERING_DONE", "PARTIAL", "PENDING_USER_ACCEPTANCE"],
        },
    }


def _post_checkpoint_a_packet() -> dict:
    packet = copy.deepcopy(_packet())
    packet["m2"].update(
        {
            "status": "DONE",
            "checkpoint_a_status": "HUMAN_PASS",
            "acceptance_status": "HUMAN_PASS",
        }
    )
    packet["m3"]["reconstructed_continuity"] = {
        "trace_id": "600519-reconstructed-evidence-continuity-2024-06-21-v1",
        "symbol": "600519",
        "baseline_date": "2024-06-21",
        "future_rule_version_used": True,
        "strict_contemporaneous_rule_pit": "NOT_PROVEN",
        "conclusion_status": "RECONSTRUCTED_EVIDENCE_ONLY",
        "actual_entry_present": False,
        "human_decision": None,
        "requires_human_review": True,
        "blockers": [
            "strict_contemporaneous_rule_pit_not_proven",
            "reconstructed_not_actual_entry",
            "action_no_order",
        ],
        "comparisons": [
            {
                "dimension": "parent_profit",
                "baseline_value": "74734071550.75",
                "observation_id": "600519-2024-annual",
                "observation_value": "86228146421.62",
                "change_direction": "UP",
                "impact": "STRENGTHENED",
                "arithmetic_note": "FY2024 parent profit is higher.",
            }
        ],
        "action": ACTION_NO_ORDER,
    }
    packet["m5"]["disclosure_queue_600519"] = {
        "queue_id": "cninfo-review-2026-06-01-20260924T084715Z",
        "symbol": "600519",
        "provider": "cninfo",
        "parser_version": "m5-cninfo-announcement-title-v1",
        "scan_from": "2026-06-01",
        "scan_to": "2026-09-09",
        "retrieved_at": "2026-09-24T08:47:15Z",
        "coverage_status": "COMPLETE",
        "total_announcements": 16,
        "pending_count": 9,
        "source_unavailable": 0,
        "pending_items": [
            {
                "announcement_id": "1225475868",
                "published_at": "2026-08-15T00:00:00+08:00",
                "title": "贵州茅台2026年半年度报告",
                "rule_kind": "financial_statement",
                "review_status": "PENDING_HUMAN_REVIEW",
                "source_url": "https://static.cninfo.com.cn/finalpage/2026-08-15/1225475868.PDF",
                "pdf_sha256": "0e10aa26be46b1cf3cd03f06e834c7fb98d5dd0d661b96f8fddd4af7e846a4f6",
            }
        ],
        "action": ACTION_NO_ORDER,
    }
    packet["stage_statuses"]["m2"] = [
        "M2",
        "ENGINEERING_DONE",
        "DONE",
        "HUMAN_PASS",
    ]
    return packet


def _all_text(workbook) -> str:
    values = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            values.extend(str(value) for value in row if value is not None)
    return "\n".join(values)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_daily_workbench_has_nine_visible_and_two_hidden_sheets(tmp_path: Path):
    packet = _packet()
    workbook = build_daily_workbench(packet)

    assert workbook.sheetnames[:10] == list(VISIBLE_SHEETS)
    assert workbook.sheetnames[10:] == list(HIDDEN_SHEETS)
    assert all(workbook[name].sheet_state != "hidden" for name in VISIBLE_SHEETS)
    assert all(workbook[name].sheet_state == "hidden" for name in HIDDEN_SHEETS)


def test_overview_is_explicitly_fail_closed_and_no_order(tmp_path: Path):
    receipt = write_daily_workbench(
        _packet(),
        output=tmp_path / "daily.xlsx",
        root=tmp_path,
    )
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    text = _all_text(workbook)

    assert "0 个深研候选不等于 0 个买入目标" in text
    assert "当前无任何可用订单" in text
    assert "0 条。当前没有 BUY / ADD 复核可进入" in text
    assert "真实 IPS / 持仓尚未由用户提供" in text
    for forbidden in ("建议买入", "建议加仓", "目标仓位", "下单"):
        assert forbidden not in text
    assert receipt["action"] == ACTION_NO_ORDER
    assert receipt["summary"]["m2_verified_for_deep_research"] == 0
    assert receipt["summary"]["m5_new_pending_reviews"] == 1


def test_actual_event_sheet_explains_dependency_and_not_ready_boundary():
    packet = _packet()
    packet["m5"]["actual_event_chain"] = {
        "reviewed_count": 1, "pending_human_review": 0, "verified_fact_count": 1,
        "rows": [{
            "announcement_id": "1225475868", "materiality": "MATERIAL_REQUIRES_RECALCULATION",
            "title": "2026 half-year report", "affected_dependencies": ["financial_facts", "valuation_inputs"],
            "recalculation_status": "STILL_NOT_READY",
            "blockers": ["missing_dependency_node:valuation_inputs"],
            "pdf_sha256": "a" * 64, "event_id": "event-1",
            "requires_human_decision_review": True, "new_valuation_result": None,
            "action": ACTION_NO_ORDER,
        }],
        "action": ACTION_NO_ORDER,
    }
    sheet = build_daily_workbench(packet)[VISIBLE_SHEETS[6]]
    text = "\n".join(str(value) for row in sheet.iter_rows(values_only=True)
                     for value in row if value is not None)
    for expected in ("1225475868", "financial_facts, valuation_inputs", "STILL_NOT_READY",
                     "missing_dependency_node:valuation_inputs", "人工决策复核：需要",
                     "新估值：未生成", "Event ID: event-1"):
        assert expected in text


def test_actual_event_sheet_shows_versioned_result_but_keeps_event_stale():
    packet = _packet()
    packet["m5"]["actual_event_chain"] = {
        "reviewed_count": 1, "pending_human_review": 0, "verified_fact_count": 5,
        "rows": [{
            "announcement_id": "1225475868", "materiality": "MATERIAL_REQUIRES_RECALCULATION",
            "title": "2026 half-year report", "affected_dependencies": ["valuation_inputs"],
            "recalculation_status": "MODEL_STALE",
            "blockers": ["event_bound_model_validity_not_reconciled"],
            "pdf_sha256": "a" * 64, "event_id": "event-1",
            "requires_human_decision_review": True,
            "new_valuation_result": {
                "valuation_date": "2026-06-30", "model_version": "residual-income-v1",
                "artifact_id": "version-2", "payload_sha256": "b" * 64,
                "event_validity_status": "UNRECONCILED",
            },
            "action": ACTION_NO_ORDER,
        }],
        "action": ACTION_NO_ORDER,
    }
    sheet = build_daily_workbench(packet)[VISIBLE_SHEETS[6]]
    text = "\n".join(str(value) for row in sheet.iter_rows(values_only=True)
                     for value in row if value is not None)
    for expected in ("MODEL_STALE", "event_bound_model_validity_not_reconciled",
                     "2026-06-30 / residual-income-v1", "产物 ID：version-2",
                     "事件有效性：UNRECONCILED", "Valuation SHA-256: " + "b" * 64,
                     "人工决策复核：需要"):
        assert expected in text


def test_actual_event_sheet_requires_review_before_showing_recalculated():
    packet = _packet()
    packet["m5"]["actual_event_chain"] = {
        "reviewed_count": 1, "pending_human_review": 0, "verified_fact_count": 5,
        "rows": [{
            "announcement_id": "1225475868", "materiality": "MATERIAL_REQUIRES_RECALCULATION",
            "title": "2026 half-year report", "affected_dependencies": ["valuation_inputs"],
            "recalculation_status": "RECALCULATED", "blockers": [],
            "pdf_sha256": "a" * 64, "event_id": "event-1",
            "requires_human_decision_review": True,
            "new_valuation_result": {
                "valuation_date": "2026-06-30", "model_version": "residual-income-v1",
                "artifact_id": "version-2", "payload_sha256": "b" * 64,
                "event_validity_status": "RECONCILED",
            },
            "action": ACTION_NO_ORDER,
        }],
        "action": ACTION_NO_ORDER,
    }
    with pytest.raises(ValueError, match="reconciled review evidence"):
        build_daily_workbench(packet)
    packet["m5"]["actual_event_chain"]["event_refresh_review_sha256"] = "c" * 64
    sheet = build_daily_workbench(packet)[VISIBLE_SHEETS[6]]
    text = "\n".join(str(value) for row in sheet.iter_rows(values_only=True)
                     for value in row if value is not None)
    assert "RECALCULATED" in text
    assert "事件有效性：RECONCILED" in text
    assert "人工决策复核：需要" in text


def test_market_sheet_shows_limited_quality_coverage_and_value_scope(tmp_path: Path):
    packet = _packet()
    receipt = write_daily_workbench(
        packet,
        output=tmp_path / "daily.xlsx",
        root=tmp_path,
    )
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    market = workbook[VISIBLE_SHEETS[1]]
    values = [str(value) for row in market.iter_rows(values_only=True) for value in row if value is not None]
    text = "\n".join(values)

    assert "873 / 5568 usable quality evidence" in text
    assert "COVERAGE_LIMITED" in text
    assert "不能把 0 个 Quality 候选解释成市场没有高质量公司" in text
    assert "尚未验证 FCF Yield、EV/EBIT、正常化盈利和资产负债表质量" in text
    assert receipt["workbook_sha256"] == _digest(tmp_path / "daily.xlsx")


def test_decision_and_position_sheets_fail_closed(tmp_path: Path):
    packet = _packet()
    write_daily_workbench(
        packet,
        output=tmp_path / "daily.xlsx",
        root=tmp_path,
    )
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    decision = workbook[VISIBLE_SHEETS[3]]
    position = workbook[VISIBLE_SHEETS[4]]
    decision_text = "\n".join(
        str(value) for row in decision.iter_rows(values_only=True) for value in row if value is not None
    )
    position_text = "\n".join(
        str(value) for row in position.iter_rows(values_only=True) for value in row if value is not None
    )

    assert "RESEARCH_ATTRACTIVE" in decision_text
    assert "其余价格状态不得产生 BUY/ADD" in decision_text
    assert "INSUFFICIENT_RESEARCH" in decision_text
    assert "NOT_APPROVED_YET" in decision_text
    assert "PENDING_USER_PRIVATE_INPUT" in position_text
    assert "0。只有有效的 MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW" in position_text


def test_candidate_sheet_exposes_v2_zero_verified_resolutions(tmp_path: Path):
    packet = _packet()
    write_daily_workbench(
        packet,
        output=tmp_path / "daily.xlsx",
        root=tmp_path,
    )
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    candidate = workbook[VISIBLE_SHEETS[2]]
    text = _all_text(workbook)

    assert "LEAD 18 | VERIFIED 0 | REJECTED 13 | INSUFFICIENT 5 | UNSUPPORTED 0" in text
    assert "质量 验证 0 / 否决 0 / 不足 0" in text
    assert "股息/现金回报 验证 0 / 否决 3 / 不足 3" in text
    assert "价值 验证 0 / 否决 5 / 不足 1" in text
    assert "周期 验证 0 / 否决 5 / 不足 1" in text
    assert candidate["D8"].value == "证据不足"
    assert candidate["D11"].value == "通道否决"
    assert "3 个深研候选" not in text


def test_manifest_is_written_with_hash_and_sheet_receipt(tmp_path: Path):
    output = tmp_path / "daily.xlsx"
    receipt = write_daily_workbench(
        _packet(),
        output=output,
        root=tmp_path,
    )
    manifest_path = output.with_name(output.stem + ".m7-daily-workbench-manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["schema_version"] == SCHEMA_VERSION
    assert manifest["action"] == ACTION_NO_ORDER
    assert manifest["workbook_sha256"] == _digest(output)
    assert manifest["visible_sheet_count"] == 10
    assert manifest["hidden_sheet_count"] == 2
    assert receipt["manifest_sha256"] == _digest(manifest_path)


def test_historical_replay_does_not_claim_contemporaneous_rule_pit(tmp_path: Path):
    write_daily_workbench(
        _packet(),
        output=tmp_path / "daily.xlsx",
        root=tmp_path,
    )
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    text = _all_text(workbook)

    assert "事实/行情 PIT" in text
    assert "规则时点 PIT=NOT CLAIMED" in text
    assert "future_rule_version_used=True" in text
    assert "所用规则（事后注册，非当时版本）" in text
    assert "真实 PIT 历史重放" not in text
    assert "当时规则" not in text


def test_rejects_non_no_order_or_truthy_execution_keys(tmp_path: Path):
    packet = _packet()
    packet["action"] = "paper_trade"
    with pytest.raises(ValueError, match="no_order"):
        build_daily_workbench(packet)

    packet = _packet()
    packet["m3"]["historical_replay"]["trade_approved"] = True
    with pytest.raises(ValueError, match="execution keys"):
        build_daily_workbench(packet)


def test_never_overwrites_existing_candidate(tmp_path: Path):
    output = tmp_path / "daily.xlsx"
    write_daily_workbench(_packet(), output=output, root=tmp_path)
    with pytest.raises(ValueError, match="already exists"):
        write_daily_workbench(_packet(), output=output, root=tmp_path)


def test_post_checkpoint_a_evidence_layers_are_fail_closed(tmp_path: Path):
    packet = _post_checkpoint_a_packet()
    write_daily_workbench(packet, output=tmp_path / "daily.xlsx", root=tmp_path)
    workbook = load_workbook(tmp_path / "daily.xlsx", data_only=True)
    text = _all_text(workbook)

    assert "M3 重建证据连续性" in text
    assert "RECONSTRUCTED_EVIDENCE_ONLY" in text
    assert "strict PIT=NOT_PROVEN" in text
    assert "actual_entry=False" in text
    assert "human_decision=None" in text
    assert "CNINFO 2026-06-01 至 2026-09-09" in text
    assert "16 条公告，9 条待人工复核，0 条来源缺失" in text
    assert "机器不代理重大性判断" in text
    assert "贵州茅台2026年半年度报告" in text
    assert "1225475868" in text
    for forbidden in ("建议买入", "建议加仓", "目标仓位", "下单"):
        assert forbidden not in text


def test_post_checkpoint_a_manifest_keeps_human_and_pit_boundaries(tmp_path: Path):
    output = tmp_path / "daily.xlsx"
    receipt = write_daily_workbench(
        _post_checkpoint_a_packet(),
        output=output,
        root=tmp_path,
    )
    manifest_path = output.with_name(
        output.stem + ".m7-daily-workbench-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["action"] == ACTION_NO_ORDER
    assert manifest["summary"]["m2_checkpoint_a_status"] == "HUMAN_PASS"
    assert manifest["summary"]["m3_reconstructed_continuity_status"] == (
        "RECONSTRUCTED_EVIDENCE_ONLY"
    )
    assert manifest["summary"]["m5_600519_pending_reviews"] == 9
    assert manifest["summary"]["m4_private_input_status"] == (
        "PENDING_USER_PRIVATE_INPUT"
    )
    assert manifest["summary"]["m6_operational_status"] == "NOT_STARTED"
    assert manifest["stage_statuses"]["m2"] == [
        "M2",
        "ENGINEERING_DONE",
        "DONE",
        "HUMAN_PASS",
    ]
    assert receipt["manifest_sha256"] == _digest(manifest_path)


def _require_post_checkpoint_a_real_artifacts() -> None:
    required = (
        "runtime/m3-reconstructed-continuity-20260924T083028Z/manifest.json",
        "runtime/m3-reconstructed-continuity-20260924T083028Z/trace.json",
        "runtime/m3-reconstructed-continuity-20260924T083028Z/input-payload.json",
        "runtime/m3-reconstructed-continuity-20260924T083028Z/A股价值投资_M3重建证据连续性候选_20260924.xlsx",
        "runtime/m5-600519-disclosure-queue-20260924/source/queue.json",
        "runtime/m5-600519-disclosure-queue-20260924/wps-receipt.json",
        "A股价值投资_M5真实披露待复核队列_600519_20260924.xlsx",
    )
    if any(not (ROOT / item).exists() for item in required):
        pytest.skip("Post-Checkpoint A runtime artifacts are not present in clean CI")


def _load_post_checkpoint_a_builder():
    spec = importlib.util.spec_from_file_location(
        "post_checkpoint_a_daily_workbench_builder",
        ROOT / "scripts" / "build_m7_daily_workbench_post_checkpoint_a.py",
    )
    assert spec is not None and spec.loader is not None
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


def test_real_post_checkpoint_a_builder_pins_new_evidence():
    _require_post_checkpoint_a_real_artifacts()
    builder = _load_post_checkpoint_a_builder()
    from datetime import datetime, timezone

    packet = builder.build_packet(
        datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    )

    reconstructed = packet["m3"]["reconstructed_continuity"]
    queue = packet["m5"]["disclosure_queue_600519"]
    assert packet["action"] == ACTION_NO_ORDER
    assert packet["m2"]["checkpoint_a_status"] == "HUMAN_PASS"
    assert reconstructed["conclusion_status"] == "RECONSTRUCTED_EVIDENCE_ONLY"
    assert reconstructed["strict_contemporaneous_rule_pit"] == "NOT_PROVEN"
    assert reconstructed["actual_entry_present"] is False
    assert queue["total_announcements"] == 16
    assert queue["pending_count"] == 9
    assert queue["source_unavailable"] == 0
    assert all(item["review_status"] == "PENDING_HUMAN_REVIEW" for item in queue["pending_items"])
    assert all(item["pdf_sha256"] for item in queue["pending_items"])


def test_frozen_m7_packet_does_not_follow_mutable_m6_latest_pointer():
    _require_post_checkpoint_a_real_artifacts()
    builder = _load_post_checkpoint_a_builder()
    from datetime import datetime, timezone

    packet = builder.build_packet(
        datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    )

    assert packet["m6"]["status"] == "PREFLIGHT_DONE"


def test_frozen_m7_packet_does_not_expose_an_m3_latest_pointer():
    _require_post_checkpoint_a_real_artifacts()
    builder = _load_post_checkpoint_a_builder()

    assert "M3_AUDIT_POINTER" not in builder.BASE_BUILDER
