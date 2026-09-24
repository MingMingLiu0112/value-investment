"""Presentation workbook for a reconstructed M3 evidence continuity trace.

This is a standalone public candidate.  It contains no actual account data,
human decision, position sizing or executable instruction.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .m3_reconstructed_evidence_continuity import (
    ACTION_NO_ORDER,
    DIRECTION_DOWN,
    DIRECTION_UNCHANGED,
    DIRECTION_UP,
    IMPACT_NEUTRAL,
    IMPACT_STRENGTHENED,
    IMPACT_WEAKENED,
    METRIC_BASIC_EPS,
    METRIC_CASH_PER_SHARE,
    METRIC_CLOSE_PRICE,
    METRIC_ENDING_SHARES,
    METRIC_PARENT_EQUITY,
    METRIC_PARENT_PROFIT,
    TRACE_NAMESPACE,
    M3ReconstructedEvidenceContinuity,
)


BOUNDARY_SHEET = "00_重建边界"
BASELINE_SHEET = "01_历史基准"
DISCLOSURE_SHEET = "02_官方披露演变"
COMPARISON_SHEET = "03_一致性观察"
CONCLUSION_SHEET = "04_阻断与结论"
SOURCE_SHEET = "05_来源哈希"

INK = "24312D"
GREEN = "18755D"
BLUE = "245D83"
AMBER = "FFF1D6"
GREY = "EFF3F1"
RED = "C0392B"

_METRIC_LABELS = {
    METRIC_PARENT_PROFIT: "归母净利润",
    METRIC_PARENT_EQUITY: "归母净资产",
    METRIC_BASIC_EPS: "基本每股收益",
    METRIC_ENDING_SHARES: "期末普通股数",
    METRIC_CLOSE_PRICE: "收盘价",
    METRIC_CASH_PER_SHARE: "每股现金分红",
}
_DIRECTION_LABELS = {
    DIRECTION_UP: "上升",
    DIRECTION_DOWN: "下降",
    DIRECTION_UNCHANGED: "持平",
    "NOT_COMPARABLE": "不可比",
}
_IMPACT_LABELS = {
    IMPACT_STRENGTHENED: "趋势加强",
    IMPACT_WEAKENED: "趋势减弱",
    IMPACT_NEUTRAL: "未变化",
    "NOT_COMPARABLE": "不可比",
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


def _write_row(ws, row: int, values: list[Any], fill: str = "FFFFFF") -> None:
    for column, value in enumerate(values, 1):
        _style(ws.cell(row, column, value), fill=fill)


def _boundary(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(BOUNDARY_SHEET)
    ws.sheet_view.showGridLines = False
    columns = ["项目", "值", "说明"]
    _widths(ws, [26, 46, 80])
    _title(
        ws,
        "M3 重建证据连续性边界",
        "这是真实官方披露演变，不含真实账户、原始论点确认或任何执行指令。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    rows = [
        ("Trace ID", trace.trace_id, "不可变证据链标识"),
        ("证券代码", trace.symbol, "贵州茅台"),
        ("命名空间", trace.namespace, "只表示重建证据连续性"),
        ("生成时间", trace.generated_at.isoformat(), "UTC"),
        ("历史基准日", trace.baseline.baseline_date.isoformat(), "冻结研究重放日期"),
        ("规则登记状态", trace.baseline.rule_registration_status, "追溯扩展，不是同期规则"),
        ("同期规则 PIT", "否", "仍为 NOT_PROVEN"),
        ("真实 Entry", "否", "没有使用真实账户或真实成交"),
        ("人工决定", "无", "本工件不记录任何人类决定"),
        ("结论状态", trace.conclusion_status, "只用于证据重放"),
        ("需要人工复核", "是", "任何研究结论仍需人工确认"),
        ("动作", trace.action, "全程保持 no_order"),
    ]
    for values in rows:
        _write_row(ws, row, list(values), fill=GREY if row % 2 == 0 else "FFFFFF")
        row += 1


def _baseline(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(BASELINE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "指标", "报告期", "时点口径", "披露值", "单位", "核验状态", "来源ID"]
    _widths(ws, [12, 16, 13, 14, 22, 12, 42, 32])
    _title(
        ws,
        "历史基准事实",
        trace.baseline.note,
        len(columns),
    )
    row = _header(ws, 4, columns)
    for fact in trace.baseline.facts:
        _write_row(
            ws,
            row,
            [
                trace.symbol,
                _label(_METRIC_LABELS, fact.metric),
                fact.period_end.isoformat(),
                fact.period_basis,
                str(fact.current_value),
                fact.unit,
                fact.validation_status,
                fact.reference_id,
            ],
        )
        row += 1


def _disclosures(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(DISCLOSURE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "观察ID",
        "披露编号",
        "标题",
        "报告期",
        "可用日期",
        "证据质量",
        "指标",
        "本期值",
        "上期值",
        "算术方向",
        "同比/环比百分比",
        "来源ID",
    ]
    _widths(ws, [28, 18, 30, 13, 22, 44, 16, 22, 22, 12, 18, 32])
    _title(
        ws,
        "官方披露演变",
        "只展示发行人在各期原始披露中的数值及简单算术变化；不是估值或论点结论。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for disclosure in trace.disclosures:
        for metric in disclosure.metrics:
            _write_row(
                ws,
                row,
                [
                    disclosure.observation_id,
                    disclosure.disclosure_id,
                    disclosure.title,
                    disclosure.report_period.isoformat(),
                    disclosure.available_at.isoformat(),
                    disclosure.evidence_quality,
                    _label(_METRIC_LABELS, metric.metric),
                    str(metric.current_value),
                    (
                        str(metric.comparative_value)
                        if metric.comparative_value is not None
                        else ""
                    ),
                    _label(_DIRECTION_LABELS, metric.change_direction),
                    (
                        f"{metric.percentage_change:.6f}%"
                        if metric.percentage_change is not None
                        else ""
                    ),
                    metric.reference_id,
                ],
                fill=AMBER if metric.change_direction == DIRECTION_DOWN else "FFFFFF",
            )
            row += 1


def _comparisons(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(COMPARISON_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["维度", "基准值", "观察ID", "观察值", "算术方向", "观察结论", "算术依据"]
    _widths(ws, [18, 22, 28, 22, 12, 14, 80])
    _title(
        ws,
        "一致性观察",
        "这里的加强/减弱只描述数值趋势，不等于原始投资论点已经兑现或破坏。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for comparison in trace.comparisons:
        _write_row(
            ws,
            row,
            [
                _label(_METRIC_LABELS, comparison.dimension),
                str(comparison.baseline_value),
                comparison.observation_id,
                str(comparison.observation_value),
                _label(_DIRECTION_LABELS, comparison.change_direction),
                _label(_IMPACT_LABELS, comparison.impact),
                comparison.arithmetic_note,
            ],
            fill=AMBER if comparison.impact == IMPACT_WEAKENED else "FFFFFF",
        )
        row += 1


def _conclusion(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(CONCLUSION_SHEET)
    ws.sheet_view.showGridLines = False
    columns = ["类型", "内容"]
    _widths(ws, [24, 130])
    _title(
        ws,
        "阻断与结论",
        "本工件不签发研究批准、价格结论、持有决定或执行动作。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    _write_row(ws, row, ["结论", trace.conclusion_status], fill=GREY)
    row += 1
    _write_row(ws, row, ["动作", trace.action], fill=GREY)
    row += 1
    for blocker in trace.blockers:
        _write_row(ws, row, ["阻断项", blocker], fill=AMBER)
        row += 1


def _sources(wb: Workbook, trace: M3ReconstructedEvidenceContinuity) -> None:
    ws = wb.create_sheet(SOURCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["来源ID", "类型", "可用时间", "路径", "来源URL", "SHA-256", "角色"]
    _widths(ws, [32, 20, 24, 76, 64, 64, 44])
    _title(
        ws,
        "来源哈希绑定",
        "每个官方披露、行情与重建输入均绑定本地原件 Hash 和可核验来源 URL。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for ref in trace.evidence_references:
        values = [
            ref.ref_id,
            ref.kind,
            ref.available_at.isoformat(),
            ref.path,
            ref.source_url,
            ref.sha256,
            ref.role,
        ]
        for column, value in enumerate(values, 1):
            _style(ws.cell(row, column, value), fill=GREY)
        if ref.source_url.startswith(("http://", "https://")):
            cell = ws.cell(row, 5, ref.source_url)
            cell.hyperlink = ref.source_url
            cell.font = Font(
                name="Microsoft YaHei",
                size=11,
                color=BLUE,
                underline="single",
            )
        row += 1


def build_reconstructed_evidence_workbook(
    trace: M3ReconstructedEvidenceContinuity,
) -> Workbook:
    if trace.action != ACTION_NO_ORDER:
        raise ValueError("Reconstructed evidence workbook requires no_order")
    if trace.namespace != TRACE_NAMESPACE:
        raise ValueError("Reconstructed evidence workbook requires the trace namespace")
    if trace.actual_entry_present or trace.human_decision is not None:
        raise ValueError("Reconstructed evidence workbook cannot contain private decisions")
    wb = Workbook()
    wb.remove(wb.active)
    _boundary(wb, trace)
    _baseline(wb, trace)
    _disclosures(wb, trace)
    _comparisons(wb, trace)
    _conclusion(wb, trace)
    _sources(wb, trace)
    wb.active = 0
    return wb


def write_reconstructed_evidence_workbook(
    trace: M3ReconstructedEvidenceContinuity,
    *,
    output: Path,
    root: Path,
) -> dict[str, Any]:
    """Write a deterministic, no-overwrite reconstructed evidence workbook."""
    output = output.resolve()
    root = root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Reconstructed evidence output escapes its root")
    if output.exists():
        raise ValueError(f"Reconstructed evidence workbook already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_reconstructed_evidence_workbook(trace)
    workbook.save(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "workbook_path": str(output.relative_to(root)),
        "workbook_sha256": digest,
        "sheet_count": len(workbook.sheetnames),
        "trace_id": trace.trace_id,
        "trace_sha256": trace.trace_sha256,
        "namespace": trace.namespace,
        "action": ACTION_NO_ORDER,
    }
