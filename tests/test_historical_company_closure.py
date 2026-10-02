from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def fixed_closure_clock(monkeypatch):
    import value_investment_agent.application.historical_validation.historical_company_closure as module

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = cls(2026, 10, 1, 4, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(module, "datetime", FixedDatetime)

from value_investment_agent.application.historical_validation.historical_company_closure import (
    build_historical_company_closure,
)
from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_SYSTEM_AUDIT,
    USER_SHEETS,
    build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.historical_company_closure import (
    project_historical_company_closure,
    render_historical_company_closure,
    render_historical_reviews,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    ACTION_NO_ORDER,
    HISTORICAL_REVIEW_KIND,
    PRODUCT_WORKBENCH_SCHEMA_VERSION,
    product_workbench_from_payload,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _digest(path)


def _pin(path: Path, *, filename: str | None = None) -> dict[str, str]:
    value = {"path": path.as_posix(), "sha256": _digest(path)}
    if filename is not None:
        value["filename"] = filename
    return value


def _fixture(root: Path) -> Path:
    source = root / "m3-source.json"
    _write_json(source, {"source": "fixture"})
    filing = root / "filing.pdf"
    filing.write_bytes(b"filing")
    prices = root / "prices.json"
    _write_json(prices, {"close": "10"})
    m3 = {
        "schema_version": "m3-historical-research-replay-v1",
        "replay_id": "fixture-replay", "symbol": "600519", "replay_date": "2024-06-21",
        "source_receipt": {"input": {"path": source.as_posix(), "sha256": _digest(source)}, "source_decision": {"date": "2024-06-21"}},
        "then_known_facts": {"symbol": "600519", "period_label": "2023-12-31"},
        "then_known_filings": [{"path": filing.as_posix(), "sha256": _digest(filing)}],
        "then_known_quote": {"symbol": "600519", "quote_date": "2024-06-21", "close_cny": "10", "source_ref": {"path": prices.as_posix(), "sha256": _digest(prices)}},
        "rule": {"rule_version": "fixture-v1", "rule_registration_status": "RETROSPECTIVE_RESEARCH_EXTENSION"},
        "final_decision": "WAIT", "blockers": ["retrospective_rule_not_contemporaneous"],
        "valuation_approved": False, "trade_approved": False,
        "future_facts_used": False, "future_rule_version_used": True, "action": "no_order",
    }
    m3_path = root / "replay.json"
    _write_json(m3_path, m3)
    canonical = hashlib.sha256(json.dumps(m3, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    m3_manifest = root / "replay.manifest.json"
    _write_json(m3_manifest, {"replay_sha256": canonical, "action": "no_order"})

    sessions = [
        {"date": "2015-01-05", "open": "10", "close": "10"},
        {"date": "2015-01-06", "open": "10", "close": "10"},
    ]
    execution_input = root / "execution-input.json"
    execution_input_hash = _write_json(execution_input, {
        "contract_version": "moutai-real-execution-input-v5",
        "input_scope": "authenticated_historical_OHLC_and_reviewed_cash_distributions",
        "symbol": "600519",
        "sessions": sessions, "cash_events": [{"event_id": "fixture"}], "decisions": {},
        "formal_fair_value": None, "valuation_approved": False, "trade_approved": False,
    })
    execution_journal = root / "execution-journal.json"
    execution_journal_hash = _write_json(execution_journal, [
        {"date": "2015-01-05", "created_order": None, "pending_order_id": None, "fill": None,
         "rejected_order_reason": None, "cash_events": [], "holding_shares": 0,
         "cash_cny": "100.00", "nav_cny": "100.00"},
        {"date": "2015-01-06", "created_order": None, "pending_order_id": None, "fill": None,
         "rejected_order_reason": None, "cash_events": [{"event_id": "fixture"}], "holding_shares": 0,
         "cash_cny": "100.00", "nav_cny": "100.00"},
    ])
    execution_summary = root / "execution-summary.json"
    execution_summary_hash = _write_json(execution_summary, {
        "symbol": "600519", "input_sha256": execution_input_hash, "opening_cash_cny": "100.00",
        "filled_orders": [], "pending_order": None, "trade_approved": False, "live_eligible": False,
    })
    execution_manifest = root / "execution.manifest.json"
    _write_json(execution_manifest, {"outputs": {"summary.json": execution_summary_hash, "journal.json": execution_journal_hash}})

    range_journal = root / "upper-30pct-journal.json"
    range_journal_hash = _write_json(range_journal, [
        {"date": "2015-01-05", "decision": "no_decision", "created_order": None, "fill": None,
         "rejected_order_reason": None, "execution_state_reason": "research_assumption", "cash_events": []},
        {"date": "2015-01-06", "decision": "proposed_entry", "created_order": {"side": "buy"},
         "fill": None, "rejected_order_reason": None, "execution_state_reason": "research_assumption", "cash_events": []},
    ])
    range_result = root / "range-result.json"
    range_result_hash = _write_json(range_result, {
        "symbol": "600519", "run_type": "historical_research_range_sensitivity", "sessions": 2,
        "results": [{"scenario": "upper-30pct", "endpoint": "upper", "safety_margin": "0.30", "fills": 0,
                     "ending_nav_cny": "100.00", "gross_research_return": "0", "maximum_drawdown": "0", "periods": []}],
        "formal_fair_value": None, "valuation_approved": False, "trade_approved": False, "live_eligible": False,
        "strategy_backtest_complete": False, "validation_classification": "NOT_PIT_SAFE",
        "validation_admission_status": "NOT_ADMITTED", "limitations": ["fixture limitation"],
    })
    range_manifest = root / "range.manifest.json"
    _write_json(range_manifest, {"outputs": {"result.json": range_result_hash, range_journal.name: range_journal_hash}})

    recipe = root / "input.json"
    payload = {
        "schema_version": "historical-company-closure-input-v1", "action": "no_order",
        "scope": "READ_ONLY_HISTORICAL_RESEARCH_CLOSURE", "symbol": "600519", "company_name": "贵州茅台",
        "m3_replay": _pin(m3_path), "m3_manifest": _pin(m3_manifest),
        "execution_input": _pin(execution_input), "execution_summary": _pin(execution_summary),
        "execution_journal": _pin(execution_journal), "execution_manifest": _pin(execution_manifest),
        "range_result": _pin(range_result), "range_manifest": _pin(range_manifest),
        "range_journal": _pin(range_journal, filename=range_journal.name),
    }
    _write_json(recipe, payload)
    return recipe


def _product_model():
    return product_workbench_from_payload({
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": "2026-10-01T12:00:00+08:00",
        "as_of": "2026-10-01",
        "action": ACTION_NO_ORDER,
        "overview": {"pending_count": 0},
        "system_health": {"status": "EVIDENCE_INSUFFICIENT", "message": "测试状态"},
        "stages": {
            "m2": {"status": "DONE", "detail": "筛选完成"},
            "m3": {"status": "PARTIAL", "detail": "研究进行中"},
            "m4": {"status": "PARKED_WAITING_R2_NONBLOCKING", "detail": "无真实组合"},
            "m5": {"status": "PARTIAL", "detail": "事件链进行中"},
            "m6": {"status": "NOT_STARTED", "detail": "真实监控未开始"},
        },
        "audit": {"evidence": []},
        "today_items": [],
        "opportunities": [],
        "companies": [],
        "portfolio": {
            "real_data_available": False,
            "status": "PARKED_WAITING_R2_NONBLOCKING",
            "connection_hint": "尚未接入真实组合",
            "summary": [],
            "positions": [],
            "action": ACTION_NO_ORDER,
        },
        "events": [],
    })


def _projected_fixture(tmp_path: Path):
    recipe = _fixture(tmp_path)
    closure = build_historical_company_closure(
        root=tmp_path,
        input_path=recipe,
        input_sha256=_digest(recipe),
    )
    closure_path = tmp_path / "closure-result.json"
    digest = _write_json(closure_path, closure)
    model = _product_model()
    return model, closure, project_historical_company_closure(
        model,
        closure=closure,
        closure_path=closure_path.as_posix(),
        closure_sha256=digest,
    )


def _sheet_text(workbook, titles: tuple[str, ...]) -> str:
    values: list[str] = []
    for title in titles:
        for row in workbook[title].iter_rows():
            for cell in row:
                if cell.value is not None:
                    values.append(str(cell.value))
    return "\n".join(values)


def test_historical_company_closure_builds_readable_report(tmp_path: Path):
    recipe = _fixture(tmp_path)
    result = build_historical_company_closure(root=tmp_path, input_path=recipe, input_sha256=_digest(recipe))

    assert result["symbol"] == "600519"
    assert result["engineering_delivery"] == "DELIVERED"
    assert result["current_research_admission"] == "NOT_READY"
    assert result["execution_clock"]["sessions"] == 2
    assert result["execution_clock"]["declared_cash_events"] == 1
    assert result["execution_clock"]["journal_cash_event_rows"] == 1
    assert result["range_diagnostics"]["scenarios"][0]["scenario"] == "upper-30pct"
    assert result["strict_pit_admitted"] is False
    assert result["historical_execution_validated"] is False
    report = render_historical_company_closure(result)
    assert "历史研究闭环" in report
    assert "当前研究准入 | 尚无交易准入" in report
    assert "不生成交易订单" in report
    assert "无决策执行时钟" in report
    assert "事后研究扩展规则，不能代表当时已经知悉" in report
    assert "相对PE只用于研究参考，不代表公司内在价值。" in report
    assert "relative_pe_research_only_not_intrinsic_valuation" not in report
    assert "NOT_READY" not in report
    assert "action=no_order" not in report


def test_historical_company_closure_rejects_manifest_hash_drift(tmp_path: Path):
    recipe = _fixture(tmp_path)
    manifest = tmp_path / "range.manifest.json"
    manifest.write_text(json.dumps({"outputs": {"result.json": "0" * 64, "upper-30pct-journal.json": "1" * 64}}), encoding="utf-8")
    payload = json.loads(recipe.read_text(encoding="utf-8"))
    payload["range_manifest"]["sha256"] = _digest(manifest)
    recipe.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="range manifest result hash mismatch"):
        build_historical_company_closure(root=tmp_path, input_path=recipe, input_sha256=_digest(recipe))


def test_historical_closure_projects_only_to_secondary_audit(tmp_path: Path):
    model, _closure, projected = _projected_fixture(tmp_path)

    assert projected.companies == model.companies
    assert len(projected.historical_reviews) == 1
    review = projected.historical_reviews[0]
    assert review.review_kind == HISTORICAL_REVIEW_KIND
    assert review.symbol == "600519"
    assert review.engineering_delivery.code == "DELIVERED"
    assert review.current_research_admission.code == "NOT_READY"
    assert review.strict_pit.code == "NOT_PROVEN"
    assert review.historical_execution.code == "NOT_VALIDATED"
    assert review.performance_claim.code == "NOT_ALLOWED"
    assert review.action == ACTION_NO_ORDER

    report = render_historical_reviews(projected)
    assert "贵州茅台" in report
    assert "当前研究未准入" in report
    assert "严格历史时点未证明" in report
    assert "历史执行未验证" in report
    assert "不形成业绩结论" in report
    assert "action=no_order" not in report

    workbook = build_product_workbench_workbook(projected)
    audit_text = _sheet_text(workbook, (SHEET_SYSTEM_AUDIT,))
    user_text = _sheet_text(workbook, USER_SHEETS)
    assert "历史研究闭环审计" in audit_text
    assert "贵州茅台" in audit_text
    assert "历史研究闭环审计" not in user_text
    assert "贵州茅台" not in user_text


@pytest.mark.parametrize(
    "field",
    ("strict_pit_admitted", "historical_execution_validated", "performance_claim_allowed", "price_review_eligible"),
)
def test_historical_closure_projection_rejects_promotion(tmp_path: Path, field: str):
    _model, closure, _projected = _projected_fixture(tmp_path)
    promoted = deepcopy(closure)
    promoted[field] = True
    with pytest.raises(ValueError, match=field):
        project_historical_company_closure(
            _product_model(),
            closure=promoted,
            closure_path="runtime/historical-closure.json",
            closure_sha256="a" * 64,
        )


def test_historical_closure_projection_rejects_m3_symbol_mismatch(tmp_path: Path):
    _model, closure, _projected = _projected_fixture(tmp_path)
    mismatched = deepcopy(closure)
    mismatched["m3_replay"]["then_known_facts"]["symbol"] = "600000"
    mismatched["m3_replay"]["then_known_quote"]["symbol"] = "600000"
    with pytest.raises(ValueError, match="m3 symbol mismatch"):
        project_historical_company_closure(
            _product_model(),
            closure=mismatched,
            closure_path="runtime/historical-closure.json",
            closure_sha256="a" * 64,
        )


def test_historical_closure_projection_rejects_future_generation(tmp_path: Path):
    _model, closure, _projected = _projected_fixture(tmp_path)
    future = deepcopy(closure)
    future["generated_at"] = "2026-10-02T00:00:00+08:00"
    with pytest.raises(ValueError, match="generated after"):
        project_historical_company_closure(
            _product_model(),
            closure=future,
            closure_path="runtime/historical-closure.json",
            closure_sha256="a" * 64,
        )


def test_historical_closure_projection_rejects_nonzero_execution(tmp_path: Path):
    _model, closure, _projected = _projected_fixture(tmp_path)
    nonzero = deepcopy(closure)
    nonzero["execution_clock"]["orders"] = 1
    with pytest.raises(ValueError, match="zero orders"):
        project_historical_company_closure(
            _product_model(),
            closure=nonzero,
            closure_path="runtime/historical-closure.json",
            closure_sha256="a" * 64,
        )

    changed_cash = deepcopy(closure)
    changed_cash["execution_clock"]["ending_nav_cny"] = "100.01"
    with pytest.raises(ValueError, match="changed cash or nav"):
        project_historical_company_closure(
            _product_model(),
            closure=changed_cash,
            closure_path="runtime/historical-closure.json",
            closure_sha256="a" * 64,
        )
