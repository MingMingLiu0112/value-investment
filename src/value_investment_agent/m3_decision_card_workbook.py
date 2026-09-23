"""Presentation-only M3 decision-card workbook candidate.

This workbook consumes the non-personal DecisionCard read model.  It is a
standalone candidate and never mutates the WPS production workbook.  It has no
valuation arithmetic, position sizing or order column.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .decision_read_model import (
    ACTION_NO_ORDER,
    CARD_ENTRY_MISSING,
    CARD_ENTRY_NOT_REQUIRED,
    CARD_ENTRY_RECONSTRUCTED,
    CARD_JOURNAL_ABSENT,
    CARD_PORTFOLIO_CONFIRMED,
    CARD_PORTFOLIO_MISSING,
    CARD_PORTFOLIO_PROVIDED_UNCONFIRMED,
    CARD_REASON_ENTRY_MISSING,
    CARD_REASON_HUMAN_REVIEW_REQUIRED,
    CARD_REASON_OTHER,
    CARD_REASON_PERSONAL_INPUT_MISSING,
    CARD_REASON_PRICE_UNAVAILABLE,
    CARD_REASON_RESEARCH_INCOMPLETE,
    DecisionCard,
    DecisionCardCollection,
)
from .investment_decision import (
    STATUS_HOLD,
    STATUS_INSUFFICIENT_RESEARCH,
    STATUS_MANUAL_ADD_REVIEW,
    STATUS_MANUAL_BUY_REVIEW,
    STATUS_MANUAL_EXIT_REVIEW,
    STATUS_MANUAL_REDUCE_REVIEW,
    STATUS_RESEARCH_CANDIDATE,
    STATUS_WATCH,
    STATUS_WAIT_FOR_PRICE,
)


OVERVIEW_SHEET = "00_决策卡"
MISSING_SHEET = "01_缺失与阻断"
SOURCE_SHEET = "02_来源哈希"
EVIDENCE_SHEET = "03_证据引用"

INK = "24312D"
GREEN = "18755D"
BLUE = "245D83"
AMBER = "FFF1D6"
GREY = "EFF3F1"
RED = "C0392B"

_STATUS_LABELS = {
    STATUS_INSUFFICIENT_RESEARCH: "研究证据不足",
    STATUS_WAIT_FOR_PRICE: "等待有效价格",
    STATUS_RESEARCH_CANDIDATE: "研究候选",
    STATUS_WATCH: "等待人工复核",
    STATUS_MANUAL_BUY_REVIEW: "待人工复核",
    STATUS_MANUAL_ADD_REVIEW: "待人工复核",
    STATUS_HOLD: "待人工复核",
    STATUS_MANUAL_REDUCE_REVIEW: "待人工复核",
    STATUS_MANUAL_EXIT_REVIEW: "待人工复核",
}
_REASON_LABELS = {
    CARD_REASON_RESEARCH_INCOMPLETE: "研究证据不足",
    CARD_REASON_PRICE_UNAVAILABLE: "价格证据不可用",
    CARD_REASON_PERSONAL_INPUT_MISSING: "个人组合输入缺失",
    CARD_REASON_ENTRY_MISSING: "原始 Entry 缺失",
    CARD_REASON_HUMAN_REVIEW_REQUIRED: "需要人工复核",
    CARD_REASON_OTHER: "其他",
}
_PORTFOLIO_LABELS = {
    CARD_PORTFOLIO_MISSING: "缺失",
    CARD_PORTFOLIO_PROVIDED_UNCONFIRMED: "已提供，未确认",
    CARD_PORTFOLIO_CONFIRMED: "已确认",
}
_ENTRY_LABELS = {
    CARD_ENTRY_NOT_REQUIRED: "本卡不需要",
    CARD_ENTRY_MISSING: "缺失",
    CARD_ENTRY_RECONSTRUCTED: "已标注事后重建",
    "AVAILABLE": "已提供",
}
_MISSING_EXPLANATIONS = {
    "research_or_valuation_inputs": "研究与估值前置条件未完成，不能进入正向决策复核。",
    "verified_price_or_quote": "尚无通过模型有效期与双源校验的当前价格/报价链。",
    "portfolio_input": "用户尚未提供个人组合输入，不能形成个人化正向复核。",
    "portfolio_capacity_confirmation": "最小组合容量尚未由用户人工确认。",
    "original_entry": "缺少原始 Entry Thesis，不能形成 HOLD/ADD/REDUCE/EXIT 复核。",
    "human_decision": "最终动作仍须用户明确做出人工决定。",
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
    ws.row_dimensions[2].height = 32


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


def _overview(wb: Workbook, collection: DecisionCardCollection, names: Mapping[str, str]) -> None:
    ws = wb.create_sheet(OVERVIEW_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "决策时点",
        "系统状态",
        "原因类别",
        "决策意图",
        "组合输入",
        "原始 Entry",
        "人工决策记录",
        "阻断数",
        "证据构件数",
        "来源哈希数",
    ]
    _widths(ws, [11, 14, 14, 17, 20, 14, 16, 15, 15, 9, 11, 11])
    _title(
        ws,
        "M3 非个人化失败关闭决策卡候选",
        "action=no_order；全部卡片均要求人工复核；未形成任何正向复核、仓位或订单。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for card in collection.cards:
        values = [
            card.symbol,
            _name(card.symbol, names),
            card.decision_as_of.isoformat(),
            _label(_STATUS_LABELS, card.status),
            _label(_REASON_LABELS, card.reason_kind),
            "未提交" if card.decision_intent is None else card.decision_intent,
            _label(_PORTFOLIO_LABELS, card.portfolio_status),
            _label(_ENTRY_LABELS, card.entry_status),
            "无" if card.journal_status == CARD_JOURNAL_ABSENT else "有",
            len(card.blockers),
            len(card.artifact_refs),
            len(card.source_hashes),
        ]
        for column, value in enumerate(values, 1):
            fill = AMBER if card.reason_kind in {
                CARD_REASON_RESEARCH_INCOMPLETE,
                CARD_REASON_PRICE_UNAVAILABLE,
                CARD_REASON_PERSONAL_INPUT_MISSING,
                CARD_REASON_ENTRY_MISSING,
            } else "FFFFFF"
            _style(ws.cell(row, column, value), fill=fill)
        row += 1


def _missing(wb: Workbook, collection: DecisionCardCollection, names: Mapping[str, str]) -> None:
    ws = wb.create_sheet(MISSING_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "公司", "缺失输入", "为什么不能形成正向复核", "相关阻断"]
    _widths(ws, [11, 14, 28, 48, 72])
    _title(
        ws,
        "缺失输入与阻断",
        "研究与价格状态、个人组合、原始 Entry 和人工决定分别记录，不合并成一个模糊状态。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for card in collection.cards:
        blockers = "\n".join(card.blockers)
        for missing in card.missing_inputs:
            values = [
                card.symbol,
                _name(card.symbol, names),
                missing,
                _MISSING_EXPLANATIONS.get(missing, "缺少完成该决策复核所需输入。"),
                blockers if missing in {
                    "research_or_valuation_inputs",
                    "verified_price_or_quote",
                } else "",
            ]
            for column, value in enumerate(values, 1):
                _style(ws.cell(row, column, value), fill=AMBER if value else "FFFFFF")
            row += 1
        if not card.missing_inputs:
            _style(ws.cell(row, 1, card.symbol))
            _style(ws.cell(row, 2, _name(card.symbol, names)))
            _style(ws.cell(row, 3, "无自动可判定缺失；仍须人工复核"), fill=GREY)
            row += 1


def _source(wb: Workbook, collection: DecisionCardCollection) -> None:
    ws = wb.create_sheet(SOURCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "来源键", "制品类型", "制品 ID", "SHA-256", "可用时点"]
    _widths(ws, [11, 30, 30, 34, 64, 14])
    _title(
        ws,
        "来源哈希绑定",
        "每张卡保留 M1 集成运行、决策复核和证据包三个不可变来源 Hash；篡改任一来源会导致绑定失效。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for card in collection.cards:
        for source in card.source_hashes:
            values = [
                card.symbol,
                source.source_key,
                source.artifact_type,
                source.artifact_id or "",
                source.sha256,
                source.available_at.isoformat() if source.available_at else "",
            ]
            for column, value in enumerate(values, 1):
                _style(ws.cell(row, column, value), fill=GREY)
            row += 1


def _evidence(wb: Workbook, collection: DecisionCardCollection) -> None:
    ws = wb.create_sheet(EVIDENCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "证据 ID", "类型", "路径", "来源 URL", "SHA-256"]
    _widths(ws, [11, 34, 24, 68, 58, 64])
    _title(
        ws,
        "证据引用",
        "只展示冻结 M1 证据的 ID、来源 URL 和原件 Hash；缺失证据不会被补成可用值。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for card in collection.cards:
        for ref in card.evidence_refs:
            url = str(ref.get("source_url") or ref.get("url") or "")
            values = [
                card.symbol,
                str(ref.get("id") or ""),
                str(ref.get("kind") or ref.get("provider") or ""),
                str(ref.get("path") or ref.get("location") or ""),
                url,
                str(ref.get("sha256") or ""),
            ]
            for column, value in enumerate(values, 1):
                _style(ws.cell(row, column, value))
            if url.startswith(("http://", "https://")):
                cell = ws.cell(row, 5, url)
                cell.hyperlink = url
                cell.font = Font(
                    name="Microsoft YaHei",
                    size=11,
                    color=BLUE,
                    underline="single",
                )
            row += 1


def build_decision_card_workbook(
    collection: DecisionCardCollection,
    *,
    security_names: Mapping[str, str] | None = None,
) -> Workbook:
    if collection.action != ACTION_NO_ORDER:
        raise ValueError("Decision-card workbook requires action=no_order")
    if any(card.action != ACTION_NO_ORDER for card in collection.cards):
        raise ValueError("Decision cards must remain no_order")
    names = dict(security_names or {})
    wb = Workbook()
    wb.remove(wb.active)
    _overview(wb, collection, names)
    _missing(wb, collection, names)
    _source(wb, collection)
    _evidence(wb, collection)
    wb.active = 0
    return wb


def write_decision_card_workbook(
    collection: DecisionCardCollection,
    *,
    output: Path,
    root: Path,
    security_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Write a deterministic, no-overwrite, hash-pinned candidate workbook."""
    output = output.resolve()
    root = root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Decision-card workbook output escapes its root")
    if output.exists():
        raise ValueError(f"Decision-card workbook already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_decision_card_workbook(collection, security_names=security_names)
    workbook.save(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "workbook_path": str(output.relative_to(root)),
        "workbook_sha256": digest,
        "sheet_count": len(workbook.sheetnames),
        "card_count": len(collection.cards),
        "positive_review_count": sum(card.is_positive_review() for card in collection.cards),
        "action": ACTION_NO_ORDER,
    }
