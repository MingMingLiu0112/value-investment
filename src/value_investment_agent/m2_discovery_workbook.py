"""Presentation-only M2 opportunity workbook.

This workbook is derived from an immutable DiscoveryRunReceipt.  It contains
no valuation arithmetic, order, position or BUY column.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .m2_discovery_engine import M2ScreeningPolicy
from .m2_opportunity_discovery import (
    ACTION_NO_ORDER,
    CANDIDATE_CLASS_VERIFIED,
    CHANNEL_CYCLICAL,
    CHANNEL_DIVIDEND,
    CHANNEL_QUALITY,
    CHANNEL_VALUE,
    CandidateReason,
    ChannelResult,
    DiscoveryRunReceipt,
    ExcludedSecurity,
)
from .m2_research_report import (
    M2ResearchReportBatch,
    VERDICT_INSUFFICIENT,
    VERDICT_PENDING,
    VERDICT_REJECTED,
)


OVERVIEW_SHEET = "00_M2总览"
POOL_SHEET = "01_候选池"
QUALITY_SHEET = "02_质量候选"
DIVIDEND_SHEET = "03_现金回报候选"
VALUE_SHEET = "04_价值候选"
CYCLICAL_SHEET = "05_周期候选"
HEALTH_SHEET = "06_数据健康"
EXCLUDED_SHEET = "07_不支持与缺失"
LEGACY_SHEET = "08_Legacy对比"
EVIDENCE_SHEET = "09_证据清单"
COVERAGE_SHEET = "10_逐通道覆盖"
RESEARCH_SHEET = "11_研究报告"
RESEARCH_EVIDENCE_SHEET = "12_研究证据"

VERDICT_LABELS = {
    VERDICT_PENDING: "待深研",
    VERDICT_REJECTED: "通道否决",
    VERDICT_INSUFFICIENT: "证据不足",
}
CHANNEL_LABELS = {
    CHANNEL_QUALITY: "质量",
    CHANNEL_DIVIDEND: "股息/现金回报",
    CHANNEL_VALUE: "价值",
    CHANNEL_CYCLICAL: "周期",
}
VERDICT_FILLS = {
    VERDICT_PENDING: "E4F3EE",
    VERDICT_REJECTED: "F8E7E6",
    VERDICT_INSUFFICIENT: "FFF1D6",
}

INK = "24312D"
GREEN = "18755D"
BLUE = "245D83"
AMBER = "FFF1D6"
GREY = "EFF3F1"
RED = "C0392B"


def _style(cell, *, fill: str = "FFFFFF", bold: bool = False, color: str = INK) -> None:
    cell.font = Font(name="Microsoft YaHei", size=11, bold=bold, color=color)
    cell.fill = PatternFill("solid", fgColor=fill)
    cell.alignment = Alignment(vertical="top", wrap_text=True)


def _title(ws, title: str, subtitle: str, columns: int) -> None:
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=columns)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=columns)
    _style(ws.cell(1, 1, title), fill=GREEN, bold=True, color="FFFFFF")
    _style(ws.cell(2, 1, subtitle), fill=GREY, bold=True)
    ws.row_dimensions[1].height = 34
    ws.row_dimensions[2].height = 28


def _header(ws, row: int, columns: list[str]) -> int:
    for column, value in enumerate(columns, 1):
        _style(ws.cell(row, column, value), fill=BLUE, bold=True, color="FFFFFF")
    return row + 1


def _widths(ws, widths: list[int]) -> None:
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width


def _number(value: Any, digits: int = 2) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _metrics_text(metrics: Mapping[str, Any]) -> str:
    labels = {
        "pe_ttm": "PE(TTM)",
        "pb": "PB",
        "market_cap": "总市值",
        "quality_score": "质量分",
        "coverage_ratio": "证据覆盖",
        "cash_dps": "每股分红",
        "declared_yield": "参考股息率",
        "earnings_yield": "盈利收益率",
        "implied_roe": "隐含ROE",
        "fcf_yield": "FCF Yield",
        "ev_ebit": "EV/EBIT",
        "normalized_earnings": "正常化盈利",
        "current_vs_normalized_roe": "当前/正常化ROE",
        "dividend_status": "分红状态",
    }
    lines: list[str] = []
    for key, value in metrics.items():
        label = labels.get(key, key)
        if value is None:
            lines.append(f"{label}: 缺失")
        elif key in {"declared_yield", "earnings_yield", "implied_roe", "coverage_ratio"}:
            lines.append(f"{label}: {float(value) * 100:.2f}%")
        else:
            lines.append(f"{label}: {_number(value)}")
    return "\n".join(lines)


def _candidate_row(ws, row: int, candidate: CandidateReason, include_channel: bool) -> int:
    _style(ws.cell(row, 1, candidate.symbol), bold=True)
    _style(ws.cell(row, 2, candidate.name))
    if include_channel:
        _style(ws.cell(row, 3, candidate.channel), fill=GREY)
        offset = 1
    else:
        offset = 0
    _style(ws.cell(row, 3 + offset, candidate.priority_tier), bold=True)
    _style(ws.cell(row, 4 + offset, candidate.profile_status))
    _style(
        ws.cell(row, 5 + offset, "已核候选" if candidate.candidate_class == CANDIDATE_CLASS_VERIFIED else "研究线索"),
        fill=GREY if candidate.candidate_class == CANDIDATE_CLASS_VERIFIED else AMBER,
    )
    _style(
        ws.cell(row, 6 + offset, candidate.data_status),
        fill=AMBER if candidate.data_status == "PARTIAL" else "FFFFFF",
    )
    _style(ws.cell(row, 7 + offset, candidate.evidence_date))
    _style(ws.cell(row, 8 + offset, candidate.metrics.get("industry") or ""))
    _style(ws.cell(row, 9 + offset, "\n".join(candidate.reasons)))
    _style(ws.cell(row, 10 + offset, _metrics_text(candidate.metrics)))
    ws.row_dimensions[row].height = max(58, len(candidate.reasons) * 16)
    return row + 1


def _candidate_sheet(
    wb: Workbook,
    title: str,
    subtitle: str,
    candidates: Iterable[CandidateReason],
    *,
    include_channel: bool,
) -> None:
    ws = wb.create_sheet(title)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = ["证券代码", "公司", "通道", "优先级", "画像", "研究层级", "数据", "证据日期", "行业", "Why Now / 原因", "关键指标"]
    if not include_channel:
        columns = columns[:2] + columns[3:]
    _widths(ws, [11, 16, 18, 9, 13, 12, 12, 12, 14, 62, 46][: len(columns)])
    _title(ws, title, subtitle, len(columns))
    row = _header(ws, 4, columns)
    for candidate in candidates:
        row = _candidate_row(ws, row, candidate, include_channel)


def _overview(wb: Workbook, receipt: DiscoveryRunReceipt, policy: M2ScreeningPolicy) -> None:
    ws = wb.create_sheet(OVERVIEW_SHEET)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 100
    _title(
        ws,
        "M2 多通道机会发现",
        (
            f"run_id={receipt.run_id} | as_of={receipt.as_of.isoformat()} | "
            f"rule={receipt.rule_version} | action={receipt.action}"
        ),
        2,
    )
    row = 4
    coverage_text = "；".join(
        (
            f"{channel}: 分母 {result.coverage_count} / PASS {result.pass_count} / "
            f"REJECTED {result.rejected_count} / DATA_GAP {result.data_gap_count} / "
            f"CONFLICT {result.conflict_count} / UNSUPPORTED {result.unsupported_count} / "
            f"NOT_EVALUATED {result.not_evaluated_count} / BUDGET_EXCLUDED {result.budget_excluded_count}"
        )
        for channel, result in receipt.channel_results.items()
    )
    lead_count = sum(len(items) for items in receipt.candidate_pool().values())
    verified_count = sum(len(items) for items in receipt.verified_candidate_pool().values())
    quality_verified_count = len(
        receipt.verified_candidate_pool().get(CHANNEL_QUALITY, ())
    )
    quality_evidence_count = receipt.data_health.financial_evidence_count
    quality_coverage_status = (
        "COVERAGE_LIMITED"
        if quality_evidence_count < receipt.data_health.universe_count
        else "COMPLETE"
    )
    items = [
        ("产品结论", "系统只发现值得深研的公司，不生成估值、BUY、仓位或订单。"),
        ("Universe 分母", f"{receipt.data_health.universe_count} 家官方证券清单，行情匹配 {receipt.data_health.matched_quote_count} 家。"),
        ("数据健康", f"{receipt.data_health.status}；阻断 {len(receipt.data_health.blockers)} 项。"),
        ("逐通道覆盖", coverage_text),
        ("候选总量", f"{receipt.legacy_comparison.new_candidate_count} 家，跨通道可能重复。"),
        ("研究层级", f"研究线索 {lead_count} 条；已核候选 {verified_count} 条。线索不视为研究完成。"),
        (
            "Quality 通道覆盖",
            (
                f"Quality Channel Coverage: {quality_evidence_count} / "
                f"{receipt.data_health.universe_count} have usable quality evidence"
            ),
        ),
        ("Quality 覆盖状态", quality_coverage_status),
        ("Quality 已核线索", str(quality_verified_count)),
        (
            "Quality 覆盖解释",
            "当前数据覆盖不足，不能把 0 候选解释成市场没有高质量公司。",
        ),
        ("预算外通过者", f"各通道超出展示预算的通过者已在覆盖账中保留，不静默删除。"),
        ("Legacy 对比", f"{receipt.legacy_comparison.legacy_candidate_count} 家旧 PE/PB 阴影候选，与新池重叠 {receipt.legacy_comparison.overlap_count} 家。"),
        ("覆盖签名", receipt.coverage_signature),
        ("候选签名", receipt.candidate_signature),
    ]
    for label, value in items:
        _style(ws.cell(row, 1, label), fill=GREY, bold=True)
        _style(ws.cell(row, 2, str(value)))
        row += 1


def _health(wb: Workbook, receipt: DiscoveryRunReceipt) -> None:
    ws = wb.create_sheet(HEALTH_SHEET)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 30
    _title(ws, "全市场数据健康", "缺失、冲突和不支持行业必须可见；缺失不得视为 0。", 2)
    row = _header(ws, 4, ["指标", "数量"])
    health = receipt.data_health
    rows = [
        ("状态", health.status),
        ("官方 Universe", health.universe_count),
        ("行情快照", health.quote_count),
        ("行情与官方清单匹配", health.matched_quote_count),
        ("官方清单缺行情", health.missing_quote_count),
        ("行情不在官方清单", health.extra_quote_count),
        ("双源价格冲突", health.price_conflict_count),
        ("申万行业映射", health.industry_mapping_count),
        ("财务证据公司数", health.financial_evidence_count),
        ("分红证据公司数", health.dividend_evidence_count),
        ("金融行业待专用模型", health.unsupported_financial_count),
    ]
    for label, value in rows:
        _style(ws.cell(row, 1, label), fill=GREY)
        _style(ws.cell(row, 2, str(value)))
        row += 1
    row += 1
    _style(ws.cell(row, 1, "阻断项"), fill=BLUE, bold=True, color="FFFFFF")
    row += 1
    for blocker in health.blockers:
        _style(ws.cell(row, 1, blocker), fill=AMBER)
        row += 1


def _excluded(wb: Workbook, receipt: DiscoveryRunReceipt) -> None:
    ws = wb.create_sheet(EXCLUDED_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    _widths(ws, [12, 18, 22, 50, 18, 14])
    _title(ws, "不支持与缺失", "银行/保险/券商等不进入通用通道；金融专用模型另评。", 6)
    row = _header(ws, 4, ["证券代码", "公司", "通道", "原因", "画像", "证据日期"])
    seen: set[tuple[str, str, str]] = set()
    for channel, result in receipt.channel_results.items():
        for item in [*result.excluded, *result.missing]:
            key = (item.symbol, item.reason, channel)
            if key in seen:
                continue
            seen.add(key)
            _style(ws.cell(row, 1, item.symbol))
            _style(ws.cell(row, 2, item.name))
            _style(ws.cell(row, 3, channel))
            _style(ws.cell(row, 4, item.reason))
            _style(ws.cell(row, 5, item.profile_status))
            _style(ws.cell(row, 6, item.evidence_date))
            row += 1


def _legacy(wb: Workbook, receipt: DiscoveryRunReceipt) -> None:
    ws = wb.create_sheet(LEGACY_SHEET)
    ws.sheet_view.showGridLines = False
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 100
    _title(ws, "Legacy PE/PB Shadow 对比", receipt.legacy_comparison.note, 2)
    row = _header(ws, 4, ["项目", "数值"])
    comparison = receipt.legacy_comparison
    for label, value in (
        ("Legacy 候选数", comparison.legacy_candidate_count),
        ("M2 新候选数", comparison.new_candidate_count),
        ("重叠数", comparison.overlap_count),
    ):
        _style(ws.cell(row, 1, label), fill=GREY)
        _style(ws.cell(row, 2, str(value)))
        row += 1
    row += 1
    _style(ws.cell(row, 1, "Legacy 证券代码"), fill=BLUE, bold=True, color="FFFFFF")
    row += 1
    _style(ws.cell(row, 1, "、".join(comparison.legacy_candidates)), fill=GREY)


def _evidence(wb: Workbook, receipt: DiscoveryRunReceipt) -> None:
    ws = wb.create_sheet(EVIDENCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    _widths(ws, [18, 48, 70, 72, 28])
    _title(ws, "运行证据清单", "每个原始快照都保留路径与 SHA-256，可重放。", 5)
    row = _header(ws, 4, ["证据 ID", "本地路径", "来源", "URL", "抓取时间"])
    for reference in receipt.evidence_refs:
        _style(ws.cell(row, 1, reference.id))
        _style(ws.cell(row, 2, reference.path))
        _style(ws.cell(row, 3, reference.source_name))
        _style(ws.cell(row, 4, reference.source_url))
        _style(ws.cell(row, 5, reference.fetched_at.isoformat()))
        row += 1


def _coverage(wb: Workbook, receipt: DiscoveryRunReceipt) -> None:
    ws = wb.create_sheet(COVERAGE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    _widths(ws, [12, 18, 22, 18, 72, 14, 14])
    _title(
        ws,
        "逐证券逐通道覆盖",
        "覆盖账保留完整官方分母、原因、画像与证据日期；PASS 不等于买入。",
        7,
    )
    row = _header(ws, 4, ["证券代码", "公司", "通道", "状态", "原因", "画像", "证据日期"])
    for channel, result in receipt.channel_results.items():
        for evaluation in result.evaluations:
            fill = "FFFFFF"
            if evaluation.status == "PASS":
                fill = "E4F3EE"
            elif evaluation.status == "BUDGET_EXCLUDED":
                fill = AMBER
            elif evaluation.status in {"DATA_GAP", "CONFLICT", "UNSUPPORTED"}:
                fill = "F8E7E6"
            _style(ws.cell(row, 1, evaluation.symbol))
            _style(ws.cell(row, 2, evaluation.name))
            _style(ws.cell(row, 3, channel), fill=GREY)
            _style(ws.cell(row, 4, evaluation.status), fill=fill, bold=True)
            _style(ws.cell(row, 5, evaluation.reason))
            _style(ws.cell(row, 6, evaluation.profile_status))
            _style(ws.cell(row, 7, evaluation.evidence_date))
            row += 1


def _research_summary_links(wb: Workbook, batch: M2ResearchReportBatch) -> None:
    ws = wb[OVERVIEW_SHEET]
    row = ws.max_row + 1
    substantive = batch.substantive_reports()
    rejected = sum(report.verdict == VERDICT_REJECTED for report in batch.reports)
    pending = sum(report.verdict == VERDICT_PENDING for report in batch.reports)
    insufficient = sum(
        report.verdict == VERDICT_INSUFFICIENT for report in batch.reports
    )
    links = [
        (
            "研究/否决报告",
            (
                f"{len(batch.reports)} 份；待深研 {pending} / 通道否决 {rejected} / "
                f"证据不足 {insufficient}；实质报告 {len(substantive)} 份"
            ),
            RESEARCH_SHEET,
        ),
        (
            "研究证据",
            "点击查看每条报告对应的来源 URL、原件 SHA-256、报告期与抓取时间",
            RESEARCH_EVIDENCE_SHEET,
        ),
    ]
    for label, value, target in links:
        _style(ws.cell(row, 1, label), fill=GREY, bold=True)
        cell = ws.cell(row, 2, value)
        _style(cell)
        cell.hyperlink = f"#'{target}'!A1"
        cell.font = Font(
            name="Microsoft YaHei",
            size=11,
            bold=True,
            color=BLUE,
            underline="single",
        )
        row += 1


def _research_reports_sheet(wb: Workbook, batch: M2ResearchReportBatch) -> None:
    ws = wb.create_sheet(RESEARCH_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "公司",
        "报告ID",
        "主通道",
        "通道结论",
        "总结论",
        "研究层级",
        "数据",
        "研究/否决结论",
        "正向证据",
        "反证",
        "缺失证据",
        "下一触发点",
    ]
    _widths(ws, [11, 16, 28, 17, 34, 14, 12, 12, 72, 48, 48, 48, 48])
    _title(
        ws,
        "AC8 实质研究与通道否决",
        (
            f"policy={batch.policy_version} | action={batch.action} | "
            f"machine={batch.machine_status} | acceptance={batch.acceptance_status}"
        ),
        len(columns),
    )
    row = _header(ws, 4, columns)
    for report in batch.reports:
        channel_verdicts = "；".join(
            f"{CHANNEL_LABELS.get(channel, channel)}="
            f"{VERDICT_LABELS.get(verdict, verdict)}"
            for channel, verdict in report.channel_verdicts.items()
        )
        fill = VERDICT_FILLS.get(report.verdict, "FFFFFF")
        values = [
            report.symbol,
            report.name,
            report.report_id,
            CHANNEL_LABELS.get(report.primary_channel, report.primary_channel),
            channel_verdicts,
            VERDICT_LABELS.get(report.verdict, report.verdict),
            report.candidate_class,
            report.data_status,
            report.conclusion,
            "\n".join(report.positives),
            "\n".join(report.counter_evidence),
            "\n".join(report.missing_evidence),
            "\n".join(report.next_events),
        ]
        for column, value in enumerate(values, 1):
            cell = ws.cell(row, column, value)
            _style(cell, fill=fill if column == 6 else "FFFFFF")
            if column == 1:
                cell.font = Font(
                    name="Microsoft YaHei",
                    size=11,
                    bold=True,
                    color=INK,
                )
        ws.row_dimensions[row].height = max(
            72,
            max(len(value.splitlines()) for value in values[8:]) * 16,
        )
        row += 1


def _research_evidence_sheet(wb: Workbook, batch: M2ResearchReportBatch) -> None:
    ws = wb.create_sheet(RESEARCH_EVIDENCE_SHEET)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"
    columns = [
        "证券代码",
        "字段",
        "报告期",
        "值",
        "单位",
        "校验状态",
        "来源",
        "来源URL",
        "原件SHA-256",
        "发布时间",
        "抓取时间",
    ]
    _widths(ws, [11, 20, 15, 18, 13, 12, 32, 58, 64, 22, 25])
    _title(
        ws,
        "研究证据追溯",
        "每条证据保留来源、URL、原件 Hash 与可用时间；不得把研究结论当成交易指令。",
        len(columns),
    )
    row = _header(ws, 4, columns)
    for report in batch.reports:
        for evidence in report.evidence:
            values = [
                report.symbol,
                evidence.field_name,
                evidence.period_label,
                evidence.value,
                evidence.unit,
                evidence.validation_status,
                evidence.source_name,
                evidence.source_url,
                evidence.source_sha256 or "",
                evidence.published_at or "",
                evidence.fetched_at or "",
            ]
            for column, value in enumerate(values, 1):
                cell = ws.cell(row, column, value)
                _style(cell)
            if evidence.source_url.startswith(("http://", "https://")):
                url_cell = ws.cell(row, 8, evidence.source_url)
                url_cell.hyperlink = evidence.source_url
                url_cell.font = Font(
                    name="Microsoft YaHei",
                    size=11,
                    color=BLUE,
                    underline="single",
                )
            row += 1


def append_research_reports(
    wb: Workbook,
    batch: M2ResearchReportBatch,
) -> dict[str, Any]:
    if batch.action != ACTION_NO_ORDER:
        raise ValueError("M2 research workbook requires action=no_order")
    if batch.machine_status != "MACHINE_CHECKS_PASS":
        raise ValueError("M2 research reports have not passed machine checks")
    _research_summary_links(wb, batch)
    _research_reports_sheet(wb, batch)
    _research_evidence_sheet(wb, batch)
    substantive = batch.substantive_reports()
    return {
        "report_count": len(batch.reports),
        "substantive_report_count": len(substantive),
        "substantive_channels": list(batch.substantive_channels()),
        "insufficient_evidence_count": sum(
            report.verdict == VERDICT_INSUFFICIENT for report in batch.reports
        ),
        "rejected_count": sum(
            report.verdict == VERDICT_REJECTED for report in batch.reports
        ),
        "pending_deep_research_count": sum(
            report.verdict == VERDICT_PENDING for report in batch.reports
        ),
    }


def build_discovery_workbook(
    receipt: DiscoveryRunReceipt,
    policy: M2ScreeningPolicy,
) -> Workbook:
    if receipt.action != ACTION_NO_ORDER:
        raise ValueError("M2 workbook cannot consume a non-no_order receipt")
    wb = Workbook()
    wb.remove(wb.active)
    _overview(wb, receipt, policy)
    _candidate_sheet(
        wb,
        POOL_SHEET,
        "全部通道候选；仅进入深研队列，不代表便宜或值得买入。",
        tuple(
            candidate
            for channel in (CHANNEL_QUALITY, CHANNEL_DIVIDEND, CHANNEL_VALUE, CHANNEL_CYCLICAL)
            for candidate in receipt.channel_results[channel].candidates
        ),
        include_channel=True,
    )
    _candidate_sheet(wb, QUALITY_SHEET, "Quality 候选", receipt.channel_results[CHANNEL_QUALITY].candidates, include_channel=False)
    _candidate_sheet(wb, DIVIDEND_SHEET, "Dividend / Cash Return 候选", receipt.channel_results[CHANNEL_DIVIDEND].candidates, include_channel=False)
    _candidate_sheet(wb, VALUE_SHEET, "Value 候选", receipt.channel_results[CHANNEL_VALUE].candidates, include_channel=False)
    _candidate_sheet(wb, CYCLICAL_SHEET, "Cyclical 候选", receipt.channel_results[CHANNEL_CYCLICAL].candidates, include_channel=False)
    _health(wb, receipt)
    _excluded(wb, receipt)
    _legacy(wb, receipt)
    _evidence(wb, receipt)
    _coverage(wb, receipt)
    wb.active = 0
    return wb


def write_discovery_workbook(
    receipt: DiscoveryRunReceipt,
    policy: M2ScreeningPolicy,
    *,
    output: Path,
    root: Path,
) -> dict[str, Any]:
    output = output.resolve()
    if not output.is_relative_to(root.resolve()):
        raise ValueError("M2 workbook output escapes project root")
    if output.exists():
        raise ValueError(f"M2 workbook output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = build_discovery_workbook(receipt, policy)
    workbook.save(output)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return {
        "workbook_path": str(output.relative_to(root)),
        "workbook_sha256": digest,
        "action": ACTION_NO_ORDER,
    }
