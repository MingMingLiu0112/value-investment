"""Compiler consumer tests use explicit TEST_ONLY adapters, not real acceptance."""
from copy import deepcopy
from datetime import datetime,timezone
import pytest
from value_investment_agent.application.research import operating_distribution_review_v1 as app

def arrange(monkeypatch):
    policy=dict(fiscal_year=2026,minimum_payout_ratio=".75",minimum_distribution_cny="850",currency="CNY",scope="consolidated_parent")
    source=dict(path="TEST_ONLY.pdf",sha256="a"*64)
    observations=dict(status="VERIFIED",source_bound_observations=[dict(source=source,
        observation=dict(dividend_policy=dict(status="VERIFIED",policies=[policy])))],
        current_financial_coverage=dict(latest_report_period="2026-09-30"))
    context=dict(financial_basis="2026-06-30",evidence=[dict(field="parent_profit",period="2026-06-30",
        scope="consolidated_parent",unit="CNY",kind="VERIFIED_REPORTED_FACT",value="430")])
    # Rolling PBT 300 = H2 100 + next H1 200; taxes60=20+40; NCI3=1+2.
    path=dict(annual_income_rows=[dict(period_start="2026-07-01",period_end="2027-06-30",
        group_pbt_cny="300",tax_assumption=dict(value="60"),signed_nci_cny="3")],
        d2_witness=dict(group_pbt_cny="200",income_tax_cny="40",signed_nci_cny="2"))
    cash=dict(consumption_fingerprint="b"*64,annual_followup=dict(status="CONDITIONAL_STRESS_CONSUMED",
        input_descriptor_sha256="c"*64,transport=dict(scenarios={k:deepcopy(path) for k in ("bear","base","bull")})))
    monkeypatch.setattr(app,"read_current_capital_observation",lambda *args:deepcopy(observations))
    monkeypatch.setattr(app,"build_operating_source_context",lambda **kwargs:deepcopy(context))
    calls=[]
    def cold(**kwargs):calls.append(kwargs);return deepcopy(cash)
    monkeypatch.setattr(app,"read_operating_cash_consumption",cold)
    task=dict(symbol="000001",research_as_of="2026-10-31T00:00:00+00:00",source_binding=source)
    def run():return app.read_operating_distribution_review(root=None,task=task,now=datetime(2026,11,1,tzinfo=timezone.utc))
    return run,observations,context,cash,calls

def test_exact_half_reconstruction_not_rolling_or_times_two(monkeypatch):
    run,_,_,_,calls=arrange(monkeypatch)
    result=run()
    assert calls and result["status"]=="SOURCE_BOUND_FISCAL_POLICY_REVIEW"
    for row in result["scenarios"].values():
        assert row["assumed_h2_parent_profit_cny"]=="79"
        assert row["conditional_fy_parent_profit_cny"]=="509"
        assert row["policy_target_cny"]=="850"
        assert row["target_above_current_year_positive_earnings_cny"]=="341"
        assert row["policy_compliance"]=="NOT_ASSESSED"
    assert result["financial_update_review"]["status"]=="NEWER_REPORT_REQUIRES_MODEL_REVALIDATION"
    assert result["condition_price"] is None and not result["formal_eligibility"]

def test_bad_source_retains_explicit_failure_without_using_cash(monkeypatch):
    run,obs,_,_,calls=arrange(monkeypatch);obs["status"]="PARTIAL"
    assert run()["reason"]=="ALL_REGISTERED_CAPITAL_ORIGINALS_MUST_VERIFY"
    assert not calls

def test_conflicting_policy_refuses_without_selecting_one(monkeypatch):
    run,obs,_,_,calls=arrange(monkeypatch)
    item=deepcopy(obs["source_bound_observations"][0])
    item["observation"]["dividend_policy"]["policies"][0]["minimum_distribution_cny"]="950"
    obs["source_bound_observations"].append(item)
    assert run()["reason"]=="CONFLICTING_DISCLOSED_FISCAL_POLICIES"
    assert not calls

def test_unavailable_annual_result_not_replaced_by_old_values(monkeypatch):
    run,_,_,cash,_=arrange(monkeypatch);cash["annual_followup"]["status"]="UNASSESSABLE"
    assert run()["reason"]=="COLD_RECOMPUTED_ANNUAL_CASH_PATH_REQUIRED"

def test_future_h1_misdated_transport_refuses(monkeypatch):
    run,_,_,cash,_=arrange(monkeypatch)
    cash["annual_followup"]["transport"]["scenarios"]["bear"]["annual_income_rows"][0]["period_end"]="2026-12-31"
    with pytest.raises(ValueError,match="ROLLING_TRANSPORT_PERIOD_CHANGED"):run()

def test_conflicting_actual_anchor_refuses(monkeypatch):
    run,_,context,_,_=arrange(monkeypatch);context["evidence"].append(deepcopy(context["evidence"][0]))
    assert run()["reason"]=="EXACT_REPORTED_PARENT_PROFIT_ANCHOR_REQUIRED"

def test_same_economic_policy_with_different_source_metadata_corrobates(monkeypatch):
    run,obs,_,_,_=arrange(monkeypatch)
    obs["source_bound_observations"][0]["observation"]["dividend_policy"]["policies"][0].update(
        physical_page=31,excerpt="TEST_ONLY FY policy")
    item=deepcopy(obs["source_bound_observations"][0])
    item["observation"]["dividend_policy"]["policies"][0].update(physical_page=21,excerpt="TEST_ONLY H1 policy")
    obs["source_bound_observations"].append(item)
    value=run()
    assert value["status"]=="SOURCE_BOUND_FISCAL_POLICY_REVIEW"
    assert [r["policy"]["physical_page"] for r in value["policy_evidence"]]==[31,21]

def test_verified_q3_consumed_without_modifying_frozen_cash_path(monkeypatch):
    run,obs,_,cash,_=arrange(monkeypatch)
    obs["source_bound_observations"][0]["observation"]["financial_update"]=dict(
        status="VERIFIED",period_basis="YEAR_TO_DATE_9M_NOT_SINGLE_QUARTER",
        period_start="2026-01-01",period_end="2026-09-30",
        fields=dict(parent_profit_cny=dict(value="567",unit="CNY",scope="consolidated_parent")))
    before=deepcopy(cash)
    result=run()
    assert result["financial_update_review"]["comparisons"]["base"]["implied_q4_parent_profit_cny"]=="-58"
    assert cash==before
