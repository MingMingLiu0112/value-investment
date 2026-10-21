from datetime import datetime, timezone

from test_value_action_plan import _published
from value_investment_agent.application.decision.current_value_plan import revalidate_current_value_plan
from value_investment_agent.application.decision.value_action_plan import load_registered_value_action_plans
from value_investment_agent.application.decision import current_value_plan
import pytest


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


@pytest.mark.parametrize('verified,price,expected', [
    (True, '100.50', '100.50'), (False, '100.50', None),
    (True, 'NaN', None), (True, '-1', None), (True, None, None),
])
def test_stale_economics_keeps_only_independently_rebuilt_quote(tmp_path, monkeypatch, verified, price, expected):
    frozen = dict(schema_version='value-action-plan-v1', symbol='600519',
                  current_quote_verified=True, reference_close='999', market_trade_date='2026-10-20',
                  bear='80', base='100', bull='120', formal_eligibility=True,
                  entry_condition=dict(price='90'), blockers=[])
    rebuilt = dict(symbol='600519', current_quote_verified=verified, reference_close=price,
                   market_trade_date='2026-10-21', source_bindings=[dict(path='TEST_ONLY.json', sha256='test')])
    monkeypatch.setattr(current_value_plan, 'load_registered_value_action_plans',
        lambda *args, **kwargs: dict(items=[rebuilt], blockers=[]))
    actual = revalidate_current_value_plan(tmp_path, frozen, now=datetime.now(timezone.utc))
    assert actual['reference_close'] == expected
    assert actual['current_quote_verified'] is (expected is not None)
    assert actual['price_comparison_eligible'] is False
    assert actual['formal_eligibility'] is False
    assert actual['entry_condition'] is None and actual['bear'] is None
    if expected is not None:
        assert actual['market_trade_date'] == '2026-10-21'
        assert actual['reference_price_scope'] == 'CURRENT_VERIFIED_CLOSE_NOT_VALUATION_COMPARABLE'
    assert frozen['reference_close'] == '999'
