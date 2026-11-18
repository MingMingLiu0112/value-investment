"""Versioned direct-owner-cash model with explicit scheduled distributions.

The v1 adapter remains immutable.  V2 delegates every cash, clean-surplus and
terminal calculation to ``direct_parent_owner_cash_v2`` and only projects that
deterministic result into the existing valuation service contract.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, fields, replace
from decimal import Decimal, localcontext
from typing import Any

from ..domain.valuation.direct_parent_owner_cash_v2 import compile_direct_owner_cash_path
from ..research_case import ResearchCase
from ..valuation_confidence import evaluate_confidence
from .base import ValuationResult, merge_evidence_refs
from .direct_owner_cash_v1 import (
    DirectOwnerCashScenario as _V1Scenario,
    MODEL_ID,
    REQUIRED_INPUTS,
    SCENARIOS,
)
from .residual_income import QualityCompounderFacts

MODEL_VERSION = "direct-owner-cash-equity-v2"
SCENARIO_CONTRACT = "direct-owner-cash-scenario-v2"


@dataclass(frozen=True)
class DirectOwnerCashScenario(_V1Scenario):
    """V2 scenario; annual policies may include scheduled owner cash."""


def _json_numbers(value: Any) -> Any:
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("DIRECT_OWNER_V2_FINITE_DECIMALS_REQUIRED")
        return str(value)
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("DIRECT_OWNER_V2_STRING_KEYS_REQUIRED")
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("DIRECT_OWNER_V2_JSON_INPUT_REQUIRED")


def scenario_to_payload(scenario: DirectOwnerCashScenario) -> dict[str, Any]:
    if not isinstance(scenario, DirectOwnerCashScenario):
        raise TypeError("DIRECT_OWNER_V2_TYPED_SCENARIO_REQUIRED")
    scenario = replace(scenario)
    return {
        "scenario_contract": SCENARIO_CONTRACT,
        "symbol": scenario.symbol,
        "scope": scenario.scope,
        "currency": scenario.currency,
        "ordinary_shares": str(scenario.ordinary_shares),
        "cost_of_equity": str(scenario.cost_of_equity),
        "forecast_roes": [str(item) for item in scenario.forecast_roes],
        "forecast_retentions": [str(item) for item in scenario.forecast_retentions],
        "opening": _json_numbers(scenario.opening),
        "years": _json_numbers(scenario.years),
        "terminal": _json_numbers(scenario.terminal),
    }


def scenario_from_payload(payload: dict[str, Any]) -> DirectOwnerCashScenario:
    expected = {
        "scenario_contract", "symbol", "scope", "currency", "ordinary_shares",
        "cost_of_equity", "forecast_roes", "forecast_retentions", "opening",
        "years", "terminal",
    }
    if (not isinstance(payload, dict) or set(payload) != expected
            or payload.get("scenario_contract") != SCENARIO_CONTRACT):
        raise ValueError("DIRECT_OWNER_V2_EXACT_SCENARIO_PAYLOAD_REQUIRED")

    def number(value: Any) -> Decimal:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("DIRECT_OWNER_V2_DECIMAL_STRING_REQUIRED")
        result = Decimal(value)
        if not result.is_finite():
            raise ValueError("DIRECT_OWNER_V2_FINITE_DECIMALS_REQUIRED")
        return result

    if any(not isinstance(payload[key], list) for key in ("forecast_roes", "forecast_retentions")):
        raise ValueError("DIRECT_OWNER_V2_ANNUAL_VECTORS_REQUIRED")
    return DirectOwnerCashScenario(
        symbol=payload["symbol"], scope=payload["scope"], currency=payload["currency"],
        ordinary_shares=number(payload["ordinary_shares"]),
        cost_of_equity=number(payload["cost_of_equity"]),
        forecast_roes=tuple(number(item) for item in payload["forecast_roes"]),
        forecast_retentions=tuple(number(item) for item in payload["forecast_retentions"]),
        opening=deepcopy(payload["opening"]), years=deepcopy(payload["years"]),
        terminal=deepcopy(payload["terminal"]),
    )


def facts_to_payload(facts: QualityCompounderFacts) -> dict[str, Any]:
    from ..research_input import facts_to_payload as legacy_to_payload

    if (not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs
            or set(facts.scenario_inputs) != set(SCENARIOS)
            or any(not isinstance(item, DirectOwnerCashScenario)
                   for item in facts.scenario_inputs.values())):
        raise TypeError("DIRECT_OWNER_V2_TYPED_FACTS_REQUIRED")
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_V2_VALUATION_TIMING_UNSUPPORTED")
    result = legacy_to_payload(replace(facts, scenario_inputs=None))
    result["direct_owner_cash_contract"] = MODEL_VERSION
    result["scenario_inputs"] = {
        name: scenario_to_payload(facts.scenario_inputs[name]) for name in SCENARIOS
    }
    return result


def facts_from_payload(payload: dict[str, Any]) -> QualityCompounderFacts:
    from ..research_input import facts_from_payload as legacy_from_payload

    if (not isinstance(payload, dict)
            or payload.get("direct_owner_cash_contract") != MODEL_VERSION
            or payload.get("facts_type") != "quality_compounder"):
        raise ValueError("DIRECT_OWNER_V2_FACTS_PAYLOAD_REQUIRED")
    data = deepcopy(payload)
    data.pop("direct_owner_cash_contract")
    scenarios = data.get("scenario_inputs")
    if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIOS):
        raise ValueError("DIRECT_OWNER_V2_EXACT_SCENARIOS_REQUIRED")
    data["scenario_inputs"] = None
    facts = replace(legacy_from_payload(data), scenario_inputs={
        name: scenario_from_payload(scenarios[name]) for name in SCENARIOS
    })
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_V2_VALUATION_TIMING_UNSUPPORTED")
    return facts


def _decimal(row: dict[str, Any], key: str) -> Decimal:
    try:
        value = Decimal(row[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("DIRECT_OWNER_V2_RESULT_FIELD_REQUIRED:" + key) from exc
    if not value.is_finite():
        raise ValueError("DIRECT_OWNER_V2_FINITE_RESULT_REQUIRED:" + key)
    return value


def scenario_calculation(
    facts: QualityCompounderFacts, scenario: DirectOwnerCashScenario,
) -> dict[str, Any]:
    if not isinstance(scenario, DirectOwnerCashScenario):
        raise TypeError("DIRECT_OWNER_V2_TYPED_SCENARIO_REQUIRED")
    scenario = replace(scenario)
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_V2_VALUATION_TIMING_UNSUPPORTED")
    if scenario.symbol != facts.symbol:
        raise ValueError("DIRECT_OWNER_V2_SCENARIO_SYMBOL_MISMATCH")
    for name in REQUIRED_INPUTS:
        value = facts.operating_inputs.get(name)
        if (not isinstance(value, Decimal) or not value.is_finite()
                or value < 0 or (name != "opening_cash" and value == 0)):
            raise ValueError("DIRECT_OWNER_V2_FACT_BASIS_INVALID:" + name)
    result = compile_direct_owner_cash_path(
        opening=deepcopy(scenario.opening), years=deepcopy(scenario.years),
        terminal=deepcopy(scenario.terminal), ordinary_shares=scenario.ordinary_shares,
        cost_of_equity=scenario.cost_of_equity, scope=scenario.scope,
        currency=scenario.currency,
    )
    rows = result["annual_rows"]
    first = rows[0]
    for fact_key, actual in (
        ("start_book_equity", _decimal(first, "opening_book_equity_cny")),
        ("opening_cash", _decimal(first, "opening_cash_cny")),
        ("ordinary_shares", Decimal(result["ordinary_shares"])),
    ):
        if facts.operating_inputs[fact_key] != actual:
            raise ValueError("DIRECT_OWNER_V2_FACT_BASIS_MISMATCH:" + fact_key)
    for fact_key, row_key in (
        ("opening_debt", "opening_debt_cny"),
        ("opening_distribution_capacity", "opening_distribution_capacity_cny"),
    ):
        if fact_key in facts.operating_inputs and facts.operating_inputs[fact_key] != _decimal(first, row_key):
            raise ValueError("DIRECT_OWNER_V2_FACT_BASIS_MISMATCH:" + fact_key)
    actual_roes = tuple(_decimal(row, "roe_assumption") for row in rows)
    actual_retentions = tuple(_decimal(row, "retention_assumption") for row in rows)
    if actual_roes != scenario.forecast_roes:
        raise ValueError("DIRECT_OWNER_V2_ANNUAL_VECTOR_MISMATCH:forecast_roes")
    if actual_retentions != scenario.forecast_retentions:
        raise ValueError("DIRECT_OWNER_V2_ANNUAL_VECTOR_MISMATCH:forecast_retentions")
    for row in rows:
        scheduled = _decimal(row, "scheduled_owner_distribution_cny")
        conditional = _decimal(row, "conditional_distribution_cny")
        total = _decimal(row, "total_owner_distribution_cny")
        if scheduled < 0 or conditional < 0 or total != scheduled + conditional:
            raise ValueError("DIRECT_OWNER_V2_DISTRIBUTION_RECONCILIATION_FAILED")
        with localcontext() as context:
            context.prec = 48
            profit = _decimal(row, "net_income_assumption_cny")
            opening_book = _decimal(row, "opening_book_equity_cny")
            closing_book = _decimal(row, "closing_book_equity_cny")
            if closing_book != opening_book + profit - total:
                raise ValueError("DIRECT_OWNER_V2_CLEAN_SURPLUS_FAILED")
            expected_retention = (profit - total) / profit
            if _decimal(row, "retention_assumption") != expected_retention:
                raise ValueError("DIRECT_OWNER_V2_RETENTION_RECALCULATION_FAILED")
            if _decimal(row, "roe_assumption") != profit / opening_book:
                raise ValueError("DIRECT_OWNER_V2_ROE_RECALCULATION_FAILED")
    return result


@dataclass(frozen=True)
class DirectOwnerCashValuationModel:
    model_type: str = MODEL_ID

    def value(self, facts: QualityCompounderFacts, case: ResearchCase) -> ValuationResult:
        if not isinstance(facts, QualityCompounderFacts) or not isinstance(case, ResearchCase):
            raise TypeError("DIRECT_OWNER_V2_TYPED_FACTS_AND_CASE_REQUIRED")
        if facts.symbol != case.symbol:
            raise ValueError("Quality-compounder facts and research case symbols must match")
        refs = merge_evidence_refs(facts.evidence_refs, case.evidence_refs)
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *([] if facts.verified else ["financial_facts_not_verified"]),
            *("quality_compounder_input_missing:" + name for name in REQUIRED_INPUTS
              if facts.operating_inputs.get(name) is None),
        ]))
        scenarios = facts.scenario_inputs
        if not scenarios or set(scenarios) != set(SCENARIOS):
            blockers.append("quality_compounder_scenarios_must_contain_exactly_bear_base_bull")
        elif any(not isinstance(item, DirectOwnerCashScenario) for item in scenarios.values()):
            blockers.append("direct_owner_cash_v2_scenario_inputs_must_be_typed")
        if not refs:
            raise ValueError("Quality-compounder research requires named evidence references")
        if blockers:
            return ValuationResult(
                symbol=case.symbol, model_type=self.model_type, valuation_date=facts.as_of,
                bear_value=None, base_value=None, bull_value=None, confidence=facts.confidence,
                assumptions={"scope": "direct owner cash v2 verified input gate"},
                sensitivities=[], evidence_refs=refs, blockers=blockers, status="not_ready",
                model_version=MODEL_VERSION,
            )
        calculations = {name: scenario_calculation(facts, scenarios[name]) for name in SCENARIOS}
        baseline = calculations["bear"]["annual_rows"][0]
        basis_keys = ("opening_book_equity_cny", "opening_cash_cny", "opening_debt_cny",
                      "opening_distribution_capacity_cny")
        years = [row["year"] for row in calculations["bear"]["annual_rows"]]
        for calculation in calculations.values():
            first = calculation["annual_rows"][0]
            if any(_decimal(first, key) != _decimal(baseline, key) for key in basis_keys):
                raise ValueError("DIRECT_OWNER_V2_SCENARIO_OPENING_STATE_MISMATCH")
            if [row["year"] for row in calculation["annual_rows"]] != years:
                raise ValueError("DIRECT_OWNER_V2_SCENARIO_YEARS_MISMATCH")
        values = {name: Decimal(calculations[name]["per_share_value"]) for name in SCENARIOS}
        if not values["bear"] <= values["base"] <= values["bull"]:
            raise ValueError("Scenario values must be bear <= base <= bull")
        assessment = (evaluate_confidence(facts.confidence_evidence)
                      if facts.confidence_evidence is not None else None)
        return ValuationResult(
            symbol=case.symbol, model_type=self.model_type, valuation_date=facts.as_of,
            bear_value=values["bear"], base_value=values["base"], bull_value=values["bull"],
            confidence=assessment.confidence if assessment else facts.confidence,
            assumptions={
                "scope": "conditional parent direct-CFO owner distributions v2",
                "status": "conditional_research_only", "action": "no_order",
                "formal_eligibility": False,
                "legal_distribution_capacity_certified": False,
                "valuation_timing": "BASIS_DATE_ONLY_NO_ROLL_FORWARD",
                "scenario_calculations": calculations,
                **({"confidence_assessment": assessment.as_policy()} if assessment else {}),
            },
            sensitivities=[{
                "scenario": name,
                "cost_of_equity": calculation["cost_of_equity"],
                "ordinary_equity_value": calculation["conditional_equity_value_cny"],
                "per_share_value": calculation["per_share_value"],
                "dividend_crosscheck_difference": calculation["crosscheck_difference_cny"],
                "arithmetic_status": "research_arithmetic_only",
            } for name, calculation in calculations.items()],
            evidence_refs=refs, blockers=[], status="conditional_research_only",
            model_version=MODEL_VERSION,
        )


def build_direct_owner_cash_router():
    """Opt-in router for the shared ResearchApplicationService."""
    from ..valuation_router import ValuationModelRegistration, ValuationModelRegistry, ValuationRouter

    return ValuationRouter(registry=ValuationModelRegistry((ValuationModelRegistration(
        model_id=MODEL_ID, model_type=MODEL_ID, model_factory=DirectOwnerCashValuationModel,
        facts_contract=QualityCompounderFacts,
        required_inputs=(*REQUIRED_INPUTS, "scenario_inputs"),
    ),)))
