"""Scheduled owner-distribution model tests; synthetic and no_order only."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal as D
import json

import pytest

from test_direct_parent_owner_cash_v1 import inputs
from test_residual_income_equity_valuation import case, complete_facts
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import (
    compile_direct_owner_cash_path as compile_v1,
)
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v2 import (
    compile_direct_owner_cash_path as compile_v2,
)
from value_investment_agent.valuation_models import direct_owner_cash_v2 as model


def scenario(cost="0.08", *, scheduled="0", operating_cash="100"):
    data = deepcopy(inputs())
    data["cost_of_equity"] = cost
    data["years"][0]["policy"]["operating_cash"] = operating_cash
    data["years"][0]["scheduled_owner_distribution_cny"] = scheduled
    result = compile_v2(**data)
    return model.DirectOwnerCashScenario(
        symbol="600519", opening=data["opening"], years=data["years"],
        terminal=data["terminal"], ordinary_shares=D(data["ordinary_shares"]),
        cost_of_equity=D(cost),
        forecast_roes=tuple(D(row["roe_assumption"]) for row in result["annual_rows"]),
        forecast_retentions=tuple(
            D(row["retention_assumption"]) for row in result["annual_rows"]
        ),
    )


def facts(*, scheduled="0", operating_cash="100"):
    return complete_facts(
        operating_inputs={
            "start_book_equity": D(1000), "ordinary_shares": D(100),
            "opening_cash": D(20),
        },
        scenario_inputs={
            name: scenario(cost, scheduled=scheduled, operating_cash=operating_cash)
            for name, cost in zip(model.SCENARIOS, (".10", ".08", ".06"))
        },
    )


def test_payload_roundtrip_preserves_scheduled_distribution_exactly():
    original = scenario(scheduled="20", operating_cash="50")
    payload = json.loads(json.dumps(model.scenario_to_payload(original)))
    restored = model.scenario_from_payload(payload)
    assert restored == original
    assert restored.years[0]["scheduled_owner_distribution_cny"] == "20"
    assert model.scenario_to_payload(restored) == payload


def test_scheduled_distribution_enters_shared_model_and_reconciles():
    value = model.DirectOwnerCashValuationModel().value(
        facts(scheduled="20", operating_cash="50"), case()
    )
    row = value.assumptions["scenario_calculations"]["base"]["annual_rows"][0]
    assert D(row["scheduled_owner_distribution_cny"]) == 20
    assert D(row["conditional_distribution_cny"]) == 10
    assert D(row["total_owner_distribution_cny"]) == 30
    assert D(row["closing_book_equity_cny"]) == 1050
    assert D(row["retention_assumption"]) == D("0.625")
    assert value.status == "conditional_research_only"
    assert value.assumptions["formal_eligibility"] is False
    assert value.assumptions["action"] == "no_order"


def test_shared_model_rechecks_nonterminating_roe_at_domain_precision():
    data = deepcopy(inputs())
    data["opening"].update(book="3", cash="0", capacity="0", debt="0")
    data["ordinary_shares"] = "3"
    for policy in (data["years"][0]["policy"], data["terminal"]["policy"]):
        policy.update(
            parent_profit="1",
            operating_cash="1",
            maintenance_capex="0",
            cash_floor="0",
            payout_ratio="1",
        )
    data["years"][0]["scheduled_owner_distribution_cny"] = "0"
    calculated = compile_v2(**data)
    typed = model.DirectOwnerCashScenario(
        symbol="600519",
        opening=data["opening"],
        years=data["years"],
        terminal=data["terminal"],
        ordinary_shares=D(data["ordinary_shares"]),
        cost_of_equity=D(data["cost_of_equity"]),
        forecast_roes=tuple(D(row["roe_assumption"]) for row in calculated["annual_rows"]),
        forecast_retentions=tuple(
            D(row["retention_assumption"]) for row in calculated["annual_rows"]
        ),
    )
    f = complete_facts(
        operating_inputs={
            "start_book_equity": D("3"),
            "ordinary_shares": D("3"),
            "opening_cash": D("0"),
        },
        scenario_inputs={name: typed for name in model.SCENARIOS},
    )
    value = model.DirectOwnerCashValuationModel().value(f, case())
    assert value.status == "conditional_research_only"


def test_zero_scheduled_is_economically_v1_compatible():
    data = inputs()
    old = compile_v1(**deepcopy(data))
    data["years"][0]["scheduled_owner_distribution_cny"] = "0"
    new = compile_v2(**data)
    assert new["per_share_value"] == old["per_share_value"]
    assert new["conditional_equity_value_cny"] == old["conditional_equity_value_cny"]
    assert new["annual_rows"][0]["total_owner_distribution_cny"] == old["annual_rows"][0]["conditional_distribution_cny"]


def test_tampering_is_recomputed_and_rejected():
    f = facts(scheduled="20", operating_cash="50")
    altered = deepcopy(f.scenario_inputs["base"].years)
    altered[0]["scheduled_owner_distribution_cny"] = "40"
    tampered = replace(f.scenario_inputs["base"], years=altered)
    with pytest.raises(ValueError, match="SCHEDULED_DISTRIBUTION_REQUIRES_BORROWING_OR_CASH"):
        model.scenario_calculation(f, tampered)


@pytest.mark.parametrize("change", ["extra", "missing", "old_contract", "float"])
def test_unknown_or_lossy_fields_are_rejected(change):
    payload = model.scenario_to_payload(scenario())
    if change == "extra":
        payload["unregistered_cash"] = "1"
    elif change == "missing":
        del payload["years"]
    elif change == "old_contract":
        payload["scenario_contract"] = "direct-owner-cash-scenario-v1"
    else:
        payload["ordinary_shares"] = 100.0
    with pytest.raises(ValueError):
        model.scenario_from_payload(payload)


def test_facts_codec_rejects_cross_version_scenarios():
    payload = model.facts_to_payload(facts())
    payload["scenario_inputs"]["base"]["scenario_contract"] = "direct-owner-cash-scenario-v1"
    with pytest.raises(ValueError):
        model.facts_from_payload(payload)
