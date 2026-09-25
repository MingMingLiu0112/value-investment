"""Read-only M7 daily workbench presentation.

This workbook consumes application read models already sealed in runtime JSON.
It does not import an IPS, portfolio, quote stream, valuation model, scheduler
or notification target, and it never computes an order or position size.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


SCHEMA_VERSION = "m7-daily-workbench-v1"
ACTION_NO_ORDER = "no_order"

VISIBLE_SHEETS = (
    "00_今日总览",
    "01_全市场与数据健康",
    "02_候选与重点关注",
    "03_决策复核",
    "04_当前持仓与仓位",
    "05_股息现金流",
    "06_事件与预警",
    "07_公司研究",
    "08_买卖逻辑与历史",
    "09_审计与证据",
)
HIDDEN_SHEETS = ("_模块状态矩阵", "_审计明细索引")

INK = "24312D"
WHITE = "FFFFFF"
GREEN = "18755D"
BLUE = "245D83"
AMBER = "FFF1D6"
GREY = "EFF3F1"
RED_FILL = "F8E7E6"
RED = "C0392B"
ORANGE_FILL = "FFF4E3"

_FORBIDDEN_EXECUTION_KEYS = {
    "trade_approved",
    "order_quantity",
    "order_price",
    "order_id",
    "target_weight",
    "position_size",
    "broker",
    "live_eligible",
}

CHANNEL_LABELS = {
    "quality": "质量",
    "dividend_cash_return": "股息/现金回报",
    "value": "价值",
    "cyclical": "周期",
}

VERIFICATION_LABELS = {
    "VERIFIED_FOR_DEEP_RESEARCH": "进入深研队列",
    "REJECTED_AFTER_VERIFICATION": "通道否决",
    "INSUFFICIENT_EVIDENCE": "证据不足",
    "UNSUPPORTED": "不支持",
}

VERIFICATION_FILLS = {
    "VERIFIED_FOR_DEEP_RESEARCH": "E4F3EE",
    "REJECTED_AFTER_VERIFICATION": RED_FILL,
    "INSUFFICIENT_EVIDENCE": AMBER,
    "UNSUPPORTED": "EEEEEE",
}

RESEARCH_REVIEW_LABELS = {
    "POST_EVENT_OPERATING_EVIDENCE_INSUFFICIENT": "提价后的销量、渠道与实际价格证据不足",
    "EVENT_DATE_DISCOUNT_INPUTS_NOT_REVIEWED": "事件日折现参数尚未复核",
    "DISTRIBUTION_RETENTION_NOT_REVIEWED": "分配、现金流与留存假设尚未复核",
    "TERMINAL_ASSUMPTIONS_NOT_REVIEWED": "长期 ROE 与终值增长假设尚未复核",
    "post_event_target_sku_volume": "目标产品提价后的销量或动销",
    "post_event_channel_mix": "提价后的渠道结构与经销状态",
    "post_event_realized_price_margin": "实际成交价、收入与利润率",
    "next_official_post_event_report": "事件后的下一份正式报告",
    "updated_parent_consolidated_cash_flow": "母公司及合并现金流更新",
    "distribution_remittance_capital_allocation": "分红上缴与资本配置证据",
    "dated_cny_discount_inputs": "同一时点的人民币折现输入",
    "forecast_horizon_roe_fade_terminal_evidence": "预测期 ROE 回落及终值依据",
}


def _style(
    cell,
    *,
    fill: str = WHITE,
    bold: bool = False,
    color: str = INK,
    size: int = 10,
    horizontal: str = "left",
) -> None:
    cell.font = Font(name="Microsoft YaHei", size=size, bold=bold, color=color)
    cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(
        vertical="top",
        horizontal=horizontal,
        wrap_text=True,
    )


def _title(ws: Worksheet, title: str, subtitle: str, columns: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    _style(ws.cell(1, 1, title), fill=GREEN, bold=True, color=WHITE, size=16)
    _style(ws.cell(2, 1, subtitle), fill=GREY, bold=True)
    ws.row_dimensions[1].height = 32
    ws.row_dimensions[2].height = 38


def _header(ws: Worksheet, row: int, columns: list[str]) -> int:
    for column, value in enumerate(columns, 1):
        _style(
            ws.cell(row, column, value),
            fill=BLUE,
            bold=True,
            color=WHITE,
        )
    return row + 1


def _widths(ws: Worksheet, widths: list[int]) -> None:
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _label_value(ws: Worksheet, row: int, label: str, value: str, columns: int) -> int:
    _style(ws.cell(row, 1, label), fill=GREY, bold=True)
    ws.merge_cells(
        start_row=row,
        start_column=2,
        end_row=row,
        end_column=columns,
    )
    _style(ws.cell(row, 2, value))
    ws.row_dimensions[row].height = max(18, value.count("\n") * 15 + 18)
    return row + 1


def _hyperlink(ws: Worksheet, row: int, column: int, target: str, value: str) -> None:
    cell = ws.cell(row, column, value)
    cell.hyperlink = f"#'{target}'!A1"
    cell.font = Font(
        name="Microsoft YaHei",
        size=10,
        color=BLUE,
        underline="single",
    )
    cell.alignment = Alignment(vertical="top", wrap_text=True)


def _required_mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    return value


def _required_list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _reject_execution_keys(value: object) -> None:
    if isinstance(value, dict):
        found = {
            key
            for key in _FORBIDDEN_EXECUTION_KEYS & set(value)
            if value[key] not in (False, None, 0, "", "no_order", "false", "0")
        }
        if found:
            raise ValueError(
                "M7 daily workbench packet contains execution keys: "
                + ", ".join(sorted(found))
            )
        for child in value.values():
            _reject_execution_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_execution_keys(child)


def _validate_packet(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    _reject_execution_keys(packet)
    if packet.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported M7 daily workbench packet schema")
    if packet.get("action") != ACTION_NO_ORDER:
        raise ValueError("M7 daily workbench packet must remain no_order")
    _required_text(packet.get("generated_at"), "generated_at")
    _required_text(packet.get("as_of"), "as_of")
    for key in ("m2", "m3", "m4", "m5", "m6", "audit"):
        _required_mapping(packet.get(key), key)

    m2 = _required_mapping(packet["m2"], "m2")
    if m2.get("status") == "DONE" and m2.get("checkpoint_a_status") != "HUMAN_PASS":
        raise ValueError("M2 DONE requires a bound Checkpoint A HUMAN_PASS status")
    _required_list(m2.get("rows"), "m2.rows")
    quality = _required_mapping(m2.get("quality"), "m2.quality")
    for key in (
        "lead_count",
        "verified_count",
        "rejected_count",
        "insufficient_count",
        "unsupported_count",
        "budget_excluded_count",
    ):
        if not isinstance(m2.get(key), int) or m2[key] < 0:
            raise ValueError(f"m2.{key} must be a non-negative integer")
    for key in (
        "universe_count",
        "evidence_count",
        "pass_count",
        "data_gap_count",
    ):
        if not isinstance(quality.get(key), int) or quality[key] < 0:
            raise ValueError(f"m2.quality.{key} must be a non-negative integer")
    if quality["evidence_count"] > quality["universe_count"]:
        raise ValueError("quality evidence count cannot exceed universe count")
    _required_text(m2.get("value_disclaimer"), "m2.value_disclaimer")

    m3 = _required_mapping(packet["m3"], "m3")
    _required_list(m3.get("negative_cards"), "m3.negative_cards")
    _required_mapping(m3.get("historical_replay"), "m3.historical_replay")
    _required_text(m3.get("positive_price_safety"), "m3.positive_price_safety")
    reconstructed = m3.get("reconstructed_continuity")
    if reconstructed is not None:
        reconstructed = _required_mapping(
            reconstructed, "m3.reconstructed_continuity"
        )
        _required_text(reconstructed.get("trace_id"), "m3.reconstructed_continuity.trace_id")
        _required_text(
            reconstructed.get("conclusion_status"),
            "m3.reconstructed_continuity.conclusion_status",
        )
        _required_text(
            reconstructed.get("strict_contemporaneous_rule_pit"),
            "m3.reconstructed_continuity.strict_contemporaneous_rule_pit",
        )
        _required_list(
            reconstructed.get("blockers"),
            "m3.reconstructed_continuity.blockers",
        )
        _required_list(
            reconstructed.get("comparisons"),
            "m3.reconstructed_continuity.comparisons",
        )
        if reconstructed.get("action") != ACTION_NO_ORDER:
            raise ValueError("m3.reconstructed_continuity.action must be no_order")

    m4 = _required_mapping(packet["m4"], "m4")
    _required_list(m4.get("required_inputs"), "m4.required_inputs")
    _required_text(m4.get("private_input_status"), "m4.private_input_status")
    if not isinstance(m4.get("new_capacity_available"), bool):
        raise ValueError("m4.new_capacity_available must be boolean")

    m5 = _required_mapping(packet["m5"], "m5")
    _required_list(m5.get("pending_items"), "m5.pending_items")
    for key in (
        "current_candidates",
        "carried_forward",
        "pending_human_review",
        "hash_conflicts",
        "superseded_pending",
    ):
        if not isinstance(m5.get(key), int) or m5[key] < 0:
            raise ValueError(f"m5.{key} must be a non-negative integer")

    disclosure_queue = m5.get("disclosure_queue_600519")
    if disclosure_queue is not None:
        disclosure_queue = _required_mapping(
            disclosure_queue, "m5.disclosure_queue_600519"
        )
        _required_list(
            disclosure_queue.get("pending_items"),
            "m5.disclosure_queue_600519.pending_items",
        )
        for key in ("total_announcements", "pending_count", "source_unavailable"):
            if (
                not isinstance(disclosure_queue.get(key), int)
                or disclosure_queue[key] < 0
            ):
                raise ValueError(
                    f"m5.disclosure_queue_600519.{key} must be a non-negative integer"
                )
        if disclosure_queue.get("action") != ACTION_NO_ORDER:
            raise ValueError("m5.disclosure_queue_600519.action must be no_order")
    actual = m5.get("actual_event_chain")
    if actual is not None:
        actual = _required_mapping(actual, "m5.actual_event_chain")
        rows = _required_list(actual.get("rows"), "m5.actual_event_chain.rows")
        if (actual.get("action") != ACTION_NO_ORDER or actual.get("reviewed_count") != len(rows)
            or actual.get("pending_human_review") != 0
            or any(row.get("action") != ACTION_NO_ORDER for row in rows)):
            raise ValueError("Actual event read model has inconsistent review or action state")
        review_fields = {"research_review_status", "research_review_sha256",
                         "research_review_blockers", "evidence_triggers", "next_trigger"}
        if review_fields & actual.keys():
            from .m5_scenario_research_review import BLOCKERS, TRIGGERS, TRIGGER_BLOCKERS
            triggers = _required_list(actual.get("evidence_triggers"), "m5.actual_event_chain.evidence_triggers")
            if (actual.get("research_review_status") != "HUMAN_REVIEWED_NEED_MORE_EVIDENCE"
                or not re.fullmatch(r"[0-9a-f]{64}", str(actual.get("research_review_sha256", "")))
                or actual.get("research_review_blockers") != list(BLOCKERS)
                or triggers != [{"kind": kind, "addresses": TRIGGER_BLOCKERS[kind],
                                  "on_evidence": "REOPEN_RESEARCH"} for kind in TRIGGERS]
                or actual.get("next_trigger") != "waiting_for_post_event_evidence"
                or not rows or any(row.get("event_id") and
                    (row.get("research_review_status") != "HUMAN_REVIEWED_NEED_MORE_EVIDENCE"
                     or row.get("recalculation_status") != "STILL_NOT_READY"
                     or row.get("new_valuation_result") is not None)
                    for row in rows)):
                raise ValueError("Actual event research review must remain blocked and evidence-bound")
        if any(row.get("recalculation_status") == "RECALCULATED" for row in rows):
            if (not re.fullmatch(r"[0-9a-f]{64}", str(actual.get("event_refresh_review_sha256", "")))
                or any(row.get("recalculation_status") == "RECALCULATED"
                       and not row.get("event_id") for row in rows)
                or any(row.get("recalculation_status") != "RECALCULATED"
                       or row.get("blockers")
                       or row.get("requires_human_decision_review") is not True
                       or not isinstance(row.get("new_valuation_result"), Mapping)
                       or row["new_valuation_result"].get("event_validity_status") != "RECONCILED"
                       for row in rows if row.get("event_id"))):
                raise ValueError("Recalculated event view requires reconciled review evidence")

    m6 = _required_mapping(packet["m6"], "m6")
    _required_list(m6.get("blockers"), "m6.blockers")
    audit = _required_mapping(packet["audit"], "audit")
    _required_list(audit.get("artifacts"), "audit.artifacts")
    if audit.get("action") != ACTION_NO_ORDER:
        raise ValueError("audit.action must be no_order")
    return packet


def _overview(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[0])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A5"
    ws.sheet_view.zoomScale = 100
    _widths(ws, [30, 100])
    _title(
        ws,
        "A股价值投资 Agent 每日工作台",
        "只读展示候选。所有 Review 均需人工决策，本表不生成订单、仓位或交易结论。",
        2,
    )
    row = 4
    row = _label_value(ws, row, "数据时点", str(packet["as_of"]), 2)
    row = _label_value(ws, row, "生成时间", str(packet["generated_at"]), 2)
    m2 = packet["m2"]
    verified = m2.get("verified_symbols") or []
    verification_summary = (
        f"M2 Verification v2 已对 18 条预注册 LEAD 完成真实二阶段 resolution："
        f"{m2['verified_count']} 条进入深研、{m2['rejected_count']} 条否决、"
        f"{m2['insufficient_count']} 条证据不足。"
    )
    row = _label_value(
        ws,
        row,
        "今日新发现",
        verification_summary,
        2,
    )
    row = _label_value(
        ws,
        row,
        "进入重点关注",
        "、".join(str(item) for item in verified)
        if verified
        else "无新增重点关注",
        2,
    )
    row = _label_value(ws, row, "等待价格", "当前 0 条。M3 三张现有卡均为研究不足，不是等待更低价格。", 2)
    row = _label_value(
        ws,
        row,
        "需要人工正向复核",
        "0 条。当前没有 BUY / ADD 复核可进入；深研队列只代表继续研究。",
        2,
    )
    row = _label_value(
        ws,
        row,
        "持仓论点变化",
        "无法计算。真实 IPS / 持仓尚未由用户提供，系统不会用模拟组合推断。",
        2,
    )
    row = _label_value(ws, row, "需要减仓 / 退出复核", "0 条。", 2)
    m5 = packet["m5"]
    row = _label_value(
        ws,
        row,
        "分红 / 事件风险",
        f"新增待人工复核事件 {m5['pending_human_review']} 条；"
        f"Hash 冲突 {m5['hash_conflicts']} 条。",
        2,
    )
    row = _label_value(ws, row, "数据源失效", "未发现。质量通道仍为 COVERAGE_LIMITED，不是数据源故障。", 2)
    row += 1
    _style(ws.cell(row, 1, "结论"), fill=ORANGE_FILL, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=2)
    _style(
        ws.cell(
            row,
            2,
            f"{m2['verified_count']} 个深研候选不等于 "
            f"{m2['verified_count']} 个买入目标；当前无任何可用订单。",
        ),
        fill=ORANGE_FILL,
        bold=True,
    )
    row += 2
    _style(ws.cell(row, 1, "快速入口"), fill=BLUE, bold=True, color=WHITE)
    _style(ws.cell(row, 2, "点击进入对应主页面"), fill=GREY, bold=True)
    row += 1
    for name in VISIBLE_SHEETS[1:]:
        _hyperlink(ws, row, 2, name, name)
        row += 1

    reconstructed = packet["m3"].get("reconstructed_continuity")
    disclosure_queue = packet["m5"].get("disclosure_queue_600519")
    if reconstructed or disclosure_queue:
        row += 1
        _style(ws.cell(row, 1, "新增证据"), fill=BLUE, bold=True, color=WHITE)
        _style(ws.cell(row, 2, "以下内容只用于证据连续性，不签发任何投资结论。"), fill=GREY, bold=True)
        row += 1
    if reconstructed:
        row = _label_value(
            ws,
            row,
            "M3 重建证据连续性",
            (
                f"{reconstructed.get('symbol')} / {reconstructed.get('baseline_date')}："
                f"{reconstructed.get('conclusion_status')}；"
                f"strict PIT={reconstructed.get('strict_contemporaneous_rule_pit')}；"
                f"actual_entry={reconstructed.get('actual_entry_present')}；"
                f"human_decision={reconstructed.get('human_decision')}；"
                f"action={reconstructed.get('action')}。"
            ),
            2,
        )
    actual = packet["m5"].get("actual_event_chain")
    if actual:
        row = _label_value(
            ws, row, "600519 真实公告进度",
            f"{actual['reviewed_count']} 条已复核，{actual['pending_human_review']} 条待复核；"
            f"{actual['verified_fact_count']} 项半年报事实已按 PDF 核对。"
            "需重算事件仍等待完整估值输入及人工决策复核。", 2,
        )
    elif disclosure_queue:
        row = _label_value(
            ws,
            row,
            "M5 600519 真实披露队列",
            (
                f"CNINFO {disclosure_queue.get('scan_from')} 至 "
                f"{disclosure_queue.get('scan_to')}："
                f"{disclosure_queue.get('total_announcements')} 条公告，"
                f"{disclosure_queue.get('pending_count')} 条待人工复核，"
                f"{disclosure_queue.get('source_unavailable')} 条来源缺失；"
                f"coverage={disclosure_queue.get('coverage_status')}；"
                "机器不代理重大性判断。"
            ),
            2,
        )


def _market_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[1])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    _widths(ws, [24, 34, 20, 66])
    _title(
        ws,
        "全市场与数据健康",
        "官方 Universe 与四通道覆盖来自 M2 封存收据；Quality 覆盖不足不得解释成 A 股没有质量公司。",
        4,
    )
    row = _header(ws, 4, ["通道", "PASS / 展示预算", "预算外", "当前可读解释"])
    m2 = packet["m2"]
    channel_counts = m2.get("channel_counts") or {}
    budget_by_channel = m2.get("budget_by_channel") or {}
    maturity = {
        "quality": "方法方向可接受；质量财务证据覆盖不足，仅作线索生成器。",
        "dividend_cash_return": "首层接近已宣告股息率与市值，只称股息线索生成器；派息历史/覆盖/负债/周期未验证。",
        "value": "首层为 PE/PB/隐含 ROE，只称估值线索生成器；FCF/EV/EBIT/正常化盈利未验证。",
        "cyclical": "首层为周期行业/PE/PB/市值，只称周期线索生成器；当前/正常化盈利与周期位置未形成。",
    }
    for channel in ("quality", "dividend_cash_return", "value", "cyclical"):
        pass_count = channel_counts.get(channel, 0)
        budget = budget_by_channel.get(channel, 0)
        values = [
            CHANNEL_LABELS.get(channel, channel),
            str(pass_count),
            str(budget),
            maturity.get(channel, ""),
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value))
        row += 1

    row += 1
    _style(ws.cell(row, 1, "Universe"), fill=GREY, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    quality = m2["quality"]
    _style(
        ws.cell(row, 2, f"{quality['universe_count']} 家官方证券"),
    )
    row += 1
    _style(ws.cell(row, 1, "Quality 覆盖"), fill=GREY, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    _style(
        ws.cell(row, 2, f"{quality['evidence_count']} / {quality['universe_count']} usable quality evidence"),
    )
    row += 1
    _style(ws.cell(row, 1, "覆盖状态"), fill=AMBER, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    _style(ws.cell(row, 2, quality.get("coverage_status") or "COVERAGE_LIMITED"), fill=AMBER, bold=True)
    row += 1
    _style(ws.cell(row, 1, "质量覆盖解释"), fill=AMBER, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    _style(
        ws.cell(
            row,
            2,
            f"当前 {quality['data_gap_count']} 家缺少足够质量财务证据，"
            "不能把 0 个 Quality 候选解释成市场没有高质量公司。",
        ),
        fill=AMBER,
    )
    row += 2
    _style(ws.cell(row, 1, "Value 用户文案"), fill=RED_FILL, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    _style(ws.cell(row, 2, m2["value_disclaimer"]), fill=RED_FILL, bold=True)
    row += 2
    _style(ws.cell(row, 1, "预算外通过者"), fill=GREY, bold=True)
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    _style(
        ws.cell(
            row,
            2,
            f"{m2['budget_excluded_count']} 个预算外对象仍保留 trigger metrics、"
            "trigger reasons、channel、policy version、evidence refs 和 raw rank。",
        ),
    )


def _candidate_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[2])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A8"
    _widths(ws, [12, 18, 24, 22, 86, 12])
    _title(
        ws,
        "候选与重点关注",
        "LEAD -> 二阶段 resolution。进入深研队列只表示获得继续研究资格，不代表估值、便宜或买入。",
        6,
    )
    m2 = packet["m2"]
    summary = (
        f"LEAD {m2['lead_count']} | VERIFIED {m2['verified_count']} | "
        f"REJECTED {m2['rejected_count']} | "
        f"INSUFFICIENT {m2['insufficient_count']} | "
        f"UNSUPPORTED {m2['unsupported_count']}"
    )
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=6)
    _style(ws.cell(4, 1, summary), fill=ORANGE_FILL, bold=True)
    channel_resolutions = m2.get("verification_channel_counts") or {}
    resolution_parts = []
    for channel in ("quality", "dividend_cash_return", "value", "cyclical"):
        counts = channel_resolutions.get(channel) or {}
        resolution_parts.append(
            f"{CHANNEL_LABELS.get(channel, channel)} "
            f"验证 {counts.get('verified', 0)} / 否决 {counts.get('rejected', 0)} / "
            f"不足 {counts.get('insufficient', 0)}"
        )
    ws.merge_cells(start_row=5, start_column=1, end_row=5, end_column=6)
    _style(ws.cell(5, 1, " | ".join(resolution_parts)), fill=GREY, bold=True)
    row = _header(ws, 7, ["证券代码", "公司", "通道", "二阶段结论", "原因", "证据数"])
    for item in m2["rows"]:
        status = str(item.get("status") or "")
        fill = VERIFICATION_FILLS.get(status, WHITE)
        values = [
            str(item.get("symbol") or ""),
            str(item.get("name") or ""),
            CHANNEL_LABELS.get(str(item.get("channel") or ""), str(item.get("channel") or "")),
            VERIFICATION_LABELS.get(status, status),
            str(item.get("reason") or ""),
            str(item.get("evidence_count") or 0),
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value), fill=fill)
        ws.row_dimensions[row].height = max(26, len(values[4]) // 22 * 15 + 18)
        row += 1


def _decision_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[3])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A7"
    _widths(ws, [12, 18, 24, 18, 86])
    _title(
        ws,
        "决策复核",
        "任何 BUY / ADD 都必须经过正向价格吸引力门；当前三张卡均为研究不足，不产生新增容量。",
        5,
    )
    m3 = packet["m3"]
    row = _header(ws, 4, ["证券代码", "公司", "当前状态", "原因类型", "主要阻断"])
    for card in m3["negative_cards"]:
        blockers = card.get("blockers") or []
        values = [
            str(card.get("symbol") or ""),
            str(card.get("name") or ""),
            str(card.get("status") or ""),
            str(card.get("reason_kind") or ""),
            "\n".join(str(item) for item in blockers[:8]),
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value), fill=AMBER if column == 3 else WHITE)
        ws.row_dimensions[row].height = max(24, len(blockers[:8]) * 15 + 18)
        row += 1
    row += 1
    row = _label_value(ws, row, "正向价格安全", m3["positive_price_safety"], 5)
    row = _label_value(
        ws,
        row,
        "Checkpoint B",
        str(m3.get("checkpoint_b_status") or "NOT_APPROVED_YET"),
        5,
    )
    replay = m3["historical_replay"]
    row = _label_value(
        ws,
        row,
        "历史研究重放（事实/行情 PIT，规则非当时版本）",
        (
            f"{replay.get('symbol')} / {replay.get('replay_date')} / "
            f"最终状态 {replay.get('final_decision')}；valuation_approved="
            f"{replay.get('valuation_approved')}；trade_approved={replay.get('trade_approved')}。"
            f"事实/行情 PIT=YES；规则时点 PIT=NOT CLAIMED；"
            f"future_facts_used={replay.get('future_facts_used')}；"
            f"future_rule_version_used={replay.get('future_rule_version_used')}。"
        ),
        5,
    )
    reconstructed = m3.get("reconstructed_continuity")
    if reconstructed:
        row = _label_value(
            ws,
            row,
            "600519 官方披露连续性（重建）",
            (
                f"{reconstructed.get('trace_id')}；"
                f"结论 {reconstructed.get('conclusion_status')}；"
                f"同期规则 PIT={reconstructed.get('strict_contemporaneous_rule_pit')}；"
                f"future_rule_version_used="
                f"{reconstructed.get('future_rule_version_used')}；"
                f"实际 Entry={reconstructed.get('actual_entry_present')}；"
                f"人工决策={reconstructed.get('human_decision')}。"
            ),
            5,
        )
        row = _label_value(
            ws,
            row,
            "重建证据阻断",
            "\n".join(str(item) for item in reconstructed.get("blockers") or []),
            5,
        )


def _position_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[4])
    ws.sheet_view.showGridLines = False
    _widths(ws, [32, 104])
    _title(
        ws,
        "当前持仓与仓位",
        "没有真实 IPS / 持仓时 fail-closed。系统不猜测私人上限，也不显示模拟组合为个人仓位。",
        2,
    )
    m4 = packet["m4"]
    row = 4
    row = _label_value(ws, row, "私人输入状态", m4["private_input_status"], 2)
    row = _label_value(
        ws,
        row,
        "新增容量",
        "0。只有有效的 MANUAL_BUY_REVIEW / MANUAL_ADD_REVIEW 决策制品才允许产生容量。",
        2,
    )
    row = _label_value(ws, row, "M3 决策绑定", str(m4.get("decision_binding_status") or ""), 2)
    row += 1
    _style(ws.cell(row, 1, "仍需用户提供"), fill=BLUE, bold=True, color=WHITE)
    _style(ws.cell(row, 2, "以下项目不得由 Codex 猜测或代填"), fill=GREY, bold=True)
    row += 1
    for item in m4["required_inputs"]:
        _style(ws.cell(row, 1, "-"), fill=GREY)
        _style(ws.cell(row, 2, str(item)))
        row += 1


def _dividend_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[5])
    ws.sheet_view.showGridLines = False
    _widths(ws, [32, 104])
    _title(
        ws,
        "股息现金流",
        "当前没有用户持仓，不能计算当前、Forward 或 Normalized 股息收入。模拟工程不作为现金流事实。",
        2,
    )
    row = 4
    row = _label_value(ws, row, "可用收入口径", "无。真实持仓缺失。", 2)
    row = _label_value(ws, row, "可持续性结论", "无。普通/特别分红、CFO/FCF 覆盖和周期敏感性尚未针对真实持仓验证。", 2)
    row = _label_value(ws, row, "现有模拟状态", str(packet["m4"].get("simulated_engineering_status") or ""), 2)
    row = _label_value(
        ws,
        row,
        "边界",
        "高股息率不等于买入信号；分红下降也不等于自动卖出。",
        2,
    )


def _event_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[6])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A8"
    _widths(ws, [12, 18, 46, 68, 64])
    _title(
        ws,
        "事件与预警",
        "旧人工结论按 symbol + announcement_id + PDF SHA-256 复用；只把真正的新增或变更留给用户。",
        5,
    )
    m5 = packet["m5"]
    summary = (
        f"当前候选 {m5['current_candidates']} | 复用旧结论 {m5['carried_forward']} | "
        f"新增待复核 {m5['pending_human_review']} | Hash 冲突 {m5['hash_conflicts']} | "
        f"被取代待处理 {m5['superseded_pending']}"
    )
    ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=5)
    _style(ws.cell(4, 1, summary), fill=ORANGE_FILL, bold=True)
    row = _header(ws, 6, ["证券代码", "公告ID", "标题", "来源URL", "PDF SHA-256"])
    for item in m5["pending_items"]:
        values = [
            str(item.get("symbol") or ""),
            str(item.get("announcement_id") or ""),
            str(item.get("title") or ""),
            str(item.get("source_url") or ""),
            str(item.get("current_source_sha256") or ""),
        ]
        for column, value in enumerate(values, 1):
            cell = ws.cell(row, column, value)
            _style(cell, fill=AMBER)
            if column == 4 and str(value).startswith(("http://", "https://")):
                cell.hyperlink = str(value)
                cell.font = Font(
                    name="Microsoft YaHei",
                    size=10,
                    color=BLUE,
                    underline="single",
                )
        ws.row_dimensions[row].height = max(24, len(values[2]) // 23 * 15 + 18)
        row += 1
    row += 1
    row = _label_value(ws, row, "持续监控", str(m5.get("continuous_ops_status") or ""), 5)

    actual = m5.get("actual_event_chain")
    disclosure_queue = m5.get("disclosure_queue_600519")
    if actual:
        row += 1
        row = _label_value(
            ws, row, "600519 实际事件闭环",
            f"人工已复核 {actual['reviewed_count']} 条；待复核 {actual['pending_human_review']} 条；"
            f"已核半年报事实 {actual['verified_fact_count']} 项；"
            "新估值未就绪时保持原结论失效。", 5,
        )
        if actual.get("research_review_status"):
            row = _label_value(
                ws, row, "情景研究复核",
                "NEED_MORE_EVIDENCE；A-E 假设均未批准；无新估值、无交易指令。"
                f"\n复核 SHA-256：{actual['research_review_sha256']}", 5,
            )
        row = _header(ws, row, ["公告ID", "人工结论", "标题", "影响依赖 / 重算状态", "证据与事件"])
        for item in actual["rows"]:
            dependencies = ", ".join(item["affected_dependencies"]) or "无重算依赖"
            detail = f"影响：{dependencies}\n状态：{item['recalculation_status']}"
            if item["blockers"]:
                detail += "\n阻断：" + ", ".join(item["blockers"])
            detail += ("\n人工决策复核：需要" if item["requires_human_decision_review"]
                       else "\n人工决策复核：不适用")
            refreshed = item["new_valuation_result"]
            if refreshed:
                detail += (f"\n新估值：{refreshed['valuation_date']} / {refreshed['model_version']}"
                           f"\n产物 ID：{refreshed['artifact_id']}"
                           f"\n事件有效性：{refreshed['event_validity_status']}")
            else:
                detail += "\n新估值：未生成"
            evidence = f"PDF SHA-256: {item['pdf_sha256']}"
            if item["event_id"]:
                evidence += f"\nEvent ID: {item['event_id']}"
            if refreshed:
                evidence += f"\nValuation SHA-256: {refreshed['payload_sha256']}"
            values = [item["announcement_id"], item["materiality"], item["title"], detail, evidence]
            for column, value in enumerate(values, 1):
                _style(ws.cell(row, column, value), fill=AMBER)
            ws.row_dimensions[row].height = max(60, detail.count("\n") * 15 + 25)
            row += 1
        if actual.get("research_review_status"):
            row += 1
            row = _header(ws, row, ["类别", "状态", "核对内容", "审计键 / 对应阻断", "到达后处理"])
            for blocker in actual["research_review_blockers"]:
                values = ["研究阻断", "未通过", RESEARCH_REVIEW_LABELS[blocker], blocker,
                          "保持 STILL_NOT_READY；不得刷新估值"]
                for column, value in enumerate(values, 1):
                    _style(ws.cell(row, column, value), fill=RED_FILL)
                ws.row_dimensions[row].height = 34
                row += 1
            for trigger in actual["evidence_triggers"]:
                values = ["证据触发", "待证据", RESEARCH_REVIEW_LABELS[trigger["kind"]],
                          f"{trigger['kind']}\n对应：{trigger['addresses']}",
                          "仅重新开启研究；不自动批准参数或重算"]
                for column, value in enumerate(values, 1):
                    _style(ws.cell(row, column, value), fill=AMBER)
                ws.row_dimensions[row].height = 46
                row += 1
    elif disclosure_queue:
        row += 1
        row = _label_value(
            ws,
            row,
            "600519 新增真实披露待复核队列",
            (
                f"{disclosure_queue.get('queue_id')}；"
                f"{disclosure_queue.get('total_announcements')} 条公告，"
                f"{disclosure_queue.get('pending_count')} 条待人工复核，"
                f"{disclosure_queue.get('source_unavailable')} 条来源缺失；"
                f"coverage={disclosure_queue.get('coverage_status')}。"
                "标题规则只登记候选，不判定重大性。"
            ),
            5,
        )
        row = _header(ws, row, ["证券代码", "公告ID", "标题", "规则类别", "PDF SHA-256"])
        for item in disclosure_queue.get("pending_items") or []:
            values = [
                str(disclosure_queue.get("symbol") or ""),
                str(item.get("announcement_id") or ""),
                str(item.get("title") or ""),
                str(item.get("rule_kind") or ""),
                str(item.get("pdf_sha256") or ""),
            ]
            for column, value in enumerate(values, 1):
                _style(ws.cell(row, column, value), fill=AMBER)
            ws.row_dimensions[row].height = max(
                24, len(values[2]) // 23 * 15 + 18
            )
            row += 1


def _research_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[7])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A7"
    _widths(ws, [12, 18, 24, 22, 72])
    _title(
        ws,
        "公司研究",
        "VERIFIED_FOR_DEEP_RESEARCH 是进入研究队列，不是研究已完成；深研仍需真实财务证据、反证和事件复核。",
        5,
    )
    m2 = packet["m2"]
    row = _header(ws, 4, ["证券代码", "公司", "通道", "状态", "研究结论"])
    for item in m2["rows"]:
        status = str(item.get("status") or "")
        if status != "VERIFIED_FOR_DEEP_RESEARCH":
            continue
        values = [
            str(item.get("symbol") or ""),
            str(item.get("name") or ""),
            CHANNEL_LABELS.get(str(item.get("channel") or ""), str(item.get("channel") or "")),
            VERIFICATION_LABELS.get(status, status),
            str(item.get("reason") or ""),
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value), fill="E4F3EE")
        ws.row_dimensions[row].height = max(26, len(values[4]) // 25 * 15 + 18)
        row += 1
    row += 1
    replay = packet["m3"]["historical_replay"]
    row = _label_value(
        ws,
        row,
        "历史研究重放样例（事实/行情 PIT）",
        (
            f"{replay.get('symbol')} / {replay.get('replay_date')}，"
            f"采用当时年报 {replay.get('then_known_facts', {}).get('source_id')}、"
            f"当时收盘价 {replay.get('then_known_quote', {}).get('close_cny')}。"
        ),
        5,
    )
    row = _label_value(
        ws,
        row,
        "所用规则（事后注册，非当时版本）",
        str(replay.get("rule", {}).get("rule_version") or ""),
        5,
    )
    row = _label_value(
        ws,
        row,
        "规则时点声明",
        (
            f"future_facts_used={replay.get('future_facts_used')}；"
            f"future_rule_version_used={replay.get('future_rule_version_used')}；"
            "不得称为完整当时点 PIT。"
        ),
        5,
    )
    row = _label_value(
        ws,
        row,
        "最终状态",
        str(replay.get("final_decision") or ""),
        5,
    )
    row = _label_value(
        ws,
        row,
        "阻断",
        "\n".join(str(item) for item in replay.get("blockers") or []),
        5,
    )


def _history_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[8])
    ws.sheet_view.showGridLines = False
    _widths(ws, [32, 104])
    _title(
        ws,
        "买卖逻辑与历史",
        "没有真实用户 Entry，不伪造历史决策。当前模拟历史链只用于验证展示结构。",
        2,
    )
    row = 4
    row = _label_value(ws, row, "真实 Entry / Journal", "未记录。等待用户确认原始买入理由后才可建立。", 2)
    row = _label_value(ws, row, "模拟历史", str(packet["m3"].get("simulated_history_status") or ""), 2)
    row = _label_value(
        ws,
        row,
        "历史重放",
        (
            f"{packet['m3']['historical_replay'].get('symbol')} / "
            f"{packet['m3']['historical_replay'].get('final_decision')}，"
            "事实与行情采用当日可知版本；所用 Median-PE 规则是 2026-09-12 注册的"
            "事后研究扩展，因此不声称规则当时点 PIT，也不是策略收益。"
        ),
        2,
    )
    boundaries = [
        "Research Attractive != Buy Signal",
        "High Dividend Yield != Buy Signal",
        "Price Drop != Automatic Add",
        "Price Rise != Automatic Sell",
        "Margin of Safety != Position Size",
    ]
    row += 1
    _style(ws.cell(row, 1, "永久边界"), fill=BLUE, bold=True, color=WHITE)
    _style(ws.cell(row, 2, "所有规则均保持 action=no_order"), fill=GREY, bold=True)
    row += 1
    for item in boundaries:
        _style(ws.cell(row, 1, "边界"), fill=GREY)
        _style(ws.cell(row, 2, item))
        row += 1

    reconstructed = packet["m3"].get("reconstructed_continuity")
    if reconstructed:
        row = _label_value(
            ws,
            row,
            "600519 重建证据连续性",
            (
                f"{reconstructed.get('trace_id')} / "
                f"{reconstructed.get('conclusion_status')} / "
                f"strict PIT={reconstructed.get('strict_contemporaneous_rule_pit')} / "
                f"actual_entry={reconstructed.get('actual_entry_present')} / "
                f"human_decision={reconstructed.get('human_decision')} / "
                f"action={reconstructed.get('action')}。"
            ),
            2,
        )


def _audit_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(VISIBLE_SHEETS[9])
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A7"
    _widths(ws, [34, 74, 64, 12])
    _title(
        ws,
        "审计与证据",
        "展示层只消费已封存 read model；每个关键输入保留路径与 SHA-256，可回到原始文件。",
        4,
    )
    row = _header(ws, 4, ["项目", "路径", "SHA-256", "动作"])
    audit = packet["audit"]
    for item in audit["artifacts"]:
        values = [
            str(item.get("label") or ""),
            str(item.get("path") or ""),
            str(item.get("sha256") or ""),
            str(item.get("action") or ACTION_NO_ORDER),
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value))
        row += 1
    row += 1
    row = _label_value(ws, row, "90 页审计工作台", str(audit.get("audit_workbook") or ""), 4)
    row = _label_value(ws, row, "90 页工作台 Hash", str(audit.get("audit_workbook_sha256") or ""), 4)
    row = _label_value(ws, row, "Canonical Excel", str(audit.get("canonical_workbook") or ""), 4)
    row = _label_value(ws, row, "生产动作", str(audit.get("production_actions") or "NONE"), 4)


def _status_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(HIDDEN_SHEETS[0])
    ws.sheet_state = "hidden"
    _widths(ws, [16, 36, 36, 36])
    _title(ws, "模块状态矩阵", "工程、研究/产品、人工/运营三个维度不得折叠成一个 READY。", 4)
    row = _header(ws, 4, ["阶段", "工程", "研究/产品", "人工/运营"])
    statuses = packet.get("stage_statuses") or {}
    labels = {
        "m1": ("M1", "DONE", "DONE as Research Workbench", "已完成人工 G3 初审"),
        "m2": ("M2", "ENGINEERING_DONE", "DONE", "HUMAN_PASS"),
        "m3": ("M3", "ENGINEERING_PARTIAL_PLUS", "PARTIAL", "PENDING_HUMAN_REVIEW"),
        "m4": ("M4", "ENGINEERING_DONE_SIMULATED", "PARTIAL", "PENDING_PRIVATE_INPUT"),
        "m5": ("M5", "ENGINEERING_DONE_OFFLINE", "PARTIAL", "PENDING_RECONCILIATION / OPERATIONS"),
        "m6": ("M6", "PREFLIGHT_DONE", "NOT_STARTED operationally", "PENDING_AUTHORIZATION / SHADOW"),
        "m7": ("M7", "DISPLAY_ENGINEERING_DONE", "PARTIAL", "PENDING_USER_ACCEPTANCE"),
    }
    for key, defaults in labels.items():
        values = list(statuses.get(key) or defaults)
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, str(value)))
        row += 1


def _detail_index_sheet(packet: Mapping[str, Any], wb: Workbook) -> None:
    ws = wb.create_sheet(HIDDEN_SHEETS[1])
    ws.sheet_state = "hidden"
    _widths(ws, [24, 110])
    _title(
        ws,
        "审计明细索引",
        "90 页统一工作台保留为审计/明细；本表只保留 9 个日常入口，技术页不要求每日逐页阅读。",
        2,
    )
    row = 4
    audit = packet["audit"]
    row = _label_value(ws, row, "90 页文件", str(audit.get("audit_workbook") or ""), 2)
    row = _label_value(ws, row, "90 页 Hash", str(audit.get("audit_workbook_sha256") or ""), 2)
    row = _label_value(ws, row, "Canonical 文件", str(audit.get("canonical_workbook") or ""), 2)
    row = _label_value(
        ws,
        row,
        "证据定位",
        "关键结论可从 09_审计与证据 的路径和 Hash 回到运行时 JSON 与原始 PDF。",
        2,
    )


def build_daily_workbench(packet: Mapping[str, Any]) -> Workbook:
    packet = _validate_packet(packet)
    wb = Workbook()
    wb.remove(wb.active)
    _overview(packet, wb)
    _market_sheet(packet, wb)
    _candidate_sheet(packet, wb)
    _decision_sheet(packet, wb)
    _position_sheet(packet, wb)
    _dividend_sheet(packet, wb)
    _event_sheet(packet, wb)
    _research_sheet(packet, wb)
    _history_sheet(packet, wb)
    _audit_sheet(packet, wb)
    _status_sheet(packet, wb)
    _detail_index_sheet(packet, wb)
    wb.active = 0
    return wb


def write_daily_workbench(
    packet: Mapping[str, Any],
    *,
    output: Path,
    root: Path,
) -> dict[str, Any]:
    output = output.resolve()
    root = root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("M7 daily workbench output escapes project root")
    if output.exists():
        raise ValueError(f"M7 daily workbench already exists: {output}")
    packet = _validate_packet(packet)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_daily_workbench(packet)
    workbook.save(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    visible_sheet_count = sum(
        name in VISIBLE_SHEETS for name in workbook.sheetnames
    )
    hidden_sheet_count = sum(
        name in HIDDEN_SHEETS for name in workbook.sheetnames
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": packet["generated_at"],
        "as_of": packet["as_of"],
        "action": ACTION_NO_ORDER,
        "workbook_path": str(output.relative_to(root)),
        "workbook_sha256": digest,
        "visible_sheet_count": visible_sheet_count,
        "hidden_sheet_count": hidden_sheet_count,
        "visible_sheets": list(VISIBLE_SHEETS),
        "stage_statuses": dict(packet.get("stage_statuses") or {}),
        "summary": {
            "m2_verified_for_deep_research": packet["m2"]["verified_count"],
            "m2_rejected_after_verification": packet["m2"]["rejected_count"],
            "m2_checkpoint_a_status": str(
                packet["m2"].get("checkpoint_a_status") or "NOT_RECORDED"
            ),
            "m5_new_pending_reviews": packet["m5"]["pending_human_review"],
            "m5_600519_pending_reviews": int(
                (packet["m5"].get("disclosure_queue_600519") or {}).get(
                    "pending_count", 0
                )
            ),
            "m3_reconstructed_continuity_status": str(
                (packet["m3"].get("reconstructed_continuity") or {}).get(
                    "conclusion_status", "ABSENT"
                )
            ),
            "m4_private_input_status": packet["m4"]["private_input_status"],
            "m6_operational_status": packet["m6"]["operational_status"],
        },
    }
    manifest_path = output.with_name(
        output.stem + ".m7-daily-workbench-manifest.json"
    )
    if manifest_path.exists():
        raise ValueError(f"M7 daily workbench manifest already exists: {manifest_path}")
    manifest_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    receipt["manifest_path"] = str(manifest_path.relative_to(root))
    receipt["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return receipt
