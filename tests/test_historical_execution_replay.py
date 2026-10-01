from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from value_investment_agent.application.historical_validation.historical_execution_replay import (
    build_historical_execution_replay,
)
from value_investment_agent.presentation.excel.product_workbench import (
    SHEET_SYSTEM_AUDIT,
    USER_SHEETS,
    build_product_workbench_workbook,
)
from value_investment_agent.presentation.read_models.historical_execution_replay import (
    project_historical_execution_replay,
    render_historical_execution_replay,
    render_historical_execution_replays,
)
from value_investment_agent.presentation.read_models.product_workbench import (
    ACTION_NO_ORDER,
    HISTORICAL_EXECUTION_REPLAY_KIND,
    PRODUCT_WORKBENCH_SCHEMA_VERSION,
    product_workbench_from_payload,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return _digest(path)


def _pin(path: Path, *, filename: str | None = None) -> dict[str, str]:
    value = {"path": path.as_posix(), "sha256": _digest(path)}
    if filename is not None:
        value["filename"] = filename
    return value


def _fixture(root: Path) -> Path:
    reference = root / "reference.json"
    reference_hash = _write_json(reference, {"kind": "fixture"})
    sessions = [
        {"date": "2015-08-21", "open": "10.00", "close": "10.00"},
        {"date": "2015-08-24", "open": "9.00", "close": "9.50"},
        {"date": "2015-08-25", "open": "9.50", "close": "10.00"},
        {"date": "2016-01-04", "open": "12.00", "close": "12.00"},
        {"date": "2016-01-05", "open": "13.00", "close": "13.00"},
        {"date": "2019-12-31", "open": "13.00", "close": "13.00"},
        {"date": "2020-01-02", "open": "13.00", "close": "13.00"},
        {"date": "2022-12-30", "open": "13.00", "close": "13.00"},
        {"date": "2023-01-03", "open": "13.00", "close": "13.00"},
        {"date": "2025-12-31", "open": "13.00", "close": "13.00"},
    ]
    execution_input = root / "execution-input.json"
    _write_json(execution_input, {
        "contract_version": "moutai-real-execution-input-v5",
        "input_scope": "authenticated_historical_OHLC_and_reviewed_cash_distributions",
        "symbol": "600519",
        "sessions": sessions,
        "cash_events": [],
        "decisions": {},
        "references": [{
            "kind": "prices",
            "path": reference.relative_to(root).as_posix(),
            "sha256": reference_hash,
        }],
        "formal_fair_value": None,
        "valuation_approved": False,
        "trade_approved": False,
    })

    range_config = root / "range-config.json"
    _write_json(range_config, {
        "version": "moutai-historical-range-experiment-v1",
        "execution": "daily-bar research assumption; no order-book proof",
        "fee": "dated release fee plus commission scenario",
    })
    entry_order = {
        "order_id": "fixture-entry",
        "side": "buy",
        "requested_quantity": 200,
        "submitted_on": "2015-08-21",
        "decision_state": "proposed_entry",
    }
    exit_order = {
        "order_id": "fixture-exit",
        "side": "sell",
        "requested_quantity": None,
        "submitted_on": "2016-01-04",
        "decision_state": "proposed_exit",
    }
    journal = [
        {
            "date": "2015-08-21",
            "decision": "proposed_entry",
            "decision_details": {
                "state": "proposed_entry",
                "action": "research_entry_experiment",
                "decision_id": "fixture-entry",
                "quantity": 200,
            },
            "created_order": entry_order,
            "fill": None,
            "rejected_order_reason": None,
            "cash_cny": "1000000.00",
            "holding_shares": 0,
            "sellable_shares": 0,
            "receivable_cny": "0.00",
            "nav_cny": "1000000.00",
            "cash_events": [],
            "pending_order_id": "fixture-entry",
        },
        {
            "date": "2015-08-24",
            "decision": "paper_hold",
            "decision_details": {"state": "paper_hold", "action": "no_order"},
            "created_order": None,
            "fill": {
                **entry_order,
                "filled_on": "2015-08-24",
                "quantity": 200,
                "price": "9.00",
                "fee_cny": "5.04",
            },
            "rejected_order_reason": None,
            "cash_cny": "998194.96",
            "holding_shares": 200,
            "sellable_shares": 0,
            "receivable_cny": "0.00",
            "nav_cny": "1000094.96",
            "cash_events": [],
            "pending_order_id": None,
        },
        {
            "date": "2015-08-25",
            "decision": "paper_hold",
            "decision_details": {"state": "paper_hold", "action": "no_order"},
            "created_order": None,
            "fill": None,
            "rejected_order_reason": None,
            "cash_cny": "998194.96",
            "holding_shares": 200,
            "sellable_shares": 200,
            "receivable_cny": "0.00",
            "nav_cny": "1000194.96",
            "cash_events": [],
            "pending_order_id": None,
        },
        {
            "date": "2016-01-04",
            "decision": "proposed_exit",
            "decision_details": {
                "state": "proposed_exit",
                "action": "research_exit_experiment",
                "decision_id": "fixture-exit",
            },
            "created_order": exit_order,
            "fill": None,
            "rejected_order_reason": None,
            "cash_cny": "998194.96",
            "holding_shares": 200,
            "sellable_shares": 200,
            "receivable_cny": "0.00",
            "nav_cny": "1000594.96",
            "cash_events": [],
            "pending_order_id": "fixture-exit",
        },
        {
            "date": "2016-01-05",
            "decision": "watch",
            "decision_details": {"state": "watch", "action": "no_order"},
            "created_order": None,
            "fill": {
                **exit_order,
                "filled_on": "2016-01-05",
                "quantity": 200,
                "price": "13.00",
                "fee_cny": "7.65",
            },
            "rejected_order_reason": None,
            "cash_cny": "1000787.31",
            "holding_shares": 0,
            "sellable_shares": 0,
            "receivable_cny": "0.00",
            "nav_cny": "1000787.31",
            "cash_events": [],
            "pending_order_id": None,
        },
    ]
    for date in ("2019-12-31", "2020-01-02", "2022-12-30", "2023-01-03", "2025-12-31"):
        journal.append({
            "date": date,
            "decision": "watch",
            "decision_details": {"state": "watch", "action": "no_order"},
            "created_order": None,
            "fill": None,
            "rejected_order_reason": None,
            "cash_cny": "1000787.31",
            "holding_shares": 0,
            "sellable_shares": 0,
            "receivable_cny": "0.00",
            "nav_cny": "1000787.31",
            "cash_events": [],
            "pending_order_id": None,
        })
    range_journal = root / "upper-30pct-journal.json"
    _write_json(range_journal, journal)
    range_result = root / "result.json"
    _write_json(range_result, {
        "symbol": "600519",
        "run_type": "historical_research_range_sensitivity",
        "validation_classification": "NOT_PIT_SAFE",
        "validation_admission_status": "NOT_ADMITTED",
        "approved_value_model_sessions": 0,
        "formal_fair_value": None,
        "valuation_approved": False,
        "strategy_backtest_complete": False,
        "simulation_eligible": False,
        "trade_approved": False,
        "live_eligible": False,
        "results": [{
            "scenario": "upper-30pct",
            "opening_nav_cny": "1000000.00",
            "ending_nav_cny": "1000787.31",
            "gross_research_return": "0.00078731",
            "maximum_drawdown": "0",
            "fills": 2,
            "rejected_orders": 0,
            "ending_shares": 0,
            "first_fill_date": "2015-08-24",
            "last_fill_date": "2016-01-05",
            "periods": [
                {"period": "development", "start": "2015-08-21", "end": "2019-12-31", "sessions": 6,
                 "opening_nav_cny": "1000000.00", "ending_nav_cny": "1000787.31",
                 "gross_research_return": "0.00078731", "maximum_drawdown": "0",
                 "fills": 2, "rejected_orders": 0},
                {"period": "validation", "start": "2020-01-02", "end": "2022-12-30", "sessions": 2,
                 "opening_nav_cny": "1000787.31", "ending_nav_cny": "1000787.31",
                 "gross_research_return": "0", "maximum_drawdown": "0",
                 "fills": 0, "rejected_orders": 0},
                {"period": "sealed_test", "start": "2023-01-03", "end": "2025-12-31", "sessions": 2,
                 "opening_nav_cny": "1000787.31", "ending_nav_cny": "1000787.31",
                 "gross_research_return": "0", "maximum_drawdown": "0",
                 "fills": 0, "rejected_orders": 0},
            ],
        }],
    })
    range_manifest = root / "manifest.json"
    _write_json(range_manifest, {"outputs": {
        "result.json": _digest(range_result),
        "upper-30pct-journal.json": _digest(range_journal),
        "config.json": _digest(range_config),
    }})
    recipe = root / "input.json"
    _write_json(recipe, {
        "schema_version": "historical-execution-replay-input-v1",
        "action": "no_order",
        "symbol": "600519",
        "company_name": "贵州茅台",
        "scenario": "upper-30pct",
        "initial_cash_cny": "1000000.00",
        "execution_input": _pin(execution_input),
        "range_config": _pin(range_config),
        "range_result": _pin(range_result),
        "range_manifest": _pin(range_manifest),
        "range_journal": _pin(range_journal, filename="upper-30pct-journal.json"),
    })
    return recipe


def test_historical_execution_replay_reconstructs_frozen_scenario(tmp_path: Path):
    recipe = _fixture(tmp_path)
    payload, journal = build_historical_execution_replay(
        root=tmp_path,
        input_path=recipe,
        input_sha256=_digest(recipe),
    )

    assert payload["engineering_delivery"] == "DELIVERED"
    assert payload["current_research_admission"] == "NOT_READY"
    assert payload["historical_execution_validated"] is False
    assert payload["strict_pit_admitted"] is False
    assert payload["performance_claim_allowed"] is False
    assert payload["action"] == "no_order"
    assert payload["comparison"]["frozen_journal"]["status"] == "MATCH"
    assert payload["comparison"]["range_result"]["status"] == "MATCH"
    assert payload["summary"]["fills"] == 2
    assert payload["summary"]["ending_nav_cny"] == "1000787.31"
    assert len(journal) == 10
    assert len(payload["decision_outcomes"]) == 2
    first = payload["decision_outcomes"][0]
    assert first["execution_status"] == "FILLED"
    assert first["decision_date"] == "2015-08-21"
    assert first["fill"]["order_id"] == first["decision_id"]
    assert first["fill"]["filled_on"] != first["decision_date"]
    assert first["investment_rationale_status"] == "NOT_RECONSTRUCTED"
    bundle = payload["decision_explanations"]
    assert bundle["thesis_consistency"] == "NOT_ASSESSABLE"
    assert bundle["cards"][1]["linked_entry_id"] == first["decision_id"]
    assert bundle["cards"][0]["context"]["value_cny"] is None

    report = render_historical_execution_replay(payload)
    assert "历史执行回放" in report
    assert "不证明历史可成交" in report
    assert "upper-30pct" in report
    assert "1000787.31" in report
    assert "historical_execution_validated=false" in report
    assert "原提议与执行对照" in report
    assert "未重建，不可作为当前买卖依据" in report
    assert "企业买卖逻辑一致性无法验证" in report
    assert "关联原买入" in report


def test_proposal_outcomes_attribute_rejection_after_pending_order_cleared():
    from value_investment_agent.application.historical_validation.historical_execution_replay import _decision_outcomes

    proposals = [{"decision_id": "a", "decision_date": "2025-01-01"},
                 {"decision_id": "b", "decision_date": "2025-01-03"}]
    journal = [{"date": "2025-01-02", "deferred_order_id": "a"},
               {"date": "2025-01-03", "pending_order_id": None,
                "rejected_order": {"order_id": "a"},
                "rejected_order_reason": "insufficient_cash"}]
    outcomes = _decision_outcomes(proposals, journal)
    assert outcomes[0]["execution_status"] == "REJECTED"
    assert outcomes[0]["rejections"] == [{"date": "2025-01-03", "reason": "insufficient_cash"}]
    assert outcomes[0]["deferred_dates"] == ["2025-01-02"]
    assert outcomes[1]["execution_status"] == "UNRESOLVED"
    assert outcomes[1]["rejections"] == []


def test_historical_execution_replay_rejects_hash_drift(tmp_path: Path):
    recipe = _fixture(tmp_path)
    journal = tmp_path / "upper-30pct-journal.json"
    journal.write_text(journal.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="range journal hash mismatch"):
        build_historical_execution_replay(
            root=tmp_path,
            input_path=recipe,
            input_sha256=_digest(recipe),
        )


def test_historical_execution_replay_rejects_frozen_execution_mismatch(tmp_path: Path):
    recipe = _fixture(tmp_path)
    journal_path = tmp_path / "upper-30pct-journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal[1]["cash_cny"] = "998194.95"
    _write_json(journal_path, journal)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"]["upper-30pct-journal.json"] = _digest(journal_path)
    _write_json(manifest_path, manifest)
    recipe_payload = json.loads(recipe.read_text(encoding="utf-8"))
    recipe_payload["range_journal"]["sha256"] = _digest(journal_path)
    recipe_payload["range_manifest"]["sha256"] = _digest(manifest_path)
    _write_json(recipe, recipe_payload)

    with pytest.raises(ValueError, match="frozen journal execution mismatch"):
        build_historical_execution_replay(
            root=tmp_path,
            input_path=recipe,
            input_sha256=_digest(recipe),
        )


def test_historical_execution_replay_rejects_trade_approval(tmp_path: Path):
    recipe = _fixture(tmp_path)
    execution = tmp_path / "execution-input.json"
    value = json.loads(execution.read_text(encoding="utf-8"))
    value["trade_approved"] = True
    _write_json(execution, value)
    recipe_payload = json.loads(recipe.read_text(encoding="utf-8"))
    recipe_payload["execution_input"]["sha256"] = _digest(execution)
    _write_json(recipe, recipe_payload)

    with pytest.raises(ValueError, match="cannot authorize valuation or trading"):
        build_historical_execution_replay(
            root=tmp_path,
            input_path=recipe,
            input_sha256=_digest(recipe),
        )


def _product_model(as_of: str):
    return product_workbench_from_payload({
        "schema_version": PRODUCT_WORKBENCH_SCHEMA_VERSION,
        "generated_at": f"{as_of}T12:00:00+08:00",
        "as_of": as_of,
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


def _projected_replay(tmp_path: Path):
    recipe = _fixture(tmp_path)
    payload, _journal = build_historical_execution_replay(
        root=tmp_path,
        input_path=recipe,
        input_sha256=_digest(recipe),
    )
    replay_path = tmp_path / "historical-execution-replay.json"
    digest = _write_json(replay_path, payload)
    model = _product_model(payload["generated_at"][:10])
    return model, payload, project_historical_execution_replay(
        model,
        replay=payload,
        replay_path="runtime/execution-replay-600519-20261001/result.json",
        replay_sha256=digest,
    )


def _sheet_text(workbook, titles: tuple[str, ...]) -> str:
    values: list[str] = []
    for title in titles:
        for row in workbook[title].iter_rows():
            for cell in row:
                if cell.value is not None:
                    values.append(str(cell.value))
    return "\n".join(values)


def _reproject(model, payload, **overrides):
    mutated = deepcopy(payload)
    mutated.update(overrides)
    return project_historical_execution_replay(
        model,
        replay=mutated,
        replay_path="runtime/historical-execution-replay.json",
        replay_sha256="a" * 64,
    )


def test_historical_execution_replay_projects_only_to_secondary_audit(tmp_path: Path):
    model, payload, projected = _projected_replay(tmp_path)
    digest = _digest(tmp_path / "historical-execution-replay.json")

    assert payload["action"] == "no_order"
    assert projected.companies == model.companies
    assert len(projected.historical_execution_replays) == 1
    card = projected.historical_execution_replays[0]
    assert card.replay_kind == HISTORICAL_EXECUTION_REPLAY_KIND
    assert card.symbol == "600519"
    assert card.scenario == "upper-30pct"
    assert card.action == ACTION_NO_ORDER
    assert card.replay_sha256 == digest
    assert len(card.evidence_refs) == 1 + len(payload['source_bindings'])
    originals = [binding for binding in payload['source_bindings']
                 if binding['role'].startswith('execution_original_')]
    assert originals
    assert originals[0]['path'] == 'reference.json'
    assert originals[0]['sha256'] == _digest(tmp_path / 'reference.json')
    assert "1000787.31" in card.execution_summary
    assert any("关联原买入" in text for text in card.decision_explanations)
    assert "历史执行有效性未验证" in card.validation_summary

    report = render_historical_execution_replays(projected)
    assert "贵州茅台" in report
    assert "当前研究未准入" in report
    assert "action=no_order" not in report
    assert "冻结决策解释与买卖关联" in report

    workbook = build_product_workbench_workbook(projected)
    audit_text = _sheet_text(workbook, (SHEET_SYSTEM_AUDIT,))
    user_text = _sheet_text(workbook, USER_SHEETS)
    assert "历史执行回放审计" in audit_text
    assert "贵州茅台" in audit_text
    assert "upper-30pct" in audit_text
    assert "1000787.31" in audit_text
    assert "历史执行回放审计" not in user_text
    assert "贵州茅台" not in user_text
    assert "upper-30pct" not in user_text
    assert "1000787.31" not in user_text
    assert digest[:12] not in user_text


@pytest.mark.parametrize("field,value", [
    ("action", "buy"), ("thesis_consistency", "CONSISTENT"),
    ("scope", "CURRENT_DECISION_SUPPORT"),
])
def test_frozen_decision_explanations_cannot_promote_admission(tmp_path: Path, field, value):
    model, payload, _ = _projected_replay(tmp_path)
    mutated = deepcopy(payload)
    mutated["decision_explanations"][field] = value
    with pytest.raises(ValueError, match="cannot approve thesis or trading"):
        _reproject(model, mutated)


def test_frozen_decision_explanation_links_only_executed_entries():
    from value_investment_agent.application.historical_validation.historical_execution_replay import _decision_explanation_bundle
    entry = {"decision_id": "entry", "decision_date": "2025-01-01",
             "state": "proposed_entry", "execution_status": "REJECTED", "fill": None,
             "recorded_context": {"value_cny": "100", "close_cny": "70"}}
    exit_proposal = {**entry, "decision_id": "exit", "state": "proposed_exit"}
    bundle = _decision_explanation_bundle([entry, exit_proposal], {})
    assert bundle["cards"][1]["linked_entry_id"] is None
    entry["execution_status"] = "FILLED"
    bundle = _decision_explanation_bundle([entry, exit_proposal], {})
    assert bundle["cards"][1]["linked_entry_id"] == "entry"
    assert bundle["cards"][1]["original_value_cny"] == "100"


def test_frozen_decision_explanations_survive_product_snapshot_roundtrip(tmp_path: Path):
    from dataclasses import asdict
    from value_investment_agent.presentation.read_models.existing_research_report import public_workbench_payload_from_snapshot

    _, _, projected = _projected_replay(tmp_path)
    snapshot = json.loads(json.dumps(asdict(projected), default=lambda value: value.isoformat()))
    restored = product_workbench_from_payload(public_workbench_payload_from_snapshot(snapshot))
    assert restored.historical_execution_replays[0].decision_explanations == projected.historical_execution_replays[0].decision_explanations
    assert restored.companies == projected.companies
    assert restored.portfolio == projected.portfolio


def test_historical_execution_replay_projection_rejects_duplicate_replay(tmp_path: Path):
    model, payload, projected = _projected_replay(tmp_path)

    with pytest.raises(ValueError, match="already exists"):
        project_historical_execution_replay(
            projected,
            replay=payload,
            replay_path="runtime/historical-execution-replay.json",
            replay_sha256=_digest(tmp_path / "historical-execution-replay.json"),
        )


@pytest.mark.parametrize(
    "field",
    (
        "historical_execution_validated",
        "strict_pit_admitted",
        "investment_rule_validated",
        "performance_claim_allowed",
    ),
)
def test_historical_execution_replay_projection_rejects_flag_promotion(
    tmp_path: Path, field: str
):
    model, payload, _projected = _projected_replay(tmp_path)

    with pytest.raises(ValueError, match=field):
        _reproject(model, payload, **{field: True})


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("action", "order", "must remain no_order"),
        ("schema_version", "historical-execution-replay-v2", "unsupported historical execution replay schema"),
        ("validation_classification", "PIT_SAFE", "must remain NOT_PIT_SAFE"),
        ("validation_admission_status", "ADMITTED", "must remain NOT_ADMITTED"),
        ("current_research_admission", "ADMITTED", "cannot promote current research admission"),
        ("engineering_delivery", "pending", "must be DELIVERED"),
        ("decision_rule_recomputed", True, "cannot recompute or approve a decision rule"),
        ("mechanical_reproduction_verified", False, "mechanical reproduction"),
        ("symbol", "60051", "must contain six digits"),
    ),
)
def test_historical_execution_replay_projection_rejects_scope_expansion(
    tmp_path: Path, field: str, value: object, match: str
):
    model, payload, _projected = _projected_replay(tmp_path)

    with pytest.raises(ValueError, match=match):
        _reproject(model, payload, **{field: value})


@pytest.mark.parametrize(
    ("path", "value", "match"),
    (
        (("comparison", "frozen_journal", "status"), "MISMATCH", "frozen journal must match"),
        (("comparison", "range_result", "status"), "MISMATCH", "range result must match"),
        (("comparison", "frozen_journal", "rows_compared"), 0, "comparisons cannot be empty"),
        (("comparison", "frozen_journal", "fills_compared"), 99, "comparison counts differ"),
    ),
)
def test_historical_execution_replay_projection_rejects_comparison_gaps(
    tmp_path: Path, path: tuple[str, ...], value: object, match: str
):
    model, payload, _projected = _projected_replay(tmp_path)
    mutated = deepcopy(payload)
    target = mutated
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=match):
        project_historical_execution_replay(
            model,
            replay=mutated,
            replay_path="runtime/historical-execution-replay.json",
            replay_sha256="a" * 64,
        )


def test_historical_execution_replay_projection_rejects_source_role_gaps(tmp_path: Path):
    model, payload, _projected = _projected_replay(tmp_path)

    missing = deepcopy(payload)
    missing["source_bindings"] = [
        item for item in missing["source_bindings"] if item["role"] != "range_journal"
    ]
    with pytest.raises(ValueError, match="source roles are incomplete or duplicated"):
        project_historical_execution_replay(
            model, replay=missing, replay_path="runtime/x.json", replay_sha256="a" * 64
        )

    duplicated = deepcopy(payload)
    duplicated["source_bindings"].append(deepcopy(duplicated["source_bindings"][0]))
    with pytest.raises(ValueError, match="source roles are incomplete or duplicated"):
        project_historical_execution_replay(
            model, replay=duplicated, replay_path="runtime/x.json", replay_sha256="a" * 64
        )

    absolute = deepcopy(payload)
    absolute["source_bindings"][0]["path"] = "C:/absolute/execution-input.json"
    with pytest.raises(ValueError, match="must remain a relative project path"):
        project_historical_execution_replay(
            model, replay=absolute, replay_path="runtime/x.json", replay_sha256="a" * 64
        )

    rooted = deepcopy(payload)
    rooted["source_bindings"][0]["path"] = "/etc/execution-input.json"
    with pytest.raises(ValueError, match="must remain a relative project path"):
        project_historical_execution_replay(
            model, replay=rooted, replay_path="runtime/x.json", replay_sha256="a" * 64
        )


def test_historical_execution_replay_projection_rejects_future_generation(tmp_path: Path):
    model, payload, _projected = _projected_replay(tmp_path)
    future = (model.as_of.fromordinal(model.as_of.toordinal() + 2)).isoformat()

    with pytest.raises(ValueError, match="generated after product as_of"):
        _reproject(model, payload, generated_at=f"{future}T00:00:00+08:00")
def test_price_original_correspondence_and_fail_closed(tmp_path):
    import hashlib
    import json
    import pytest
    from value_investment_agent.infrastructure.evidence.historical_price_correspondence import verify_price_correspondence

    original = tmp_path / 'prices.json'
    rows = [['2025-01-02', '10', '11'], ['2025-01-03', '11', '12']]
    original.write_text(json.dumps({'code': 0, 'data': {'sh600519': {'day': rows}}}), encoding='utf-8')
    reference = {'kind': 'prices', 'path': 'prices.json', 'sha256': hashlib.sha256(original.read_bytes()).hexdigest()}
    sessions = [{'date': row[0], 'open': row[1], 'close': row[2]} for row in rows]
    def verify(items=sessions, refs=None):
        return verify_price_correspondence(root=tmp_path, symbol='600519', sessions=items, references=refs or [reference])
    proof = verify()
    assert proof['status'] == 'MATCH'
    assert proof['matched_sessions'] == 2
    assert proof['rows'][1]['sources'][0]['row_index'] == 1
    assert proof['action'] == 'no_order'
    assert not proof['execution_admitted']
    assert not proof['historical_availability_proven']
    with pytest.raises(ValueError, match='differs'):
        verify([dict(sessions[0], close='99')])
    with pytest.raises(ValueError, match='cover'):
        verify([dict(sessions[0], date='2025-01-04')])
    conflicting = tmp_path / 'conflict.json'
    conflicting.write_text(json.dumps({'code': 0, 'data': {'sh600519': {'day': [['2025-01-02', '9', '11']]}}}), encoding='utf-8')
    conflict_ref = dict(reference, path='conflict.json', sha256=hashlib.sha256(conflicting.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='conflicting'):
        verify(refs=[reference, conflict_ref])
    original.write_text(json.dumps({'code': 0, 'data': {'sh600519': {'qfqday': rows}}}), encoding='utf-8')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify()
    reference['sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='unadjusted'):
        verify()
    original.write_text('{}', encoding='utf-8')
    reference['sha256'] = hashlib.sha256(original.read_bytes()).hexdigest()
    assert verify()['status'] == 'NOT_ASSESSABLE'

