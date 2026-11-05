from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot.observation_plan import (
    build_hotspot_observation_plan, _validation_summary,
)
from value_investment_agent.application.hotspot.validation_evidence import build_hotspot_quantitative_validation
from test_hotspot_current_price_case import capture, NOW
from test_hotspot_quantitative_validation import execution_fixture
from value_investment_agent.quote_sessions import CHINA


def binding(case):
    return dict(path=case["case_path"], sha256=case["case_sha256"])


def test_verified_case_pipeline_produces_all_conditions_without_inferring_holdings(tmp_path):
    case = capture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    result = build_hotspot_observation_plan(root=tmp_path, symbol=case["symbol"],
        case_binding=binding(case), now=NOW)
    assert result["current_data"]["data_status"] == "CURRENT"
    assert result["validation"]["execution_metrics"]["status"] == "UNASSESSABLE"
    assert set(result["observation_conditions"]) == {"entry", "add", "stop", "reduce", "exit"}
    for intent in ("add", "stop", "reduce", "exit"):
        condition = result["observation_conditions"][intent]
        assert condition["requires_existing_holding"] is True
        assert condition["personal_permission"] is False
    assert result["holdings_status"] == "UNKNOWN" and result["position_guidance"] is None
    assert result["price_action_plan"]["schema_version"] == "price-action-plan-independent-v2"
    assert "VALUE_GATE_NOT_PROVEN" not in result["blockers"]
    assert result["formal_eligibility"] is result["risk_review_eligible"] is False
    assert result["personal_action"] == result["price_action_plan"]["action_intent"] == "WATCH"
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


def test_stale_data_retains_history_without_current_actions(tmp_path):
    case = capture(tmp_path)
    result = build_hotspot_observation_plan(root=tmp_path, symbol=case["symbol"],
        case_binding=binding(case), now=datetime(2026, 9, 28, 16, tzinfo=CHINA))
    assert result["status"] == "HISTORICAL_OBSERVATION_ONLY"
    assert all(value is None for value in result["observation_conditions"].values())
    assert result["price_action_plan"]["historical_observation"]["entry_trigger_price"] is not None
    assert "CURRENT_MARKET_DATA_STALE" in result["blockers"]
    assert result["validation"]["strategy_validation"] == "NOT_PROVEN"


def test_tampered_evidence_has_no_observation_plan(tmp_path):
    case = capture(tmp_path)
    path = tmp_path / case["source_bindings"]["15m"]["path"]
    path.write_bytes(path.read_bytes() + b" ")
    result = build_hotspot_observation_plan(root=tmp_path, symbol=case["symbol"],
        case_binding=binding(case), now=NOW)
    assert result["status"] == "UNASSESSABLE"
    assert result["price_action_plan"] is None


@pytest.mark.parametrize("empty", [True, False])
def test_cost_simulation_is_explicit_and_never_becomes_current_strategy_validation(tmp_path, empty):
    case = capture(tmp_path)
    _, inputs, _, run = execution_fixture(tmp_path)
    if empty:
        inputs["orders"] = []
    report = run()
    now = datetime(2026, 10, 24, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="ACTUAL"):
        build_hotspot_observation_plan(root=tmp_path, symbol=case["symbol"],
            case_binding=binding(case), validation_binding=report["protocol_binding"], now=now)
    output = build_hotspot_observation_plan(root=tmp_path, symbol=case["symbol"],
        case_binding=binding(case), validation_binding=report["protocol_binding"], now=now,
        allow_test_only=True)
    validation = output["validation"]
    assert validation["trade_count"] == (0 if empty else 3)
    assert validation["execution_metrics"]["status"] == "INSUFFICIENT_SAMPLE"
    assert len(validation["execution_metrics"]["cost_sensitivity"]) == 2
    assert validation["applicability"] == "EXECUTION_PROTOCOL_NOT_BOUND_TO_CURRENT_STRUCTURE"
    assert validation["strategy_validation"] == "NOT_PROVEN"
    assert validation["formal_eligibility"] is False
    assert validation["elapsed_real_shadow_sessions"] == 0
    assert output["risk_review_eligible"] is False


def test_retained_real_sources_are_replayed_without_runtime_and_not_rebound_to_today():
    root = Path(__file__).resolve().parents[1]
    path = root / ("artifacts/current/dual-strategy-v5/retained-hotspot-sources/"
        "fde29d8729f84fa9b5ca4e9e07785f09/manifest.json")
    raw = path.read_bytes()
    report = build_hotspot_quantitative_validation(root=root,
        protocol_binding=dict(path=path.relative_to(root).as_posix(), sha256=sha256(raw).hexdigest()),
        now=datetime(2026, 10, 22, 16, tzinfo=CHINA))
    assert report["namespace"] == "ACTUAL"
    assert report["signal_event_count"] == 161
    assert report["mature_five_session_count"] == 150
    assert report["right_censored_count"] == 11
    case = report["results"][0]["case_binding"]
    old_binding = dict(path=case["case_path"], sha256=case["case_sha256"])
    same = _validation_summary(report, symbol=case["symbol"], case_binding=old_binding)
    assert same["applicability"] == "SAME_CASE_DESCRIPTIVE_ONLY"
    changed = deepcopy(old_binding)
    changed["sha256"] = "0" * 64
    other = _validation_summary(report, symbol=case["symbol"], case_binding=changed)
    assert other["applicability"] == "HISTORICAL_OTHER_CASES_NOT_CURRENT_STRUCTURE"
    assert other["trade_count"] is None
    assert other["execution_metrics"]["cost_sensitivity"] is None
    assert other["strategy_validation"] == "NOT_PROVEN"
