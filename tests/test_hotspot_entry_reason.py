"""Entry trigger and quality explanations preserve existing observation gates."""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path

import pytest

from value_investment_agent.application.hotspot import lifecycle_review as subject
from value_investment_agent.application.hotspot.report_text import render_hotspot_lifecycle_markdown


@pytest.mark.parametrize("trigger,quality,tier,expected", [
    (False, "RESEARCH_ONLY", "STRUCTURE_QUALIFIED_OBSERVATION", "ENTRY_TRIGGER_NOT_OBSERVED"),
    (False, "UNKNOWN", "ACTIVE_ONLY", "ENTRY_TRIGGER_NOT_OBSERVED"),
    (True, "UNKNOWN", "ACTIVE_ONLY", "ENTRY_BEHAVIOR_QUALITY_NOT_USABLE"),
    (True, "RESEARCH_ONLY", "ACTIVE_ONLY", "ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED"),
    (True, "RESEARCH_ONLY", "STRUCTURE_QUALIFIED_OBSERVATION", "ENTRY_STRUCTURE_OBSERVED"),
])
def test_independent_reasons_do_not_change_selection_or_permissions(monkeypatch, trigger, quality, tier, expected):
    case = dict(current_reference_price="213.85", market_trade_date="2026-10-23")
    plan = dict(model_or_rule_version="TEST_ONLY", price_behavior=dict(blockers=[], observation_quality=quality),
        opportunity_quality=dict(structure_tier=tier), conditional_action_rules={
            name: dict(observed=trigger if name == "OPEN" else False, personal_permission=False)
            for name in ("OPEN", "ADD", "REDUCE", "EXIT")})
    monkeypatch.setattr(subject, "inspect_current_price_case", lambda **kw:
        dict(data_status="CURRENT", source_integrity="TEST_ONLY", case=case))
    monkeypatch.setattr(subject, "project_current_price_action_plan", lambda case: deepcopy(plan))
    result = subject.build_hotspot_lifecycle_review(root=Path("."), symbol="300033",
        current_case_binding=dict(path="TEST_ONLY", sha256="a" * 64), now=datetime.now(timezone.utc))
    old_outcome = "ENTRY_OBSERVATION" if trigger and tier == "STRUCTURE_QUALIFIED_OBSERVATION" else "WATCH"
    assert result["observed_review"] == old_outcome
    assert result["current_conditions"]["OPEN"]["observed"] is trigger
    explanation = result["decision_explanation"]
    assert explanation["basis_code"] == expected
    why = explanation["why_not_add"]
    assert ("ENTRY_TRIGGER_NOT_OBSERVED" in why) is (not trigger)
    assert ("ENTRY_BEHAVIOR_QUALITY_NOT_USABLE" in why) is (quality != "RESEARCH_ONLY")
    assert ("ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED" in why) is (tier != "STRUCTURE_QUALIFIED_OBSERVATION")
    assert "OWNED_ENTRY_REQUIRED_FOR_HELD_REVIEW" in why
    assert len(why) == len(set(why))
    assert result["formal_eligibility"] is result["trade_eligible"] is False
    assert result["personal_action"] == "NO_ACTION" and result["action"] == "no_order"


def test_real_300033_trigger_is_not_described_as_untriggered():
    configured = os.environ.get("HOTSPOT_RETAINED_ROOT")
    if not configured:
        pytest.skip("Read-only real source root required")
    root = Path(configured)
    path = root / "runtime/hotspot-current-price-cases/300033-2026-10-23-8efa36adf3a545a79b4c6b0d857506e6/case.json"
    if not path.is_file():
        pytest.skip("Retained Oct23 300033 public case missing")
    ref = dict(path=path.relative_to(root).as_posix(), sha256=sha256(path.read_bytes()).hexdigest())
    assert ref["sha256"] == "f3b714c35b0d275a2dd607b9b3883768f8ff67842409c75aaf87f6555f9d86d3"
    result = subject.build_hotspot_lifecycle_review(root=root, symbol="300033",
        current_case_binding=ref, now=datetime.fromisoformat("2026-10-23T21:00:00+08:00"))
    assert result["current_data_status"] == "CURRENT", result
    assert result["observed_review"] == "WATCH"
    assert result["current_conditions"]["OPEN"]["observed"] is True
    assert result["current_conditions"]["OPEN"]["price"] == "211.500"
    explanation = result["decision_explanation"]
    assert explanation["current_price_observation"]["price"] == "213.850"
    assert explanation["basis_code"] == "ENTRY_BEHAVIOR_QUALITY_NOT_USABLE"
    assert "ENTRY_MULTIPERIOD_STRUCTURE_NOT_QUALIFIED" in explanation["why_not_add"]
    assert "ENTRY_TRIGGER_NOT_OBSERVED" not in explanation["why_not_add"]
    text = render_hotspot_lifecycle_markdown(result)
    assert "价格行为质量不足或尚待核验" in text
    assert "当前开仓结构尚不满足观察条件" not in text
    assert result["position_guidance"] is None and result["action"] == "no_order"
