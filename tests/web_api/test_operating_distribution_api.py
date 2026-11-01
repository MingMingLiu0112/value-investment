"""Public fiscal/capital projection: no private unlock, writes, or paid calls."""
from copy import deepcopy
import pytest
from web_api.test_live_operating_research_api import api,reviewed_result,BASE
from test_web_agent_research import state
from value_investment_agent.application.research import current_capital_observation_v1 as native
from value_investment_agent.application.research import operating_distribution_review_v1 as fiscal
from value_investment_agent.application.research import operating_cash_consumption_v1 as cash

def test_public_source_observations_and_fiscal_research_without_private_unlock(api,monkeypatch):
    client,_,data,root=api
    task=reviewed_result();data.rows=[task]
    capital=dict(status="VERIFIED",action="no_order",formal_eligibility=False,current_capital_continuity="NOT_PROVEN")
    review=dict(status="SOURCE_BOUND_FISCAL_POLICY_REVIEW",scenarios={"base":{"policy_compliance":"NOT_ASSESSED"}},action="no_order",formal_eligibility=False)
    monkeypatch.setattr(native,"read_current_capital_observation",lambda *args:deepcopy(capital))
    monkeypatch.setattr(fiscal,"read_operating_distribution_review",lambda **kwargs:deepcopy(review))
    monkeypatch.setattr(cash,"read_operating_cash_consumption",lambda **kwargs:{"status":"TEST_ONLY"})
    before=state(root)
    body=client.get(BASE+"/companies/600519").json()
    assert body["current_capital_observation"]==capital
    assert body["fiscal_distribution_review"]==review
    assert body["research_draft"]==task["research_draft"]
    assert state(root)==before and not data.provider_calls
    assert body["action"]=="no_order" and body["formal_eligibility"] is False

def test_failed_capital_or_fiscal_cannot_erase_valid_research(api,monkeypatch):
    client,_,data,root=api
    task=reviewed_result();data.rows=[task]
    def fail(*args,**kwargs):raise ValueError("TEST_ONLY SOURCE CHANGED")
    monkeypatch.setattr(native,"read_current_capital_observation",fail)
    monkeypatch.setattr(fiscal,"read_operating_distribution_review",fail)
    monkeypatch.setattr(cash,"read_operating_cash_consumption",lambda **kwargs:{"status":"TEST_ONLY"})
    body=client.get(BASE+"/companies/600519").json()
    assert body["status"]=="SUCCEEDED"
    assert body["current_capital_observation"]["status"]=="UNASSESSABLE"
    assert body["fiscal_distribution_review"]["status"]=="UNASSESSABLE"
    assert body["research_draft"]==task["research_draft"]


def test_parent_funding_public_projection_is_independent_and_not_current_cash(api,monkeypatch):
    from value_investment_agent.application.research import parent_funding_review_v1 as funding
    client,_,data,root=api
    task=reviewed_result();data.rows=[task]
    expected=dict(status="HISTORICAL_PARENT_REVIEW",current_capacity_proven=False,formal_eligibility=False,
        action="no_order",review=dict(result=dict(status="INCOMPLETE_OBLIGATIONS",
            static_after_declared_dividend="17016211333.61",conditional_distribution_ceiling=None)))
    monkeypatch.setattr(funding,"read_registered_parent_funding_review",lambda **kwargs:deepcopy(expected))
    monkeypatch.setattr(native,"read_current_capital_observation",lambda *args:{"status":"NOT_STARTED"})
    monkeypatch.setattr(fiscal,"read_operating_distribution_review",lambda **kwargs:{"status":"NOT_STARTED"})
    monkeypatch.setattr(cash,"read_operating_cash_consumption",lambda **kwargs:{"status":"TEST_ONLY"})
    before=state(root)
    body=client.get(BASE+"/companies/600519").json()
    assert {k:v for k,v in body["parent_funding_review"].items() if k != "cash_input_comparison"}==expected
    assert body["parent_funding_review"]["cash_input_comparison"]["status"]=="NOT_ASSESSABLE"
    assert body["status"]=="SUCCEEDED" and body["research_draft"]==task["research_draft"]
    assert state(root)==before and not data.provider_calls

def test_parent_funding_source_failure_preserves_other_public_research(api,monkeypatch):
    from value_investment_agent.application.research import parent_funding_review_v1 as funding
    client,_,data,root=api;task=reviewed_result();data.rows=[task]
    def fail(**kwargs):raise ValueError("TEST_ONLY parent original changed")
    monkeypatch.setattr(funding,"read_registered_parent_funding_review",fail)
    monkeypatch.setattr(native,"read_current_capital_observation",lambda *args:{"status":"NOT_STARTED"})
    monkeypatch.setattr(fiscal,"read_operating_distribution_review",lambda **kwargs:{"status":"SOURCE_BOUND_FISCAL_POLICY_REVIEW"})
    monkeypatch.setattr(cash,"read_operating_cash_consumption",lambda **kwargs:{"status":"TEST_ONLY"})
    body=client.get(BASE+"/companies/600519").json()
    assert body["parent_funding_review"]["status"]=="UNASSESSABLE"
    assert body["status"]=="SUCCEEDED"
    assert body["fiscal_distribution_review"]["status"]=="SOURCE_BOUND_FISCAL_POLICY_REVIEW"
