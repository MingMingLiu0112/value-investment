"""TEST_ONLY explicit terminal debt assumptions; never actual refinancing proof."""
from copy import deepcopy
from decimal import Decimal as D, localcontext

import pytest

from test_direct_parent_owner_cash_v1 import inputs
from value_investment_agent.domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path


def financed_inputs():
    data = inputs()
    data["opening"]["debt"] = "200"
    data["terminal"]["policy"].update(new_borrowing="50", debt_repayment="50", interest_outside_cfo="10")
    data["terminal"]["financing"] = dict(
        mode="CONSTANT_DEBT_REFINANCING",
        rationale="TEST_ONLY existing principal rolls at constant debt; cash interest is outside CFO",
        counter_evidence="TEST_ONLY refinancing may be unavailable or interest may increase",
        reopen_condition="TEST_ONLY changed maturity, debt level or interest classification",
        coverage=dict(interest_outside_cfo=True, debt_scope="ALL_EXISTING_TERMINAL_DEBT"),
    )
    return data


def test_constant_debt_tail_deducts_interest_and_reconciles_without_net_financing():
    data = financed_inputs()
    before = deepcopy(data)
    value = compile_direct_owner_cash_path(**data)
    assert data == before
    assert D(value["terminal_steady_distribution_cny"]) == 70
    assert D(value["terminal_equity_value_cny"]) == 875
    assert abs(D(value["crosscheck_difference_cny"])) < D("1e-30")
    assert D(value["conditional_equity_value_cny"]) < 1000
    row = value["terminal_rows"][0]
    assert row["opening_debt_cny"] == row["closing_debt_cny"] == "200"
    assert D(row["net_cash_before_distribution_cny"]) == 70
    assert row["cash_policy"]["interest_outside_cfo"] == "10"
    assert value["terminal_financing"]["net_new_borrowing_cny"] == "0"
    assert value["terminal_financing"]["classification"] == "FORECAST_ASSUMPTION"
    assert value["terminal_financing"]["actual_refinancing_guaranteed"] is False
    assert value["formal_eligibility"] is False and value["action"] == "no_order"


@pytest.mark.parametrize("amount", ["0", "1", "50", "200"])
def test_equal_rollover_does_not_change_distribution_value(amount):
    data = financed_inputs()
    expected = compile_direct_owner_cash_path(**data)
    data["terminal"]["policy"].update(new_borrowing=amount, debt_repayment=amount)
    actual = compile_direct_owner_cash_path(**data)
    assert actual["conditional_equity_value_cny"] == expected["conditional_equity_value_cny"]
    assert actual["terminal_steady_distribution_cny"] == expected["terminal_steady_distribution_cny"]


@pytest.mark.parametrize("fault,reason", [
    ("missing", "EXACT_TERMINAL_FINANCING"), ("null", "EXACT_TERMINAL_FINANCING"),
    ("mode", "FINANCING_MODE"), ("extra", "EXACT_TERMINAL_FINANCING"),
    ("rationale", "FINANCING_EXPLANATION"), ("counter_evidence", "FINANCING_EXPLANATION"),
    ("reopen_condition", "FINANCING_EXPLANATION"), ("coverage", "FINANCING_COVERAGE"),
    ("in_cfo", "FINANCING_COVERAGE"), ("truthy", "FINANCING_COVERAGE"),
    ("partial", "FINANCING_COVERAGE"), ("zero_debt", "CONSTANT_DEBT"),
    ("increase", "CONSTANT_DEBT"), ("decrease", "CONSTANT_DEBT"),
    ("excess", "CONSTANT_DEBT"), ("zero_interest", "POSITIVE_TERMINAL_CASH_INTEREST"),
    ("events", "UNCONSUMED_FUTURE_EVENTS"), ("commitment", "FINITE_COMMITMENT"),
    ("unfunded", "UNSUPPORTED_STATIONARY"),
])
def test_unsupported_terminal_financing_rejected(fault, reason):
    data = financed_inputs()
    terminal = data["terminal"]
    policy, financing = terminal["policy"], terminal["financing"]
    if fault == "missing": financing.pop("coverage")
    if fault == "null": terminal["financing"] = None
    if fault == "mode": financing["mode"] = "GUARANTEED"
    if fault == "extra": financing["guaranteed"] = True
    if fault in ("rationale", "counter_evidence", "reopen_condition"): financing[fault] = " "
    if fault == "coverage": financing["coverage"] = {}
    if fault == "in_cfo": financing["coverage"]["interest_outside_cfo"] = False
    if fault == "truthy": financing["coverage"]["interest_outside_cfo"] = 1
    if fault == "partial": financing["coverage"]["debt_scope"] = "SELECTED_DEBT"
    if fault == "zero_debt": data["opening"]["debt"] = "0"
    if fault == "increase": policy["new_borrowing"] = "51"
    if fault == "decrease": policy["new_borrowing"] = "49"
    if fault == "excess": policy.update(new_borrowing="201", debt_repayment="201")
    if fault == "zero_interest": policy["interest_outside_cfo"] = "0"
    if fault == "events": terminal["remaining_scheduled_events"] = [2030]
    if fault == "commitment": policy["commitments_outside_capex"] = "1"
    if fault == "unfunded": policy["interest_outside_cfo"] = "101"
    with pytest.raises(ValueError, match=reason):
        compile_direct_owner_cash_path(**data)


def test_default_zero_debt_stays_unchanged_and_context_is_local():
    plain = compile_direct_owner_cash_path(**inputs())
    assert "terminal_financing" not in plain
    assert D(plain["conditional_equity_value_cny"]) == 1000
    data = financed_inputs()
    expected = compile_direct_owner_cash_path(**data)
    with localcontext() as context:
        context.prec = 5
        assert compile_direct_owner_cash_path(**data) == expected
        assert context.prec == 5
    data["terminal"].pop("financing")
    with pytest.raises(ValueError, match="TERMINAL_DEBT_POLICY_UNSUPPORTED"):
        compile_direct_owner_cash_path(**data)


def test_model_adapter_shared_service_and_bundle_keep_financing_contract():
    from test_direct_owner_cash_v1 import scenario
    from test_direct_owner_cash_input_adapter_v1 import package, NOW
    from value_investment_agent.valuation_models.direct_owner_cash_v1 import scenario_to_payload, facts_from_payload
    from value_investment_agent.application.research.direct_owner_cash_input_adapter_v1 import (
        run_direct_owner_cash_research, descriptor_from_payload, DirectOwnerCashResearchRepository,
    )
    from value_investment_agent.research_artifacts import SCOPE_SECURITY, ARTIFACT_FINANCIAL_FACTS
    from value_investment_agent.application.product.company_research import _serialize_outcome
    import json

    p = package()
    for name, cost in zip(("bear", "base", "bull"), (".10", ".08", ".06")):
        p["facts"]["scenario_inputs"][name] = scenario_to_payload(scenario(cost, data=financed_inputs()))
    repo = DirectOwnerCashResearchRepository()
    outcome, desc = run_direct_owner_cash_research(p, NOW, repository=repo)
    assert outcome.valuation.base_value < 10
    restored = descriptor_from_payload(desc.as_policy())
    assert restored.input_sha256 == desc.input_sha256
    saved = repo.load_latest(SCOPE_SECURITY, desc.symbol, ARTIFACT_FINANCIAL_FACTS)
    financial = facts_from_payload(saved.envelope.payload_object())
    assert financial.scenario_inputs["base"].terminal["financing"] == financed_inputs()["terminal"]["financing"]
    bundle = _serialize_outcome(outcome)["artifact_bundle"]
    row = next(x for x in bundle["artifacts"] if x["identity"]["artifact_type"] == ARTIFACT_FINANCIAL_FACTS)
    assert json.loads(row["canonical_payload"])["scenario_inputs"]["base"]["terminal"]["financing"] == financed_inputs()["terminal"]["financing"]
