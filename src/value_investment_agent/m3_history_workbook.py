"""Public M3 history-chain Excel candidate.

The workbook is presentation-only and deliberately refuses non-simulated
chains. It never mutates the WPS production workbook and never shows target
weights, position sizes or order instructions.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .investment_decision import (
    ACTION_NO_ORDER,
    CONSISTENCY_BROKEN,
    CONSISTENCY_FULFILLED,
    CONSISTENCY_WEAKENED,
    COMPARISON_BROKEN,
    COMPARISON_FULFILLED,
    COMPARISON_NEGATIVE,
    ENTRY_TYPE_RECONSTRUCTED,
    ENTRY_TYPE_SIMULATED,
    HUMAN_CONFIRM_ADD,
    HUMAN_CONFIRM_BUY,
    HUMAN_CONFIRM_EXIT,
    HUMAN_CONFIRM_HOLD,
    HUMAN_CONFIRM_REDUCE,
    HUMAN_REJECT,
    HUMAN_DEFER,
    HUMAN_CANCEL,
)
from .m3_history_read_model import (
    ConsistencyReviewCard,
    DecisionHistoryChain,
    DecisionHistoryCollection,
    DecisionJournalLine,
    EntryThesisCard,
    PUBLIC_NAMESPACE,
)


OVERVIEW_SHEET = "00_历史链"
ENTRY_SHEET = "01_原Entry"
JOURNAL_SHEET = "02_决策日志"
CONSISTENCY_SHEET = "03_一致性复核"
SOURCE_SHEET = "04_来源哈希"

INK = "24312D"
GREEN = "18755D"
BLUE = "245D83"
AMBER = "FFF1D6"
GREY = "EFF3F1"
RED = "C0392B"

_ENTRY_LABELS = {
    "actual": "真实",
    ENTRY_TYPE_SIMULATED: "模拟",
    ENTRY_TYPE_RECONSTRUCTED: "事后重建",
}
_HUMAN_LABELS = {
    HUMAN_CONFIRM_BUY: "确认买入",
    HUMAN_CONFIRM_ADD: "确认加仓",
    HUMAN_CONFIRM_HOLD: "确认持有",
    HUMAN_CONFIRM_REDUCE: "确认减仓",
    HUMAN_CONFIRM_EXIT: "确认退出",
    HUMAN_REJECT: "拒绝",
    HUMAN_DEFER: "暂缓",
    HUMAN_CANCEL: "取消",
}
_IMPACT_LABELS = {
    "NEUTRAL": "未变化",
    "POSITIVE": "加强",
    COMPARISON_NEGATIVE: "削弱",
    COMPARISON_FULFILLED: "已兑现",
    COMPARISON_BROKEN: "已破坏",
}
_CONSISTENCY_LABELS = {
    "CONSISTENT": "一致",
    CONSISTENCY_WEAKENED: "已削弱",
    CONSISTENCY_BROKEN: "已破坏",
    CONSISTENCY_FULFILLED: "已兑现",
}


def _style(cell, *, fill: str = "FFFFFF", bold: bool = False, color: str = INK) -> None:
    cell.font = Font(name="Microsoft YaHei", size=11, bold=bold, color=color)
    cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(vertical="top", wrap_text=True)


def _title(ws, title: str, subtitle: str, columns: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    _style(ws.cell(1, 1, title), fill=GREEN, bold=True, color="FFFFFF")
    _style(ws.cell(2, 1, subtitle), fill=GREY, bold=True)
    ws.row_dimensions[1].height = 32
    ws.row_dimensions[2].height = 34


def _header(ws, row: int, columns: list[str]) -> int:
    for column, value in enumerate(columns, 1):
        _style(ws.cell(row, column, value), fill=BLUE, bold=True, color="FFFFFF")
    return row + 1


def _widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _label(mapping: Mapping[str, str], value: str) -> str:
    return mapping.get(value, value)


def _name(symbol: str, names: Mapping[str, str]) -> str:
    return names.get(symbol, symbol)


def _join(values: tuple[str, ...]) -> str:
    return "；".join(value for value in values if value)


def _write_row(ws, row: int, values: list[Any], fill: str = "FFFFFF") -> None:
    for column, value in enumerate(values, 1):
        _style(ws.cell(row, column, value), fill=fill)


def _overview(
    wb: Workbook,
    collection: DecisionHistoryCollection,
    names: Mapping[str, str],
) -> None:
    ws = wb.create_sheet(OVERVIEW_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "命名空间",
        "Entry类型",
        "Entry日期",
        "原始论点摘要",
        "最新人工决定",
        "最新一致性",
        "动作",
    ]
    _widths(ws, [12, 18, 12, 14, 13, 44, 18, 14, 12])
    _title(
        ws,
        "M3 论点连续性历史链",
        "模拟演示链路：只解释原始理由是否变化，不生成订单或真实成交。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for chain in collection.chains:
        latest = chain.latest_journal
        consistency = chain.latest_consistency
        _write_row(
            ws,
            row,
            [
                chain.symbol,
                _name(chain.symbol, names),
                "模拟",
                _label(_ENTRY_LABELS, chain.entry.entry_type),
                chain.entry.entry_date.isoformat(),
                chain.entry.thesis,
                _label(_HUMAN_LABELS, latest.human_decision) if latest else "",
                _label(_CONSISTENCY_LABELS, consistency.status) if consistency else "",
                ACTION_NO_ORDER,
            ],
        )
        row += 1


def _entry_sheet(
    wb: Workbook,
    collection: DecisionHistoryCollection,
    names: Mapping[str, str],
) -> None:
    ws = wb.create_sheet(ENTRY_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "Entry ID",
        "类型",
        "日期",
        "确认价",
        "Thesis",
        "回报来源",
        "预期差",
        "Bear",
        "Base",
        "Bull",
        "置信度",
        "股息论点",
        "持有逻辑",
        "风险",
        "反证",
        "Breaker",
        "催化剂",
        "可加仓条件",
        "停止加仓条件",
        "减仓条件",
        "退出条件",
        "事后重建说明",
        "来源Hash",
    ]
    _widths(
        ws,
        [12, 18, 30, 12, 13, 12, 42, 32, 32, 12, 12, 12, 10, 36, 36, 36, 36, 36, 24, 32, 32, 32, 32, 22, 64],
    )
    _title(
        ws,
        "原始 Entry Thesis",
        "冻结买入/持有时的原始理由；后续复核只引用本页，不覆盖原始值。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for chain in collection.chains:
        entry = chain.entry
        _write_row(
            ws,
            row,
            [
                chain.symbol,
                _name(chain.symbol, names),
                entry.entry_id,
                _label(_ENTRY_LABELS, entry.entry_type),
                entry.entry_date.isoformat(),
                entry.entry_price or "",
                entry.thesis,
                entry.return_driver,
                entry.mispricing_hypothesis,
                entry.bear_value or "",
                entry.base_value or "",
                entry.bull_value or "",
                entry.confidence,
                entry.dividend_thesis,
                entry.hold_logic,
                _join(entry.risks),
                _join(entry.counter_evidence),
                _join(entry.breakers),
                _join(entry.catalysts),
                _join(entry.reasons_to_add),
                _join(entry.reasons_not_to_add),
                _join(entry.reasons_to_reduce),
                _join(entry.reasons_to_exit),
                entry.reconstructed_note,
                entry.source_sha256,
            ],
        )
        row += 1


def _journal_sheet(
    wb: Workbook,
    collection: DecisionHistoryCollection,
    names: Mapping[str, str],
) -> None:
    ws = wb.create_sheet(JOURNAL_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "日志ID",
        "决策时间",
        "复核状态",
        "系统原因",
        "人工决定",
        "人工原因",
        "Entry ID",
        "确认价",
        "命名空间",
        "更正前日志",
        "来源Hash",
    ]
    _widths(ws, [12, 18, 30, 22, 24, 42, 14, 40, 30, 12, 12, 30, 64])
    _title(
        ws,
        "人工决策日志",
        "按时间保留决定与原因；全部为模拟记录，后续更正通过 previous_journal_id 链接。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for chain in collection.chains:
        for journal in chain.journals:
            _write_row(
                ws,
                row,
                [
                    chain.symbol,
                    _name(chain.symbol, names),
                    journal.journal_id,
                    journal.decision_at.isoformat(),
                    journal.review_status,
                    journal.system_reason,
                    _label(_HUMAN_LABELS, journal.human_decision),
                    journal.human_reason,
                    journal.entry_id or "",
                    journal.confirmed_price or "",
                    "模拟",
                    journal.previous_journal_id or "",
                    journal.source_sha256,
                ],
                fill=AMBER if journal.is_correction else "FFFFFF",
            )
            row += 1


def _consistency_sheet(
    wb: Workbook,
    collection: DecisionHistoryCollection,
    names: Mapping[str, str],
) -> None:
    ws = wb.create_sheet(CONSISTENCY_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "复核ID",
        "Entry ID",
        "复核日期",
        "总体状态",
        "维度",
        "原始值",
        "当前值",
        "变化",
        "变化原因",
        "证据ID",
        "来源Hash",
    ]
    _widths(ws, [12, 18, 30, 30, 13, 14, 16, 36, 36, 12, 42, 28, 64])
    _title(
        ws,
        "原始论点一致性复核",
        "只比较原Entry与当前证据，不因价格变化自动给出减仓或退出结论。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for chain in collection.chains:
        for review in chain.consistency_reviews:
            for comparison in review.comparisons:
                _write_row(
                    ws,
                    row,
                    [
                        chain.symbol,
                        _name(chain.symbol, names),
                        review.review_id,
                        review.entry_id,
                        review.as_of.isoformat(),
                        _label(_CONSISTENCY_LABELS, review.status),
                        comparison.dimension,
                        comparison.original_value,
                        comparison.current_value,
                        _label(_IMPACT_LABELS, comparison.impact),
                        comparison.change_reason,
                        "；".join(comparison.evidence_ids),
                        review.source_sha256,
                    ],
                )
                row += 1


def _source_sheet(wb: Workbook, collection: DecisionHistoryCollection) -> None:
    ws = wb.create_sheet(SOURCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "对象类型", "对象ID", "SHA-256"]
    _widths(ws, [12, 22, 38, 64])
    _title(
        ws,
        "来源哈希绑定",
        "Entry、每条决策日志和每次一致性复核均绑定不可变输入 Hash。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for chain in collection.chains:
        _write_row(
            ws,
            row,
            [chain.symbol, "EntryThesisSnapshot", chain.entry.entry_id, chain.entry.source_sha256],
        )
        row += 1
        for journal in chain.journals:
            _write_row(
                ws,
                row,
                [chain.symbol, "DecisionJournalEntry", journal.journal_id, journal.source_sha256],
            )
            row += 1
        for review in chain.consistency_reviews:
            _write_row(
                ws,
                row,
                [chain.symbol, "InvestmentConsistencyReview", review.review_id, review.source_sha256],
            )
            row += 1


def build_history_workbook(
    collection: DecisionHistoryCollection,
    *,
    security_names: Mapping[str, str] | None = None,
) -> Workbook:
    if collection.action != ACTION_NO_ORDER:
        raise ValueError("History workbook requires action=no_order")
    if not collection.chains:
        raise ValueError("History workbook requires at least one simulated chain")
    if any(chain.namespace != PUBLIC_NAMESPACE for chain in collection.chains):
        raise ValueError("Public history workbook requires simulated chains")
    names = dict(security_names or {})
    wb = Workbook()
    wb.remove(wb.active)
    _overview(wb, collection, names)
    _entry_sheet(wb, collection, names)
    _journal_sheet(wb, collection, names)
    _consistency_sheet(wb, collection, names)
    _source_sheet(wb, collection)
    wb.active = 0
    return wb


def write_history_workbook(
    collection: DecisionHistoryCollection,
    *,
    output: Path,
    root: Path,
    security_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write a deterministic, no-overwrite simulated history workbook."""
    output = output.resolve()
    root = root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("History workbook output escapes its root")
    if output.exists():
        raise ValueError(f"History workbook already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_history_workbook(collection, security_names=security_names)
    workbook.save(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "workbook_path": str(output.relative_to(root)),
        "workbook_sha256": digest,
        "sheet_count": len(workbook.sheetnames),
        "chain_count": len(collection.chains),
        "namespace": PUBLIC_NAMESPACE,
        "action": ACTION_NO_ORDER,
    }
