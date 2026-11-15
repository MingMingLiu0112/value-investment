"""TEST_ONLY orchestration controls; actual PDF replay is recorded separately."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import pytest
from value_investment_agent.application.research import parent_direct_cash_alternative as subject


@pytest.fixture
def observations(monkeypatch):
    h=dict(symbol="600123",scope="ISSUER_PARENT_STANDALONE",currency="CNY",
           classification="FACT",period_start="2025-01-01",period_end="2025-06-30",
           revenue="100",cost="60",customer_cash="90",supplier_cash="70",cfo="10",
           source_refs={"id":"TEST_ONLY_H1"})
    next_h=dict(h,period_start="2026-01-01",period_end="2026-06-30",
                revenue="110",cost="66",customer_cash="95",supplier_cash="45",cfo="35")
    annual=dict(h,period_end="2025-12-31",revenue="220",cost="150",
                customer_cash="210",supplier_cash="160",cfo="25",
                source_refs={"id":"TEST_ONLY_FY"})
    data={"interim":{"observed":[h,next_h]},"annual":{"observed":[annual]}}
    calls=[]
    def read(**kwargs):
        calls.append(kwargs)
        return deepcopy(data[kwargs["receipt_binding"]])
    monkeypatch.setattr(subject,"read_parent_direct_cash_research",read)
    return data,calls


def run():
    return subject.replay_direct_cash_alternative(
        root="TEST_ONLY",interim_binding="interim",annual_binding="annual",
        evaluated_at=datetime(2026,11,16,tzinfo=timezone.utc),forecast_year=2027)


def test_source_loader_is_used_and_year_is_built_from_separate_seasons(observations):
    data,calls=observations
    result=run()
    assert len(calls)==2
    assert result["derived_h2"]["cfo"]=="15"
    assert [Decimal(p["operating_cash"]) for p in result["annual_cash_scenarios"]]==[27,50]
    for path in result["annual_cash_scenarios"]:
        assert len(path["component_periods"])==2
        assert path["period_start"]=="2027-01-01"
        assert path["period_end"]=="2027-12-31"
    assert result["adopted_base"] is None and not result["e2_ready"]
    assert result["working_capital_cash_component"] is None


def test_wrong_issuer_or_unmatched_year_cannot_join_sources(observations):
    data,_=observations
    data["annual"]["observed"][0]["symbol"]="600124"
    with pytest.raises(ValueError,match="MATCHED_ANNUAL"):
        run()


def test_unavailable_original_is_not_replaced_by_cached_result(monkeypatch):
    def fail(**kwargs):
        raise ValueError("PARENT_DIRECT_CASH_HASH_CHANGED")
    monkeypatch.setattr(subject,"read_parent_direct_cash_research",fail)
    with pytest.raises(ValueError,match="HASH_CHANGED"):
        run()


def test_replay_does_not_annualise_or_imply_distribution_capacity(observations):
    result=run()
    assert all(p["distribution_capacity"] is None for p in result["annual_cash_scenarios"])
    assert result["formal_eligibility"] is False
    assert result["action"]=="no_order"
