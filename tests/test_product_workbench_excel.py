from __future__ import annotations

from collections import deque
from copy import copy
import hashlib
import json
from pathlib import Path
import re

from openpyxl import load_workbook
from openpyxl import Workbook
import pytest

from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_COMPANIES,
    SHEET_EVENTS,
    SHEET_OPPORTUNITIES,
    SHEET_PORTFOLIO,
    SHEET_SYSTEM_AUDIT,
    SHEET_TODAY,
    USER_SHEETS,
    WORKBOOK_SHEETS,
    build_product_workbench_workbook,
    apply_product_workbench_to_existing_workbook,
    write_product_workbench_candidate,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    ACTION_NO_ORDER,
    PRODUCT_WORKBENCH_SCHEMA_VERSION,
    EvidenceRecord,
    product_workbench_from_payload,
)
from value_investment_agent.presentation.read_models.m5_event_state_projection import (
    EventStateInput,
    project_m5_event_states,
)


ROOT = Path(__file__).resolve().parents[1]
SHA = "b" * 64


def _assessment(
    *,
    status: str,
    available: bool,
    value_text: str | None = None,
    reason: str | None = None,
    needed: str | None = None,
) -> dict:
    return {
        "status": status,
        "available": available,
        "value_text": value_text,
        "unavailable_reason": reason,
        "needed_evidence": needed,
        "evidence_refs": ["evidence-1"],
    }


def _payload() -> dict:
    sections = [
        {
            "key": key,
            "status": "PARTIAL",
            "summary": f"{key} 的上游结论。",
            "evidence_refs": ["evidence-1"],
        }
        for key in (
            "business_quality",
            "financial_quality",
            "capital_allocation",
            "valuation",
            "dividend",
            "risks_counterevidence",
        )
    ]
    scenarios = [
        {
            "key": key,
            "assessment": _assessment(
                status="NOT_READY",
                available=False,
                reason=f"{key} 情景输入未复核。",
                needed="同口径情景假设。",
            ),
        }
        for key in ("bear", "base", "bull")
    ]
    return {
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": "2026-09-26T03:00:00+00:00",
        "as_of": "2026-09-25",
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": 1},
        "system_health": {
            "status": "EVIDENCE_INSUFFICIENT",
            "message": "部分输入仍待人工复核。",
        },
        "stages": {
            "m2": {"status": "DONE", "detail": "初筛已人工通过。"},
            "m3": {"status": "PARTIAL", "detail": "研究资料仍在补齐。"},
            "m4": {
                "status": "PARKED_WAITING_R2_NONBLOCKING",
                "detail": "个性化组合分析已暂停，不影响公共研究。",
            },
            "m5": {"status": "PENDING_HUMAN_REVIEW", "detail": "有事件待复核。"},
            "m6": {
                "status": "PREFLIGHT_DONE",
                "detail": "真实监控尚未开始。",
            },
        },
        "audit": {
            "evidence": [
                {
                    "evidence_id": "evidence-1",
                    "title": "固定测试证据",
                    "artifact_type": "research_payload",
                    "path": "runtime/product-fixture.json",
                    "sha256": SHA,
                    "available_at": "2026-09-25",
                    "action": ACTION_NO_ORDER,
                }
            ]
        },
        "today_items": [
            {
                "category": "PRICE_WATCH",
                "company": "测试公司",
                "symbol": "600000",
                "what_happened": "价格进入关注范围。",
                "why_it_matters": "需要复核上游研究结论。",
                "current_status": "等待人工复核。",
                "next_step": "核对价格与研究时点。",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "opportunities": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "why_now": "价格状态已变化。",
                "research_status": "WAIT_FOR_PRICE",
                "valuation_status": "NOT_READY",
                "dividend_status": "INSUFFICIENT_EVIDENCE",
                "price_status": "IN_WATCH_RANGE",
                "main_risk": "价格变化不等于投资结论。",
                "next_trigger": "等待人工复核。",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "companies": [
            {
                "symbol": "600000",
                "company_name": "测试公司",
                "research_status": "PARTIAL",
                "price": _assessment(
                    status="AVAILABLE",
                    available=True,
                    value_text="上游价格 10 元",
                ),
                "valuation": _assessment(
                    status="NOT_READY",
                    available=False,
                    reason="估值输入尚未复核。",
                    needed="同一时点估值输入。",
                ),
                "margin_of_safety": _assessment(
                    status="NOT_READY",
                    available=False,
                    reason="估值输入尚未复核。",
                    needed="同一时点估值输入。",
                ),
                "dividend": _assessment(
                    status="INSUFFICIENT_EVIDENCE",
                    available=False,
                    reason="股息证据不足。",
                    needed="多财年分配与现金流证据。",
                ),
                "sections": sections,
                "scenarios": scenarios,
                "latest_change": "价格进入关注范围。",
                "next_trigger": "等待人工复核。",
                "original_thesis": "高质量经营与现金回报。",
                "thesis_change": "UNKNOWN",
                "evidence_refs": ["evidence-1"],
            }
        ],
        "portfolio": {
            "real_data_available": False,
            "status": "PARKED_WAITING_R2_NONBLOCKING",
            "connection_hint": "个性化组合分析已暂停，不影响公共研究。",
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [
            {
                "event_id": "event-1",
                "event_type": "MATERIAL_REQUIRES_RECALCULATION",
                "company_name": "测试公司",
                "what_happened": "发生需要复核的重大事项。",
                "impact_area": "投资逻辑。",
                "current_conclusion": "等待人工判断。",
                "research_action": "REOPEN_RESEARCH",
                "next_step": "补充事件后证据。",
                "evidence_refs": ["evidence-1"],
            }
        ],
    }


def _model():
    return product_workbench_from_payload(_payload())


def _all_text(workbook) -> str:
    values: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    values.append(str(cell.value))
    return "\n".join(values)


def test_retained_case_reopen_conditions_are_readable_without_changing_scope():
    from value_investment_agent.presentation.excel.product_workbench import _user_text as display_text
    original = ('000333-share-denominator-2026-06-30：'
        'A new official date-matched disclosure enumerates issued A/H shares and all treasury-share uses at 2026-06-30.'
        '；已查材料：midea_2026h1_equity_change_report')
    rendered = display_text(original)
    assert '2026-06-30' in rendered and 'A/H' in rendered
    assert '全部库存股用途' in rendered and '后续股数替代' in rendered
    assert 'midea_' not in rendered and '000333-share-' not in rendered
    assert '系统与审计页' in rendered
    assert '最终合并范围' in display_text('New official evidence bridges the final consolidation perimeter, attribution, tax/NCI and financing, with enough comparable history to calibrate the cycle.')


def _user_text(workbook) -> str:
    values: list[str] = []
    for title in USER_SHEETS:
        sheet = workbook[title]
        for row in sheet.iter_rows():
            for cell in row:
                if cell.value is not None:
                    values.append(str(cell.value))
    return "\n".join(values)


def _link_sheet(cell) -> str | None:
    hyperlink = cell.hyperlink
    if hyperlink is None:
        return None
    raw = hyperlink.location or hyperlink.target or ""
    match = re.match(r"^#'?([^'!]+)'?!", raw)
    return match.group(1) if match else None


def _click_distance(workbook, start: str, target: str) -> int | None:
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        title, distance = queue.popleft()
        if title == target:
            return distance
        sheet = workbook[title]
        for row in sheet.iter_rows():
            for cell in row:
                linked = _link_sheet(cell)
                if linked and linked not in seen and linked in workbook.sheetnames:
                    seen.add(linked)
                    queue.append((linked, distance + 1))
    return None


def _empty_payload() -> dict:
    payload = _payload()
    payload["overview"]["pending_count"] = 0
    payload["today_items"] = []
    payload["opportunities"] = []
    payload["companies"] = []
    payload["events"] = []
    payload["audit"]["evidence"] = []
    payload["stages"] = {
        key: {"status": "WAIT", "detail": f"{key} 等待输入。"}
        for key in ("m2", "m3", "m4", "m5", "m6")
    }
    payload["portfolio"] = {
        "real_data_available": False,
        "status": "NOT_STARTED",
        "connection_hint": "尚未接入真实组合。",
        "summary": [],
        "positions": [],
        "action": ACTION_NO_ORDER,
    }
    return payload


def test_candidate_has_five_user_sheets_and_secondary_audit() -> None:
    workbook = build_product_workbench_workbook(_model())

    assert tuple(workbook.sheetnames) == WORKBOOK_SHEETS
    assert tuple(workbook.sheetnames[:len(USER_SHEETS)]) == USER_SHEETS
    assert workbook.sheetnames[-1] == SHEET_SYSTEM_AUDIT
    assert workbook[USER_SHEETS[0]].sheet_view.showGridLines is False


def test_product_surface_replaces_only_its_own_sheets_and_preserves_legacy_order() -> None:
    workbook = Workbook()
    legacy = workbook.active
    legacy.title = "人工持仓"
    legacy["A1"] = "用户输入"
    legacy["B2"] = "=1+1"
    frozen = workbook.create_sheet("冻结证据")
    frozen["A1"] = "immutable"
    frozen.sheet_state = "hidden"

    sheets = apply_product_workbench_to_existing_workbook(workbook, _model())

    assert sheets[:len(WORKBOOK_SHEETS)] == WORKBOOK_SHEETS
    assert sheets[len(WORKBOOK_SHEETS):] == ("人工持仓", "冻结证据")
    assert workbook["人工持仓"]["A1"].value == "用户输入"
    assert workbook["人工持仓"]["B2"].value == "=1+1"
    assert workbook["冻结证据"]["A1"].value == "immutable"
    assert workbook["冻结证据"].sheet_state == "hidden"


def test_company_detail_is_reachable_within_three_clicks() -> None:
    workbook = build_product_workbench_workbook(_model())

    distance = _click_distance(workbook, SHEET_TODAY, SHEET_COMPANIES)

    assert distance is not None
    assert distance <= 3
    assert _click_distance(workbook, SHEET_OPPORTUNITIES, SHEET_COMPANIES) == 1


def test_user_pages_hide_internal_codes_hashes_and_execution_semantics() -> None:
    workbook = build_product_workbench_workbook(_model())
    text = _user_text(workbook)

    for hidden in (
        "PENDING_HUMAN_REVIEW",
        "PENDING_USER_PRIVATE_INPUT",
        "PREFLIGHT_DONE",
        "SHA-256",
        SHA,
        "target_weight",
        "position_size",
        "trade_approved",
        "action=no_order",
        "BLOCKED",
        "NOT_READY",
        "UNKNOWN",
        "建议买入",
        "目标仓位",
        "下单",
    ):
        assert hidden not in text
    opportunity_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_OPPORTUNITIES].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "研究完成，等待价格" in opportunity_text


def test_user_pages_translate_internal_provenance_and_status_codes() -> None:
    payload = _payload()
    payload["companies"][0]["decision_review"] = [
        {
            "label": "研究限制",
            "value": (
                "RESEARCH_NOT_READY_FOR_PRICE_ASSESSMENT；估值批准为 false；"
                "PIT；issuer-specific beta evidence missing: generic beta=1 assumption used"
            ),
        },
        {
            "label": "待复核公告 1",
            "value": (
                "披露时间：2026-09-01；原件：https://example.test/a.pdf；"
                f"SHA256={SHA}；页数=1；文本状态=TEXT_EXTRACTED_NOT_SEMANTICALLY_VERIFIED"
            ),
        },
        {
            "label": "股息记录 FY2025",
            "value": f"每股1.00 CNY；普通/特别分类：unknown。 原件：runtime/private/a.pdf；SHA256={SHA}",
        },
    ]

    workbook = build_product_workbench_workbook(product_workbench_from_payload(payload))
    text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_COMPANIES].iter_rows()
        for cell in row
        if cell.value is not None
    )

    for hidden in ("RESEARCH_NOT_READY_FOR_PRICE_ASSESSMENT", "估值批准为 false", "PIT", "SHA256", SHA, "runtime/", "unknown"):
        assert hidden not in text
    assert "研究结果暂不支持价格评估" in text
    assert "估值尚未获得正式批准" in text
    assert "严格历史时点" in text
    assert "原件及哈希见系统与审计页" in text
    assert "文本已提取，尚未做语义核验" not in text


def test_opportunity_card_header_has_visible_height() -> None:
    workbook = build_product_workbench_workbook(_model())
    sheet = workbook[SHEET_OPPORTUNITIES]

    assert sheet["A4"].value == "测试公司 / 600000"
    assert sheet.row_dimensions[4].height == 28


def test_absent_portfolio_renders_only_unconnected_state() -> None:
    workbook = build_product_workbench_workbook(_model())
    sheet = workbook[SHEET_PORTFOLIO]
    text = "\n".join(
        str(cell.value)
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert "尚未接入真实组合" in text
    assert "个性化组合分析已暂停" in text
    assert "查看接入说明" not in text
    assert not any(cell.hyperlink for row in sheet.iter_rows() for cell in row)
    for simulated_metric in (
        "总资产",
        "股票仓位",
        "现金",
        "预计年股息",
        "正常化年股息",
    ):
        assert simulated_metric not in text


def test_evidence_link_reaches_audit_and_audit_contains_hash() -> None:
    workbook = build_product_workbench_workbook(_model())
    evidence_links = [
        cell
        for row in workbook[SHEET_OPPORTUNITIES].iter_rows()
        for cell in row
        if cell.value == "查看证据 (1)"
    ]

    assert evidence_links
    assert _link_sheet(evidence_links[0]) == SHEET_SYSTEM_AUDIT
    audit_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_SYSTEM_AUDIT].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert SHA in audit_text
    assert "runtime/product-fixture.json" in audit_text
    assert "no_order" in audit_text


def test_evidence_links_target_rendered_rows_when_stage_summary_count_varies() -> None:
    payload = _payload()
    payload["audit"]["evidence"].append(
        {
            **payload["audit"]["evidence"][0],
            "evidence_id": "evidence-2",
            "title": "第二条测试证据",
        }
    )
    payload["opportunities"][0]["evidence_refs"] = ["evidence-2"]
    model = product_workbench_from_payload(payload)

    for stage_count in (1, 3, 5):
        model_variant = copy(model)
        object.__setattr__(
            model_variant,
            "stage_summaries",
            model.stage_summaries[:stage_count],
        )
        workbook = build_product_workbench_workbook(
            model_variant
        )
        evidence_link = next(
            cell
            for row in workbook[SHEET_OPPORTUNITIES].iter_rows()
            for cell in row
            if cell.value == "查看证据 (1)"
        )
        location = evidence_link.hyperlink.location or evidence_link.hyperlink.target
        row_number = int(re.search(r"!A(\d+)$", location).group(1))

        assert workbook[SHEET_SYSTEM_AUDIT].cell(row_number, 1).value == "evidence-2"


def test_multi_source_event_evidence_opens_group_with_all_non_adjacent_sources() -> None:
    payload = _payload()
    first_url = "https://example.test/evidence-1.pdf"
    middle_url = "https://example.test/evidence-2.pdf"
    last_url = "https://example.test/evidence-3.pdf"
    first_hash = "a" * 64
    middle_hash = "c" * 64
    last_hash = "d" * 64
    payload["audit"]["evidence"][0].update(
        sha256=first_hash,
        source_url=first_url,
    )
    for evidence_id, digest, url in (
        ("evidence-2", middle_hash, middle_url),
        ("evidence-3", last_hash, last_url),
    ):
        payload["audit"]["evidence"].append(
            {
                **payload["audit"]["evidence"][0],
                "evidence_id": evidence_id,
                "title": f"测试证据 {evidence_id}",
                "sha256": digest,
                "source_url": url,
            }
        )
    payload["events"][0]["evidence_refs"] = ["evidence-1", "evidence-3"]

    workbook = build_product_workbench_workbook(
        product_workbench_from_payload(payload)
    )
    event_link = next(
        cell
        for row in workbook[SHEET_EVENTS].iter_rows()
        for cell in row
        if cell.value == "打开证据组 (2)"
    )
    assert _link_sheet(event_link) == SHEET_SYSTEM_AUDIT
    group_location = event_link.hyperlink.location or event_link.hyperlink.target
    group_row = int(re.search(r"!A(\d+)$", group_location).group(1))

    audit = workbook[SHEET_SYSTEM_AUDIT]
    assert audit.cell(group_row, 1).value == "证据组 1 (2 项)"
    first_group_row = group_row + 2
    group_ids = {
        audit.cell(row, 1).value
        for row in (first_group_row, first_group_row + 1)
    }
    assert group_ids == {"evidence-1", "evidence-3"}
    assert audit.cell(first_group_row, 5).value == first_hash
    assert audit.cell(first_group_row + 1, 5).value == last_hash
    assert audit.cell(first_group_row, 6).hyperlink.target == first_url
    assert audit.cell(first_group_row + 1, 6).hyperlink.target == last_url
    assert audit.row_dimensions[first_group_row].height is not None
    assert audit.row_dimensions[first_group_row + 1].height is not None

    evidence_header_row = next(
        row for row in range(1, audit.max_row + 1)
        if audit.cell(row, 1).value == "证据ID"
    )
    assert audit.cell(evidence_header_row, 6).value == "最早可用时间（PIT保守口径）"
    assert audit.row_dimensions[evidence_header_row].height is not None

    source_rows = {
        audit.cell(row, 1).value: row
        for row in range(1, group_row)
        if audit.cell(row, 1).value in {"evidence-1", "evidence-2", "evidence-3"}
    }
    assert source_rows["evidence-3"] - source_rows["evidence-1"] == 2


def test_601088_projection_source_url_reaches_audit_title_hyperlink() -> None:
    source_url = "https://static.cninfo.com.cn/601088/shenhua-event.pdf"
    evidence = EvidenceRecord(
        evidence_id="shenhua-source",
        title="神华公告原件",
        artifact_type="cninfo_announcement",
        path="evidence/601088-event.pdf",
        sha256=SHA,
        source_url=source_url,
    )
    projection = project_m5_event_states((
        EventStateInput(
            state="material_risk_monitor",
            event_id="601088-risk",
            company_name="中国神华",
            what_happened="关联方资金风险需要持续跟踪。",
            impact_area="现金质量",
            evidence=(evidence,),
        ),
    ))
    projected = projection.as_payload()
    payload = _payload()
    payload["audit"]["evidence"].append(projected["audit_evidence"][0])
    payload["events"].extend(projected["events"])
    model = product_workbench_from_payload(payload)
    workbook = build_product_workbench_workbook(model)

    audit = workbook[SHEET_SYSTEM_AUDIT]
    evidence_row = next(
        row
        for row in range(1, audit.max_row + 1)
        if audit.cell(row, 1).value == "shenhua-source"
    )
    assert model.audit_evidence[-1].source_url == source_url
    assert audit.cell(evidence_row, 2).value == "神华公告原件"
    assert audit.cell(evidence_row, 2).hyperlink.target == source_url


def test_evidence_source_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="HTTPS URL"):
        EvidenceRecord(
            evidence_id="unsafe-source",
            title="不安全来源",
            artifact_type="test",
            path="evidence/test.pdf",
            sha256=SHA,
            source_url="http://example.test/evidence.pdf",
        )


def test_unavailable_assessment_has_reason_and_no_empty_numeric_placeholder() -> None:
    workbook = build_product_workbench_workbook(_model())
    company_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_COMPANIES].iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert "暂不可评估" in company_text
    assert "原因：估值输入尚未复核。" in company_text
    assert "需要：同一时点估值输入。" in company_text
    assert "0.00" not in company_text


def test_all_wait_empty_candidate_renders_legal_empty_states() -> None:
    model = product_workbench_from_payload(_empty_payload())
    workbook = build_product_workbench_workbook(model)

    assert tuple(workbook.sheetnames) == WORKBOOK_SHEETS
    today_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_TODAY].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "当前没有已分类的今日事项" in today_text
    assert "尚未接入真实组合" in today_text


def test_company_page_renders_optional_decision_review_explanation() -> None:
    payload = _payload()
    payload["companies"][0]["decision_review"] = [
        {"label": "模拟买入复核逻辑", "value": "研究完整后仍需人工决定。"},
        {"label": "模拟退出条件", "value": "核心假设被证伪时重新研究。"},
    ]

    workbook = build_product_workbench_workbook(product_workbench_from_payload(payload))
    company_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_COMPANIES].iter_rows()
        for cell in row
        if cell.value is not None
    )

    assert "决策复核" in company_text
    assert "模拟买入复核逻辑" in company_text
    assert "核心假设被证伪时重新研究。" in company_text


def test_manifest_is_no_order_and_does_not_touch_canonical_pointer(
    tmp_path: Path,
) -> None:
    pointer = ROOT / "config" / "current-trial-workbook.json"
    pointer_before = hashlib.sha256(pointer.read_bytes()).hexdigest()
    output = tmp_path / "m7-product-ux-candidate.xlsx"

    receipt = write_product_workbench_candidate(
        _model(),
        output=output,
        root=tmp_path,
    )

    assert output.exists()
    assert receipt["action"] == ACTION_NO_ORDER
    assert receipt["workbook_kind"] == "M7_PRODUCT_UX_CANDIDATE"
    assert receipt["final_user_acceptance"] == "NOT_PASSED"
    assert receipt["candidate_not_formal_workbook"] is True
    assert receipt["canonical_pointer_modified"] is False
    manifest_path = output.with_name(
        output.stem + ".m7-product-workbench-candidate-manifest.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["action"] == ACTION_NO_ORDER
    assert hashlib.sha256(pointer.read_bytes()).hexdigest() == pointer_before


def test_soft_wrapped_text_is_not_clipped_by_row_height() -> None:
    payload = _payload()
    long_text = "证据不足。" * 12
    payload["today_items"][0]["what_happened"] = long_text

    workbook = build_product_workbench_workbook(
        product_workbench_from_payload(payload)
    )
    sheet = workbook[SHEET_TODAY]
    target_row = None
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value == long_text:
                target_row = cell.row
    assert target_row is not None

    height = sheet.row_dimensions[target_row].height
    assert height is not None
    # 120 columns of CJK text inside a 28-wide column needs several lines.
    assert height >= 15 * 3 + 6


def test_every_row_is_tall_enough_for_its_own_wrapped_content() -> None:
    workbook = build_product_workbench_workbook(_model())

    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            texts = [str(cell.value) for cell in row if cell.value is not None]
            if not texts:
                continue
            largest = max(texts, key=lambda value: value.count("\n") + len(value))
            height = sheet.row_dimensions[row[0].row].height
            if height is None:
                continue
            assert height >= 15 * (largest.count("\n") + 1) + 6


def test_user_sheets_freeze_the_company_column_for_horizontal_scans() -> None:
    workbook = build_product_workbench_workbook(_model())

    for title in USER_SHEETS:
        assert workbook[title].freeze_panes == "B4"


def test_decision_process_is_navigable_and_keeps_unknown_steps_blocked():
    from value_investment_agent.presentation.excel.product_workbench import SHEET_DECISION_PROCESS
    workbook = build_product_workbench_workbook(_model())
    sheet = workbook[SHEET_DECISION_PROCESS]
    assert _click_distance(workbook, SHEET_TODAY, SHEET_DECISION_PROCESS) == 1
    assert _click_distance(workbook, SHEET_DECISION_PROCESS, SHEET_COMPANIES) == 1
    statuses = [cell.value for cell in sheet["C"] if cell.value == "暂未通过"]
    assert statuses == ["暂未通过"] * (8 * len(_model().companies))
    text = "\n".join(str(cell.value) for row in sheet for cell in row if cell.value)
    assert "尚未就绪" in text
    assert "NOT_READY" not in text
    assert "当前价格是否有效桥接" in text


def test_decision_process_preserves_upstream_status_and_audit_links():
    from value_investment_agent.presentation.excel.product_workbench import SHEET_DECISION_PROCESS
    from value_investment_agent.presentation.read_models.product_workbench import DECISION_STEP_TITLES
    payload = _payload()
    steps = [dict(key=key, status="PASS", reason="已记录的上游评估。", next_action="跟踪新证据。",
                  assessment_id=f"assessment-{key}", evidence_refs=["evidence-1"])
             for key in DECISION_STEP_TITLES]
    steps[1]["status"] = "CONDITIONAL"
    steps[-1]["status"] = "BLOCKED"
    payload["companies"][0]["decision_process"] = steps
    workbook = build_product_workbench_workbook(product_workbench_from_payload(payload))
    sheet = workbook[SHEET_DECISION_PROCESS]
    actual = [cell.value for cell in sheet["C"] if cell.value in {"通过", "有条件通过", "暂未通过"}]
    expected = {"PASS": "通过", "CONDITIONAL": "有条件通过", "BLOCKED": "暂未通过"}
    assert actual == [expected[step["status"]] for step in steps]
    links = [cell for row in sheet for cell in row if cell.hyperlink and str(cell.value).startswith("查看证据")]
    assert len(links) == 8
    assert all(SHEET_SYSTEM_AUDIT in cell.hyperlink.target for cell in links)
    audit_text = "\n".join(str(cell.value) for row in workbook[SHEET_SYSTEM_AUDIT] for cell in row if cell.value)
    assert "assessment-financial_facts" in audit_text
