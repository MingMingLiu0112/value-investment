"""Public capital evidence remains available without a verified paid Agent task."""
from copy import deepcopy

from web_api.test_live_operating_research_api import api, result, BASE
from test_web_agent_research import state
from value_investment_agent.application.research import current_capital_observation_v1 as native


def test_source_bound_capital_remains_visible_without_agent_task(api, monkeypatch):
    client, _, data, root = api
    data.rows = []
    capital = dict(status="VERIFIED", symbol="600519", action="no_order",
        formal_eligibility=False, current_capital_continuity="NOT_PROVEN",
        current_financial_coverage=dict(status="REGISTERED_SOURCES_ONLY",
            latest_report_period="2026-09-30", complete_current_coverage=False))
    monkeypatch.setattr(native, "read_current_capital_observation", lambda *args: deepcopy(capital))
    before = state(root)
    body = client.get(BASE + "/companies/600519").json()
    assert body["status"] == "NOT_STARTED"
    assert body["current_capital_observation"] == capital
    assert "research_draft" not in body and "condition_price" not in body
    assert body["action"] == "no_order" and body["formal_eligibility"] is False
    assert state(root) == before and not data.provider_calls


def test_bad_agent_task_does_not_hide_independent_capital_or_reuse_old_research(api, monkeypatch):
    client, _, data, root = api
    data.rows = [result(scope="TEST_ONLY_LIVE_CONTRACT")]
    capital = dict(status="VERIFIED", action="no_order", formal_eligibility=False,
        current_capital_continuity="NOT_PROVEN")
    monkeypatch.setattr(native, "read_current_capital_observation", lambda *args: deepcopy(capital))
    before = state(root)
    body = client.get(BASE + "/companies/600519").json()
    assert body["status"] == "UNASSESSABLE"
    assert body["current_capital_observation"] == capital
    assert "research_draft" not in body and "condition_price" not in body
    assert state(root) == before and not data.provider_calls


def test_corrupt_source_does_not_masquerade_as_no_evidence(api, monkeypatch):
    client, _, data, root = api
    data.rows = []
    def fail(*args):
        raise ValueError("TEST_ONLY_ORIGINAL_HASH_CHANGED")
    monkeypatch.setattr(native, "read_current_capital_observation", fail)
    before = state(root)
    body = client.get(BASE + "/companies/600519").json()
    assert body["status"] == "NOT_STARTED"
    assert body["current_capital_observation"] == dict(status="UNASSESSABLE",
        reason="CURRENT_CAPITAL_SOURCE_NOT_VERIFIED", action="no_order",
        formal_eligibility=False)
    assert state(root) == before and not data.provider_calls
