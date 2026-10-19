from datetime import datetime, timezone

from test_value_action_plan import _published
from value_investment_agent.application.decision.current_value_plan import revalidate_current_value_plan
from value_investment_agent.application.decision.value_action_plan import load_registered_value_action_plans


def test_read_time_financial_original_tamper_clears_current_conditions(tmp_path, monkeypatch):
    _, explanation, _, _ = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    frozen = load_registered_value_action_plans(tmp_path, now=now)["items"][0]
    assert revalidate_current_value_plan(tmp_path, frozen, now=now) == frozen
    (tmp_path / "runtime/fact.txt").write_bytes(b"changed financial original")
    blocked = revalidate_current_value_plan(tmp_path, frozen, now=now)
    assert blocked["signal_state"] == "BLOCKED"
    assert blocked["bear"] is None and blocked["reference_close"] is None
    assert blocked["action_intent"] is None
    assert blocked["entry_condition"] is None and blocked["formal_eligibility"] is False
    assert "CURRENT_VALUE_PLAN_CHANGED_OR_STALE" in blocked["blockers"]
    assert frozen["bear"] is not None


def test_read_time_revalidation_covers_action_and_admission_fields(tmp_path, monkeypatch):
    _, explanation, _, _ = _published(tmp_path, monkeypatch)
    now = datetime.fromisoformat(explanation["decision_as_of"]).replace(tzinfo=timezone.utc)
    frozen = load_registered_value_action_plans(tmp_path, now=now)["items"][0]
    tampered = {**frozen, "formal_eligibility": not frozen["formal_eligibility"]}

    blocked = revalidate_current_value_plan(tmp_path, tampered, now=now)

    assert blocked["signal_state"] == "STALE"
    assert blocked["formal_eligibility"] is False
    assert blocked["action_intent"] is None
    assert "CURRENT_VALUE_PLAN_CHANGED_OR_STALE" in blocked["blockers"]
