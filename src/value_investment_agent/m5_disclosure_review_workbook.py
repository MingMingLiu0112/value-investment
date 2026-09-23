"""Editable intake workbook for the real M5 disclosure review queue.

The workbook is an evidence-pinned input surface. It pre-fills queue metadata
and candidate provenance, but every materiality decision and explanation cell
starts blank. Saving it is still a presentation artifact, not a verdict.
"""
from __future__ import annotations

from datetime import date, datetime, time
import hashlib
from pathlib import Path
from typing import Any, Mapping

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_DUPLICATE,
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    DECISION_SUPPORTING,
)
from .m5_disclosure_queue import (
    ACTION_NO_ORDER,
    SOURCE_ARCHIVED,
    SOURCE_NAME_CNINFO,
    DisclosureReviewQueue,
)
from .m5_disclosure_review import (
    CN_TZ,
    DISCLOSURE_REVIEW_INTAKE_SCHEMA,
    RECOMMENDED_ARTIFACT_TAGS,
    RECOMMENDED_DOMAIN_TAGS,
    DisclosureReviewDecisionInput,
    DisclosureReviewIntake,
    disclosure_queue_sha256,
)


OVERVIEW_SHEET = "00_总览"
INPUT_SHEET = "01_人工判定"
GUIDE_SHEET = "02_判定说明"
BOUNDARY_SHEET = "03_边界"

QUEUE_ID_LABEL = "队列ID"
QUEUE_HASH_LABEL = "队列 SHA-256"
REVIEWED_AT_LABEL = "审核时间（北京时间）"
ACTION_LABEL = "动作"

COLUMNS = [
    "证券代码",
    "公告ID",
    "发布时间",
    "公告标题",
    "标题规则",
    "PDF SHA-256",
    "材料性判定",
    "受影响领域",
    "受影响事实字段",
    "受影响假设",
    "受影响制品",
    "复核说明",
    "填写提示",
]
REVIEWED_AT_COLUMN = 2
HEADER_ROW = 4
DATA_START_ROW = 5

INK = "24312D"
GREEN = "18755D"
BLUE = "245D83"
GREY = "EFF3F1"
AMBER = "FFF1D6"
_RULE_LABELS = {
    "financial_statement": "财务报告",
    "dividend": "利润分配",
    "buyback": "股份回购",
    "capital_structure": "资本结构",
    "asset_impairment": "资产减值",
    "accounting_policy": "会计政策",
    "guarantee": "对外担保",
    "operating_data": "经营数据",
    "governance": "治理/流程",
    "investor_relations": "投资者关系",
    "routine": "例行事项",
    "unknown": "待判断",
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


def _write_row(ws, row: int, values: list[Any], fill: str = "FFFFFF") -> None:
    for column, value in enumerate(values, 1):
        _style(ws.cell(row, column, value), fill=fill)


def _pdf_hash(item) -> str:
    for ref in item.evidence_refs:
        if ref.get("source_status") == SOURCE_ARCHIVED and ref.get("sha256"):
            return str(ref["sha256"])
    return ""


def _overview(
    wb: Workbook,
    queue: DisclosureReviewQueue,
    names: Mapping[str, str],
) -> None:
    sheet = wb.create_sheet(OVERVIEW_SHEET)
    sheet.sheet_view.showGridLines = False
    columns = ["项目", "值", "说明"]
    _widths(sheet, [24, 42, 72])
    _title(
        sheet,
        "M5 真实披露人工复核回填",
        "只回填人工判定；所有结论和复核说明均不得由脚本替填。",
        len(columns),
    )
    row = _header(sheet, 4, columns)
    pending = len(queue.pending_candidates)
    rows = [
        (
            QUEUE_ID_LABEL,
            queue.queue_id,
            "本表绑定的唯一真实 CNINFO 队列。",
        ),
        (
            QUEUE_HASH_LABEL,
            disclosure_queue_sha256(queue),
            "队列任何变化都会让本表失效。",
        ),
        (
            "来源",
            SOURCE_NAME_CNINFO,
            "法定披露聚合来源，不产生投资结论。",
        ),
        (
            "扫描区间",
            f"{queue.scan_from} 至 {queue.scan_to}",
            "仅复核该窗口内公告。",
        ),
        (
            "抓取时间",
            queue.retrieved_at.isoformat(),
            "所有原件均不得晚于该时间。",
        ),
        (
            "待人工复核",
            pending,
            "每一条都必须逐项填写判定和说明。",
        ),
        (
            "解析器",
            queue.parser_version,
            "标题规则版本固定。",
        ),
        (
            ACTION_LABEL,
            queue.action,
            "始终不生成订单或交易意图。",
        ),
    ]
    for item in rows:
        _write_row(sheet, row, list(item))
        row += 1
    _style(sheet.cell(row, 1, REVIEWED_AT_LABEL), fill=AMBER, bold=True)
    _style(sheet.cell(row, REVIEWED_AT_COLUMN, ""), fill=AMBER)
    _style(
        sheet.cell(row, 3, "格式：2026-09-24 18:30；只支持日期或北京时间日期时间。"),
        fill=AMBER,
    )


def _input(
    wb: Workbook,
    queue: DisclosureReviewQueue,
    names: Mapping[str, str],
) -> None:
    sheet = wb.create_sheet(INPUT_SHEET)
    sheet.sheet_view.showGridLines = False
    sheet.freeze_panes = "A5"
    _widths(sheet, [10, 13, 20, 56, 12, 66, 24, 22, 22, 22, 22, 52, 30])
    _title(
        sheet,
        "材料性判定录入",
        "判定列为空表示尚未复核；脚本会失败关闭，不会默认静默。",
        len(COLUMNS),
    )
    row = _header(sheet, HEADER_ROW, COLUMNS)
    ordered = sorted(
        (
            (scan.symbol, item)
            for scan in queue.scans
            for item in scan.validity_material_candidates
        ),
        key=lambda pair: (pair[1].published_at, pair[1].announcement_id),
    )
    for symbol, item in ordered:
        _write_row(
            sheet,
            row,
            [
                symbol,
                item.announcement_id,
                item.published_at.astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M"),
                item.title,
                _RULE_LABELS.get(item.rule_kind, item.rule_kind),
                _pdf_hash(item),
                "",
                "",
                "",
                "",
                "",
                "",
                "判定与复核说明必须由人工填写。",
            ],
        )
        row += 1
    last_data_row = row - 1
    if last_data_row < DATA_START_ROW:
        _write_row(
            sheet,
            DATA_START_ROW,
            ["无待复核公告"] + [""] * (len(COLUMNS) - 1),
            fill=GREY,
        )
        last_data_row = DATA_START_ROW
    validation = DataValidation(
        type="list",
        formula1=(
            "\"NOT_MATERIAL,MATERIAL_SUPPORTING_EVIDENCE,"
            "MATERIAL_ALREADY_INCORPORATED,MATERIAL_REQUIRES_RECALCULATION,"
            "MATERIAL_RISK_MONITOR,DUPLICATE_OR_DERIVED,REQUIRES_DECOMPOSITION\""
        ),
        allow_blank=True,
        showDropDown=False,
    )
    validation.error = "只能选择列出的材料性判定。"
    validation.errorTitle = "判定值无效"
    validation.showErrorMessage = True
    sheet.add_data_validation(validation)
    validation.add(f"G{DATA_START_ROW}:G{last_data_row}")


def _guide(wb: Workbook) -> None:
    sheet = wb.create_sheet(GUIDE_SHEET)
    sheet.sheet_view.showGridLines = False
    columns = ["项目", "内容", "要求"]
    _widths(sheet, [30, 42, 62])
    _title(
        sheet,
        "人工判定说明",
        "材料性判定是人工研究结论；标题规则只负责把事项放入待复核队列。",
        len(columns),
    )
    row = _header(sheet, HEADER_ROW, columns)
    rows = [
        ("非重大", DECISION_NOT_MATERIAL, "说明公告不影响当前事实、模型或论点。"),
        ("支持证据", DECISION_SUPPORTING, "说明它与现有研究一致但不要求重算。"),
        ("已纳入", DECISION_ALREADY_INCORPORATED, "说明事实已在当前版本中体现。"),
        ("需重算", DECISION_REQUIRES_RECALCULATION, "必须至少填写一个受影响领域或制品。"),
        ("风险监控", DECISION_RISK_MONITOR, "只进入后续决策复核，不把模型直接标过期。"),
        ("重复/衍生", DECISION_DUPLICATE, "可填写 supersedes_event_id 或 cluster id。"),
        ("需拆分", DECISION_REQUIRES_DECOMPOSITION, "只触发决策复核和当前状态，不直接改估值。"),
        ("复核说明", "必填", "所有判定都必须保留至少一行人工解释。"),
    ]
    for item in rows:
        _write_row(sheet, row, list(item))
        row += 1
    row += 1
    _style(sheet.cell(row, 1, "可填写领域标签"), fill=GREY, bold=True)
    _style(sheet.cell(row, 2, "、".join(RECOMMENDED_DOMAIN_TAGS)), fill=GREY)
    _style(sheet.cell(row, 3, "多个值用逗号、分号或换行分隔。"), fill=GREY)
    row += 1
    _style(sheet.cell(row, 1, "可填写制品标签"), fill=GREY, bold=True)
    _style(sheet.cell(row, 2, "、".join(RECOMMENDED_ARTIFACT_TAGS)), fill=GREY)
    _style(sheet.cell(row, 3, "用于把重算精确限制到受影响的研究制品。"), fill=GREY)


def _boundaries(wb: Workbook) -> None:
    sheet = wb.create_sheet(BOUNDARY_SHEET)
    sheet.sheet_view.showGridLines = False
    columns = ["边界", "状态", "说明"]
    _widths(sheet, [26, 18, 72])
    _title(
        sheet,
        "输入与运行边界",
        "本回填表只转换人工判定，不自动判定、不创建事件、不通知、不下单。",
        len(columns),
    )
    row = _header(sheet, HEADER_ROW, columns)
    rows = [
        ("判定来源", "人工必填", "脚本不提供默认结论，空值会使应用失败。"),
        ("队列指纹", "SHA-256", "队列 JSON 改变后，本回填表不能直接重放。"),
        ("PDF 原件", "SHA-256", "每条重算都绑定归档 PDF Hash，缺件不降级。"),
        ("审核时间", "北京时间", "审核不得早于公告发布时间。"),
        ("事件创建", "回填时不创建", "回填后由既有 M5 材料性桥显式消费。"),
        ("生产调度", "未启用", "不创建常驻服务或计划任务。"),
        ("通知投递", "未启用", "不发送真实提醒。"),
        ("数据库", "未连接", "不写生产 PostgreSQL。"),
        ("动作", ACTION_NO_ORDER, "所有交易决策仍由用户完成。"),
    ]
    for item in rows:
        _write_row(sheet, row, list(item))
        row += 1


def build_m5_disclosure_review_workbook(
    queue: DisclosureReviewQueue,
    *,
    security_names: Mapping[str, str] | None = None,
) -> Workbook:
    names = dict(security_names or {})
    wb = Workbook()
    wb.remove(wb.active)
    _overview(wb, queue, names)
    _input(wb, queue, names)
    _guide(wb)
    _boundaries(wb)
    return wb


def write_m5_disclosure_review_workbook(
    queue: DisclosureReviewQueue,
    *,
    output: Path,
    root: Path,
    security_names: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    output = output.resolve()
    root = root.resolve()
    if not output.is_relative_to(root):
        raise ValueError("Disclosure review workbook must remain inside the project root")
    if output.exists():
        raise ValueError("Disclosure review workbook output already exists")
    wb = build_m5_disclosure_review_workbook(
        queue,
        security_names=security_names,
    )
    wb.save(output)
    return {
        "workbook_path": str(output),
        "workbook_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "sheet_count": len(wb.sheetnames),
        "pending_candidate_count": len(queue.pending_candidates),
        "queue_id": queue.queue_id,
        "queue_sha256": disclosure_queue_sha256(queue),
        "action": queue.action,
    }


def _metadata_value(ws, label: str) -> str:
    for row in ws.iter_rows(min_col=1, max_col=2):
        first = row[0].value
        if isinstance(first, str) and first.strip() == label:
            value = row[1].value
            if value is None or str(value).strip() == "":
                raise ValueError(f"Workbook metadata is missing: {label}")
            return str(value).strip()
    raise ValueError(f"Workbook metadata label not found: {label}")


def _parse_reviewed_at(value: str) -> datetime:
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed_date = date.fromisoformat(text)
        parsed = datetime.combine(parsed_date, time(12, 0, tzinfo=CN_TZ))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CN_TZ)
    return parsed.astimezone(CN_TZ)


def _workbook_tags(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    text = str(value).strip()
    if not text:
        return ()
    parts = tuple(
        item.strip()
        for item in text.replace("，", ",").replace("；", ",").replace(";", ",").split(",")
        if item.strip()
    )
    if len(parts) != len(set(parts)):
        raise ValueError("Workbook affected-value tags contain duplicates")
    return parts


def read_m5_disclosure_review_workbook(
    workbook_path: Path,
    queue: DisclosureReviewQueue,
) -> DisclosureReviewIntake:
    workbook_path = workbook_path.resolve()
    wb = load_workbook(workbook_path, data_only=False, read_only=True)
    if INPUT_SHEET not in wb.sheetnames or OVERVIEW_SHEET not in wb.sheetnames:
        raise ValueError("Workbook is not an M5 disclosure review intake")
    overview = wb[OVERVIEW_SHEET]
    queue_id = _metadata_value(overview, QUEUE_ID_LABEL)
    queue_sha256 = _metadata_value(overview, QUEUE_HASH_LABEL)
    if queue_id != queue.queue_id:
        raise ValueError("Workbook queue id does not match the loaded queue")
    if queue_sha256 != disclosure_queue_sha256(queue):
        raise ValueError("Workbook queue hash does not match the loaded queue")
    reviewed_at = _parse_reviewed_at(
        _metadata_value(overview, REVIEWED_AT_LABEL)
    )

    pending = {
        (scan.symbol, item.announcement_id): item
        for scan in queue.scans
        for item in scan.validity_material_candidates
    }
    missing_decision: list[str] = []
    missing_notes: list[str] = []
    raw_rows: list[tuple[Any, ...]] = []
    input_sheet = wb[INPUT_SHEET]
    for row_values in input_sheet.iter_rows(
        min_row=DATA_START_ROW,
        values_only=True,
    ):
        if row_values[1] is None or str(row_values[1]).strip() == "":
            continue
        symbol = str(row_values[0]).strip()
        announcement_id = str(row_values[1]).strip()
        key = (symbol, announcement_id)
        if key not in pending:
            raise ValueError(f"Workbook contains a non-candidate decision row: {key}")
        decision = str(row_values[6] or "").strip()
        notes = str(row_values[11] or "").strip()
        if not decision:
            missing_decision.append(announcement_id)
        if not notes:
            missing_notes.append(announcement_id)
        raw_rows.append(row_values)
    supplied = {
        (str(row[0]).strip(), str(row[1]).strip())
        for row in raw_rows
    }
    if supplied != set(pending):
        missing = sorted(key[1] for key in set(pending) - supplied)
        extra = sorted(key[1] for key in supplied - set(pending))
        raise ValueError(
            f"Workbook coverage mismatch; missing={missing}, extra={extra}"
        )
    if missing_decision:
        raise ValueError(
            "Materiality decision is missing for announcement ids: "
            + ", ".join(sorted(missing_decision))
        )
    if missing_notes:
        raise ValueError(
            "Review note is missing for announcement ids: "
            + ", ".join(sorted(missing_notes))
        )
    decisions = tuple(
        DisclosureReviewDecisionInput(
            announcement_id=str(row_values[1]).strip(),
            symbol=str(row_values[0]).strip(),
            human_decision=str(row_values[6]).strip(),
            affected_domains=_workbook_tags(row_values[7]),
            affected_fact_fields=_workbook_tags(row_values[8]),
            affected_assumptions=_workbook_tags(row_values[9]),
            affected_artifacts=_workbook_tags(row_values[10]),
            review_notes=(str(row_values[11]).strip(),),
        )
        for row_values in raw_rows
    )
    return DisclosureReviewIntake(
        schema_version=DISCLOSURE_REVIEW_INTAKE_SCHEMA,
        queue_id=queue_id,
        queue_sha256=queue_sha256,
        reviewed_at=reviewed_at,
        decisions=decisions,
        action=ACTION_NO_ORDER,
    )
