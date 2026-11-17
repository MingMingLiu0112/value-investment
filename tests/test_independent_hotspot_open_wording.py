"""Successor OPEN wording changes neither source inputs nor admission results."""
from copy import deepcopy
from datetime import datetime, timezone
import json

from test_independent_hotspot_projection import isolated
from value_investment_agent.application.hotspot import independent_price_conditions as projection


def test_independent_open_wording_preserves_prices_flags_and_legacy_input(isolated, tmp_path):
    source = isolated[0]["items"][0]["price_action_plan"]
    source.update(entry_trigger_price="12.34", invalidation_price="11.20", reference_close="12.40")
    now = datetime.now(timezone.utc)
    baseline = projection.project_independent_price_condition(
        tmp_path, symbol="000333", plan=source, now=now,
    )
    legacy_rule = "VALUE_GATE_REQUIRED：价值门通过后才可进入人工开仓复核。"
    source["entry_condition"] = {"price": "12.34", "rule": legacy_rule, "status": "TRIGGER_OBSERVED"}
    source["conditional_action_rules"] = {
        "OPEN": {"price": "12.34", "rule": legacy_rule, "eligible": False},
        "ADD": {"price": "13.00", "rule": "UNCHANGED_ADD", "eligible": False},
        "REDUCE": {"price": "11.80", "rule": "UNCHANGED_REDUCE", "eligible": False},
        "EXIT": {"price": "11.20", "rule": "UNCHANGED_EXIT", "eligible": False},
    }
    original = deepcopy(source)
    original_bytes = json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8")
    result = projection.project_independent_price_condition(
        tmp_path, symbol="000333", plan=source, now=now,
    )
    rule = result["entry_condition"]["rule"]
    assert rule == result["conditional_action_rules"]["OPEN"]["rule"]
    assert "热点独立策略" in rule
    assert "价值" not in rule and "VALUE_GATE" not in rule
    for key in baseline:
        if key != "operational_conditions":
            assert result[key] == baseline[key]
    expected_entry = {**original["entry_condition"], "rule": rule}
    expected_rules = deepcopy(original["conditional_action_rules"])
    expected_rules["OPEN"]["rule"] = rule
    assert result["entry_condition"] == expected_entry
    assert result["conditional_action_rules"] == expected_rules
    assert result["operational_conditions"] == {
        **baseline["operational_conditions"], "conditions": expected_rules}
    assert result["risk_review_eligible"] is True
    for flag in ("formal_eligibility", "action_eligibility", "trade_eligible"):
        assert result[flag] is False
    assert source == original
    assert json.dumps(source, ensure_ascii=False, sort_keys=True).encode("utf-8") == original_bytes
