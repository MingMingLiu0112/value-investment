from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path
import re

from openpyxl import load_workbook
import pytest

from value_investment_agent.application.product import product_workbench_candidate as candidate_module
from value_investment_agent.application.product.product_workbench_candidate import (
    ACTION_NO_ORDER,
    build_product_workbench_candidate_payload,
    validate_product_workbench_candidate_payload,
)
from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_EVENTS,
    SHEET_PORTFOLIO,
    SHEET_SYSTEM_AUDIT,
    USER_SHEETS,
    WORKBOOK_SHEETS,
    build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    product_workbench_from_payload,
)

from product_workbench_candidate_fixture import (
    materialize_synthetic_legacy_packet,
    synthetic_legacy_packet,
)


GENERATED_AT = datetime(2026, 9, 26, 3, 0, tzinfo=timezone.utc)


def _packet() -> dict:
    return synthetic_legacy_packet(GENERATED_AT.isoformat())


def _materialized_packet(root: Path) -> dict:
    packet = _packet()
    materialize_synthetic_legacy_packet(root, packet)
    return packet


def _user_text(workbook) -> str:
    return "\n".join(
        str(cell.value)
        for title in USER_SHEETS
        for row in workbook[title].iter_rows()
        for cell in row
        if cell.value is not None
    )


def test_synthetic_packet_builds_five_page_candidate_without_portfolio_metrics(
    tmp_path: Path,
) -> None:
    packet = _materialized_packet(tmp_path)
    payload = build_product_workbench_candidate_payload(packet, root=tmp_path)
    model = product_workbench_from_payload(payload)
    workbook = build_product_workbench_workbook(model)

    assert model.action == ACTION_NO_ORDER
    assert tuple(workbook.sheetnames) == WORKBOOK_SHEETS
    assert tuple(workbook.sheetnames[:5]) == USER_SHEETS
    assert workbook.sheetnames[-1] == SHEET_SYSTEM_AUDIT
    assert len(model.today_items) == 6
    assert len(model.opportunities) == 18
    assert len(model.companies) == 3
    assert len(model.events) == 1
    assert len(model.audit_evidence) == 13
    assert model.portfolio.real_data_available is False
    assert model.portfolio.summary == ()
    assert model.portfolio.positions == ()
    assert model.opportunities[0].research_status.user_label == "等待关键经营证据"
    assert model.companies[0].research_status.user_label == "等待更多证据"

    user_text = _user_text(workbook)
    assert not re.search(r"\bM[2-6]\b", user_text)
    for hidden in (
        "INSUFFICIENT_EVIDENCE",
        "INSUFFICIENT_RESEARCH",
        "ENGINEERING_DONE_OFFLINE",
        "PREFLIGHT_DONE",
        "PENDING_USER_PRIVATE_INPUT",
        "target_weight",
        "position_size",
        "trade_approved",
        "建议买入",
        "目标仓位",
        "下单",
    ):
        assert hidden not in user_text

    portfolio_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_PORTFOLIO].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "尚未接入真实组合" in portfolio_text
    assert "个性化组合分析已暂停" in portfolio_text
    assert "查看接入说明" not in user_text
    assert "尚未收到真实个人组合输入" not in user_text
    for simulated_metric in (
        "总资产",
        "股票仓位",
        "预计年股息",
        "正常化年股息",
        "单股集中度",
    ):
        assert simulated_metric not in portfolio_text
    assert not any(
        isinstance(cell.value, (int, float))
        for row in workbook[SHEET_PORTFOLIO].iter_rows()
        for cell in row
    )

    evidence_links = [
        cell
        for title in USER_SHEETS
        for row in workbook[title].iter_rows()
        for cell in row
        if isinstance(cell.value, str) and cell.value.startswith("查看证据 (")
    ]
    assert evidence_links
    assert all(cell.hyperlink is not None for cell in evidence_links)

    audit_text = "\n".join(
        str(cell.value)
        for row in workbook[SHEET_SYSTEM_AUDIT].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert "SHA-256" in audit_text
    assert packet["audit"]["artifacts"][0]["sha256"] in audit_text
    assert packet["audit"]["artifacts"][0]["path"] in audit_text
    assert ACTION_NO_ORDER in audit_text


def test_synthetic_candidate_can_be_written_and_reopened(tmp_path: Path) -> None:
    packet = _materialized_packet(tmp_path)
    payload = build_product_workbench_candidate_payload(packet, root=tmp_path)
    model = product_workbench_from_payload(payload)
    workbook = build_product_workbench_workbook(model)
    output = tmp_path / "m7-product-ux-candidate-v1-20260926.xlsx"
    workbook.save(output)

    reopened = load_workbook(output, data_only=False)

    assert tuple(reopened.sheetnames) == WORKBOOK_SHEETS
    assert reopened[SHEET_PORTFOLIO]["A4"].value == "尚未接入真实组合"


def test_projection_fails_closed_on_missing_evidence() -> None:
    packet = _packet()
    packet["audit"]["artifacts"] = []

    with pytest.raises(ValueError, match="Pinned audit evidence"):
        build_product_workbench_candidate_payload(packet, root=Path.cwd())


def test_projection_fails_closed_on_missing_evidence_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Missing evidence file"):
        build_product_workbench_candidate_payload(_packet(), root=tmp_path)


def test_projection_requires_an_evidence_root() -> None:
    with pytest.raises(TypeError, match="root"):
        build_product_workbench_candidate_payload(_packet())

    with pytest.raises(ValueError, match="root must be a pathlib.Path"):
        build_product_workbench_candidate_payload(_packet(), root=None)  # type: ignore[arg-type]


def test_projection_fails_closed_on_unsupported_status(tmp_path: Path) -> None:
    packet = _materialized_packet(tmp_path)
    packet["m2"]["rows"][0]["status"] = "M2_VERIFIED"

    with pytest.raises(ValueError, match="Unsupported m2 row status"):
        build_product_workbench_candidate_payload(packet, root=tmp_path)


def test_projection_fails_closed_on_execution_keys(tmp_path: Path) -> None:
    packet = _materialized_packet(tmp_path)
    packet["m2"]["rows"][0]["target_weight"] = 0.1

    with pytest.raises(ValueError, match="active execution key"):
        build_product_workbench_candidate_payload(packet, root=tmp_path)


def test_projection_fails_closed_on_simulated_portfolio_metrics(
    tmp_path: Path,
) -> None:
    packet = _materialized_packet(tmp_path)
    packet["m4"]["normalized_annual_dividend"] = "0.00"

    with pytest.raises(ValueError, match="Simulated portfolio metric"):
        build_product_workbench_candidate_payload(packet, root=tmp_path)


def test_payload_validator_rejects_fake_numeric_placeholders(tmp_path: Path) -> None:
    packet = _materialized_packet(tmp_path)
    payload = build_product_workbench_candidate_payload(packet, root=tmp_path)
    malformed = copy.deepcopy(payload)
    malformed["companies"][0]["valuation"]["value_text"] = "0.00"

    with pytest.raises(ValueError, match="numeric placeholder"):
        validate_product_workbench_candidate_payload(malformed)


def test_payload_validator_rejects_internal_stage_tokens_in_user_copy(
    tmp_path: Path,
) -> None:
    packet = _materialized_packet(tmp_path)
    payload = build_product_workbench_candidate_payload(packet, root=tmp_path)
    malformed = copy.deepcopy(payload)
    malformed["companies"][0]["valuation"]["unavailable_reason"] = (
        "M3 尚未完成。"
    )

    with pytest.raises(ValueError, match="internal stage token"):
        validate_product_workbench_candidate_payload(malformed)


def test_explicit_observation_ledger_projects_research_change_only(tmp_path: Path, monkeypatch) -> None:
    packet = _materialized_packet(tmp_path)
    payload = build_product_workbench_candidate_payload(packet, root=tmp_path)
    observation_path = tmp_path / "runtime" / "prospective-observations" / "000333" / "prospective-test.json"
    observation_path.parent.mkdir(parents=True, exist_ok=True)
    observation_path.write_text("{\"observation_id\": \"prospective-test\"}\n", encoding="utf-8")
    row = {
        "observation_id": "prospective-test",
        "source_document_id": "cninfo:test",
        "source_available_at": "2026-09-26T00:00:00+08:00",
        "symbol": "000333",
        "_ledger_path": observation_path.as_posix(),
    }
    monkeypatch.setattr(candidate_module, "load_verified_observation_ledger", lambda **_: (row,))

    candidate_module._project_prospective_observation_ledger(
        payload,
        root=tmp_path,
        manifest_path=Path("config/ledger.json"),
        manifest_sha256="0" * 64,
        evaluation_cutoff=datetime(2026, 9, 27, tzinfo=timezone.utc),
    )

    evidence_id = "prospective-observation-prospective-test"
    assert evidence_id in {item["evidence_id"] for item in payload["audit"]["evidence"]}
    observation_item = next(
        item for item in payload["today_items"]
        if item["category"] == "RESEARCH_CHANGE"
        and item.get("symbol") == "000333"
        and evidence_id in item.get("evidence_refs", [])
    )
    assert "不构成严格同期PIT证明" in observation_item["why_it_matters"]
    assert len(payload["events"]) == 1
    assert payload["action"] == ACTION_NO_ORDER


def test_m5_projection_rejects_evidence_after_its_research_cutoff():
    projection = {
        "evaluation_cutoff_date": "2026-09-28",
        "events": [],
        "audit_evidence": [{"evidence_id": "notice", "available_at": "2026-09-29"}],
        "audit_decisions": [],
    }

    with pytest.raises(ValueError, match="unavailable by evaluation cutoff"):
        candidate_module._validate_m5_projection_availability(projection)


def test_future_available_source_is_absent_from_every_canonical_product_sheet(tmp_path: Path):
    packet = _materialized_packet(tmp_path)
    source_path = tmp_path / "runtime" / "excluded" / "notice.pdf"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"pinned future-available source")
    source_hash = candidate_module.hashlib.sha256(source_path.read_bytes()).hexdigest()
    evidence_id = "cninfo-1225582141"
    event_id = "midea-2026-egm-notice-1225582141"

    payload = build_product_workbench_candidate_payload(
        packet,
        root=tmp_path,
        m5_event_projection={
            "action": ACTION_NO_ORDER,
            "evaluation_cutoff_date": "2026-09-28",
            "events": [],
            "audit_evidence": [],
            "audit_decisions": [],
            "as_of_excluded_evidence": [{
                "evidence": {
                    "evidence_id": evidence_id,
                    "title": "临时股东会通知（公告日2026-09-28）",
                    "artifact_type": "cninfo_original_pdf",
                    "path": "runtime/excluded/notice.pdf",
                    "sha256": source_hash,
                    "available_at": "2026-09-29",
                    "action": ACTION_NO_ORDER,
                    "source_url": "https://static.cninfo.com.cn/finalpage/2026-09-28/1225582141.PDF",
                },
                "reason": "SOURCE_NOT_AVAILABLE_AS_OF_CUTOFF",
                "related_event_ids": [event_id],
            }],
        },
    )
    model = product_workbench_from_payload(payload)
    workbook = build_product_workbench_workbook(model)

    assert evidence_id not in {item.evidence_id for item in model.audit_evidence}
    assert "excluded_evidence" not in payload["audit"]
    product_text = "\n".join(
        str(cell.value)
        for sheet_name in WORKBOOK_SHEETS
        for row in workbook[sheet_name].iter_rows()
        for cell in row
        if cell.value is not None
    )
    assert evidence_id not in product_text
    assert event_id not in product_text
    assert "临时股东会通知（公告日2026-09-28）" not in product_text
