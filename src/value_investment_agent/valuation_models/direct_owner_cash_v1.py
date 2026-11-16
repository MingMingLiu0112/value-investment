"""Explicit direct-CFO valuation adapter; no global registration or cash formulas.

The V2 ancestry is only a shared-spec compatibility contract. Annual ROEs and
retentions must equal the compiler's actual rows, not averages. Legacy terminal
ROE/growth are zero sentinels, never terminal valuation inputs. Source binding
and versioned descriptor serialization belong to the caller's E2 adapter.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from decimal import Decimal
import re
from typing import Any

from ..domain.valuation.direct_parent_owner_cash_v1 import compile_direct_owner_cash_path
from ..domain.valuation.parent_direct_operating_cash import SCOPE
from ..research_case import ResearchCase
from ..valuation_confidence import evaluate_confidence
from .base import ValuationResult, merge_evidence_refs
from .residual_income import QualityCompounderFacts
from .residual_income_path_v2 import ResidualIncomePathScenarioInputs

MODEL_VERSION = "direct-owner-cash-equity-v1"
MODEL_ID = "residual_income_or_equity_value"
SCENARIO_CONTRACT = "direct-owner-cash-scenario-v1"
SCENARIOS = ("bear", "base", "bull")
REQUIRED_INPUTS = ("start_book_equity", "ordinary_shares", "opening_cash")


@dataclass(frozen=True)
class DirectOwnerCashScenario(ResidualIncomePathScenarioInputs):
    """Compiler arguments plus exact annual projections for the shared spec.

    ``opening``, ``years`` and ``terminal`` have the domain compiler's exact
    schemas. ``ordinary_shares`` and the opening book/cash must match facts;
    all three scenarios must share the complete opening state and year labels.
    ``terminal_roe``/``terminal_growth`` must remain zero (not Gordon inputs).
    """

    terminal_roe: Decimal = Decimal(0)
    terminal_growth: Decimal = Decimal(0)
    symbol: str = field(kw_only=True)
    opening: dict[str, Any] = field(kw_only=True)
    years: list[dict[str, Any]] = field(kw_only=True)
    terminal: dict[str, Any] = field(kw_only=True)
    ordinary_shares: Decimal = field(kw_only=True)
    scope: str = field(default=SCOPE, kw_only=True)

    def __post_init__(self) -> None:
        # Do not call V2's Gordon-growth arithmetic: this is a distinct terminal.
        if not isinstance(self.symbol, str) or not re.fullmatch(r"[0-9]{6}", self.symbol):
            raise ValueError("DIRECT_OWNER_SCENARIO_SYMBOL_INVALID")
        if self.scope != SCOPE or self.currency != "CNY":
            raise ValueError("DIRECT_OWNER_PARENT_CNY_REQUIRED")
        if (not isinstance(self.forecast_roes, tuple)
                or not isinstance(self.forecast_retentions, tuple)
                or not self.forecast_roes
                or len(self.forecast_roes) != len(self.forecast_retentions)):
            raise ValueError("DIRECT_OWNER_ANNUAL_VECTORS_REQUIRED")
        numbers = (self.cost_of_equity, self.ordinary_shares, self.retention,
                   self.terminal_roe, self.terminal_growth,
                   *self.forecast_roes, *self.forecast_retentions)
        if any(not isinstance(x, Decimal) or not x.is_finite() for x in numbers):
            raise ValueError("DIRECT_OWNER_FINITE_DECIMALS_REQUIRED")
        if (not 0 < self.cost_of_equity < 1 or self.ordinary_shares <= 0
                or self.ordinary_shares != self.ordinary_shares.to_integral_value()):
            raise ValueError("DIRECT_OWNER_SHARES_OR_COST_INVALID")
        if (self.retention != Decimal("0.30") or self.terminal_roe != 0
                or self.terminal_growth != 0):
            raise ValueError("DIRECT_OWNER_LEGACY_FIELDS_ARE_SENTINELS")
        if (any(x <= 0 for x in self.forecast_roes)
                or any(not 0 <= x <= 1 for x in self.forecast_retentions)):
            raise ValueError("DIRECT_OWNER_ANNUAL_VECTOR_RANGE_INVALID")
        if (not isinstance(self.opening, dict) or not isinstance(self.terminal, dict)
                or not isinstance(self.years, list)
                or len(self.years) != len(self.forecast_roes)):
            raise ValueError("DIRECT_OWNER_COMPILER_INPUTS_REQUIRED")
        for name in ("opening", "years", "terminal"):
            object.__setattr__(self, name, deepcopy(getattr(self, name)))


def _json_numbers(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("DIRECT_OWNER_FINITE_DECIMALS_REQUIRED")
        return str(value)
    if isinstance(value, dict):
        return {key: _json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_numbers(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("DIRECT_OWNER_JSON_INPUT_REQUIRED")


def scenario_to_payload(scenario: DirectOwnerCashScenario) -> dict[str, Any]:
    """Lossless versioned economic inputs; never use the inherited V2 serializer."""
    if not isinstance(scenario, DirectOwnerCashScenario):
        raise TypeError("DIRECT_OWNER_TYPED_SCENARIO_REQUIRED")
    scenario = replace(scenario)  # Revalidate and detach mutable input containers.
    return dict(
        scenario_contract=SCENARIO_CONTRACT, symbol=scenario.symbol,
        scope=scenario.scope, currency=scenario.currency,
        ordinary_shares=str(scenario.ordinary_shares), cost_of_equity=str(scenario.cost_of_equity),
        forecast_roes=[str(x) for x in scenario.forecast_roes],
        forecast_retentions=[str(x) for x in scenario.forecast_retentions],
        opening=_json_numbers(scenario.opening), years=_json_numbers(scenario.years),
        terminal=_json_numbers(scenario.terminal),
    )


def scenario_from_payload(payload: dict[str, Any]) -> DirectOwnerCashScenario:
    expected = {"scenario_contract", "symbol", "scope", "currency", "ordinary_shares",
                "cost_of_equity", "forecast_roes", "forecast_retentions", "opening", "years", "terminal"}
    if (not isinstance(payload, dict) or set(payload) != expected
            or payload["scenario_contract"] != SCENARIO_CONTRACT):
        raise ValueError("DIRECT_OWNER_EXACT_SCENARIO_PAYLOAD_REQUIRED")

    def number(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("DIRECT_OWNER_DECIMAL_STRING_REQUIRED")
        result = Decimal(value)
        if not result.is_finite():
            raise ValueError("DIRECT_OWNER_FINITE_DECIMALS_REQUIRED")
        return result

    if any(not isinstance(payload[key], list) for key in ("forecast_roes", "forecast_retentions")):
        raise ValueError("DIRECT_OWNER_ANNUAL_VECTORS_REQUIRED")
    return DirectOwnerCashScenario(
        symbol=payload["symbol"], scope=payload["scope"], currency=payload["currency"],
        ordinary_shares=number(payload["ordinary_shares"]),
        cost_of_equity=number(payload["cost_of_equity"]),
        forecast_roes=tuple(number(x) for x in payload["forecast_roes"]),
        forecast_retentions=tuple(number(x) for x in payload["forecast_retentions"]),
        opening=deepcopy(payload["opening"]), years=deepcopy(payload["years"]),
        terminal=deepcopy(payload["terminal"]),
    )


def facts_to_payload(facts: QualityCompounderFacts) -> dict[str, Any]:
    """For explicit codec/repository injection, not the global frozen codec."""
    from ..research_input import facts_to_payload as legacy_to_payload

    if (not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs
            or set(facts.scenario_inputs) != set(SCENARIOS)
            or any(not isinstance(x, DirectOwnerCashScenario) for x in facts.scenario_inputs.values())):
        raise TypeError("DIRECT_OWNER_TYPED_FACTS_REQUIRED")
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_VALUATION_TIMING_UNSUPPORTED")
    result = legacy_to_payload(replace(facts, scenario_inputs=None))
    result["direct_owner_cash_contract"] = MODEL_VERSION
    result["scenario_inputs"] = {name: scenario_to_payload(facts.scenario_inputs[name]) for name in SCENARIOS}
    return result


def facts_from_payload(payload: dict[str, Any]) -> QualityCompounderFacts:
    from ..research_input import facts_from_payload as legacy_from_payload

    if (not isinstance(payload, dict)
            or payload.get("direct_owner_cash_contract") != MODEL_VERSION
            or payload.get("facts_type") != "quality_compounder"):
        raise ValueError("DIRECT_OWNER_FACTS_PAYLOAD_REQUIRED")
    data = deepcopy(payload)
    data.pop("direct_owner_cash_contract")
    scenarios = data.get("scenario_inputs")
    if not isinstance(scenarios, dict) or set(scenarios) != set(SCENARIOS):
        raise ValueError("DIRECT_OWNER_EXACT_SCENARIOS_REQUIRED")
    data["scenario_inputs"] = None
    facts = replace(legacy_from_payload(data), scenario_inputs={
        name: scenario_from_payload(scenarios[name]) for name in SCENARIOS})
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_VALUATION_TIMING_UNSUPPORTED")
    return facts


def scenario_calculation(
    facts: QualityCompounderFacts, scenario: DirectOwnerCashScenario,
) -> dict[str, Any]:
    """Delegate all cash, terminal and RI arithmetic, then check exact vectors."""
    if not isinstance(scenario, DirectOwnerCashScenario):
        raise TypeError("DIRECT_OWNER_TYPED_SCENARIO_REQUIRED")
    scenario = replace(scenario)
    if facts.valuation_timing is not None:
        raise ValueError("DIRECT_OWNER_VALUATION_TIMING_UNSUPPORTED")
    if scenario.symbol != facts.symbol:
        raise ValueError("DIRECT_OWNER_SCENARIO_SYMBOL_MISMATCH")
    for name in REQUIRED_INPUTS:
        value = facts.operating_inputs.get(name)
        if (not isinstance(value, Decimal) or not value.is_finite()
                or value < 0 or name != "opening_cash" and value == 0):
            raise ValueError("DIRECT_OWNER_FACT_BASIS_INVALID:" + name)
    result = compile_direct_owner_cash_path(
        opening=deepcopy(scenario.opening), years=deepcopy(scenario.years),
        terminal=deepcopy(scenario.terminal), ordinary_shares=scenario.ordinary_shares,
        cost_of_equity=scenario.cost_of_equity, scope=scenario.scope,
        currency=scenario.currency,
    )
    first = result["annual_rows"][0]
    for fact_key, actual in (
        ("start_book_equity", first["opening_book_equity_cny"]),
        ("opening_cash", first["opening_cash_cny"]),
        ("ordinary_shares", result["ordinary_shares"]),
    ):
        if facts.operating_inputs[fact_key] != Decimal(actual):
            raise ValueError("DIRECT_OWNER_FACT_BASIS_MISMATCH:" + fact_key)
    for fact_key, row_key in (
        ("opening_debt", "opening_debt_cny"),
        ("opening_distribution_capacity", "opening_distribution_capacity_cny"),
    ):
        if fact_key in facts.operating_inputs:
            value = facts.operating_inputs[fact_key]
            if (not isinstance(value, Decimal) or not value.is_finite()
                    or value != Decimal(first[row_key])):
                raise ValueError("DIRECT_OWNER_FACT_BASIS_MISMATCH:" + fact_key)
    for field_name, row_key in (
        ("forecast_roes", "roe_assumption"),
        ("forecast_retentions", "retention_assumption"),
    ):
        actual = tuple(Decimal(row[row_key]) for row in result["annual_rows"])
        if actual != getattr(scenario, field_name):
            raise ValueError("DIRECT_OWNER_ANNUAL_VECTOR_MISMATCH:" + field_name)
    return result


@dataclass(frozen=True)
class DirectOwnerCashValuationModel:
    model_type: str = MODEL_ID

    def value(self, facts: QualityCompounderFacts, case: ResearchCase) -> ValuationResult:
        if not isinstance(facts, QualityCompounderFacts) or not isinstance(case, ResearchCase):
            raise TypeError("DIRECT_OWNER_TYPED_FACTS_AND_CASE_REQUIRED")
        if facts.symbol != case.symbol:
            raise ValueError("Quality-compounder facts and research case symbols must match")
        if facts.confidence not in {"高", "中", "低"}:
            raise ValueError("Quality-compounder confidence must be 高, 中 or 低")
        if facts.valuation_timing is not None:
            raise ValueError("DIRECT_OWNER_VALUATION_TIMING_UNSUPPORTED")
        refs = merge_evidence_refs(facts.evidence_refs, case.evidence_refs)
        if not refs:
            raise ValueError("Quality-compounder research requires named evidence references")
        blockers = list(dict.fromkeys([
            *facts.blockers,
            *(["financial_facts_not_verified"] if not facts.verified else []),
            *("quality_compounder_input_missing:" + name for name in REQUIRED_INPUTS
              if facts.operating_inputs.get(name) is None),
        ]))
        scenarios = facts.scenario_inputs
        if not scenarios:
            blockers.append("quality_compounder_scenario_inputs_not_registered")
        else:
            if set(scenarios) != set(SCENARIOS):
                blockers.append("quality_compounder_scenarios_must_contain_exactly_bear_base_bull")
            if any(not isinstance(x, DirectOwnerCashScenario) for x in scenarios.values()):
                blockers.append("direct_owner_cash_scenario_inputs_must_be_typed")
        if blockers:
            return ValuationResult(
                symbol=case.symbol, model_type=self.model_type, valuation_date=facts.as_of,
                bear_value=None, base_value=None, bull_value=None, confidence=facts.confidence,
                assumptions={"scope": "direct owner cash verified input gate"},
                sensitivities=[], evidence_refs=refs, blockers=blockers,
                status="not_ready", model_version=MODEL_VERSION,
            )
        calculations = {name: scenario_calculation(facts, scenarios[name]) for name in SCENARIOS}
        baseline = calculations["bear"]["annual_rows"][0]
        basis_keys = ("opening_book_equity_cny", "opening_cash_cny",
                      "opening_debt_cny", "opening_distribution_capacity_cny")
        years = [row["year"] for row in calculations["bear"]["annual_rows"]]
        for calculation in calculations.values():
            first = calculation["annual_rows"][0]
            if any(Decimal(first[key]) != Decimal(baseline[key]) for key in basis_keys):
                raise ValueError("DIRECT_OWNER_SCENARIO_OPENING_STATE_MISMATCH")
            if [row["year"] for row in calculation["annual_rows"]] != years:
                raise ValueError("DIRECT_OWNER_SCENARIO_YEARS_MISMATCH")
        values = {name: Decimal(calculations[name]["per_share_value"]) for name in SCENARIOS}
        # Never sort/relabel an inverted economic scenario to pass this contract.
        if not values["bear"] <= values["base"] <= values["bull"]:
            raise ValueError("Scenario values must be bear <= base <= bull")
        assessment = (evaluate_confidence(facts.confidence_evidence)
                      if facts.confidence_evidence is not None else None)
        return ValuationResult(
            symbol=case.symbol, model_type=self.model_type, valuation_date=facts.as_of,
            bear_value=values["bear"], base_value=values["base"], bull_value=values["bull"],
            confidence=assessment.confidence if assessment else facts.confidence,
            assumptions={
                "scope": "conditional parent direct-CFO owner distributions",
                "status": "conditional_research_only", "action": "no_order",
                "formal_eligibility": False, "legal_distribution_capacity_certified": False,
                "working_capital_cash_component": None,
                "valuation_timing": "BASIS_DATE_ONLY_NO_ROLL_FORWARD",
                "legacy_terminal_fields": "ZERO_COMPATIBILITY_SENTINELS_NOT_VALUATION_INPUTS",
                "scenario_calculations": calculations,
                **({"confidence_assessment": assessment.as_policy()} if assessment else {}),
            },
            sensitivities=[dict(scenario=name, cost_of_equity=item["cost_of_equity"],
                ordinary_equity_value=item["conditional_equity_value_cny"],
                per_share_value=item["per_share_value"],
                dividend_crosscheck_difference=item["crosscheck_difference_cny"],
                arithmetic_status="research_arithmetic_only")
                for name, item in calculations.items()],
            evidence_refs=refs, blockers=[], status="conditional_research_only",
            model_version=MODEL_VERSION,
        )


def build_direct_owner_cash_router():
    """Opt-in shared-service router; the default registry remains untouched."""
    from ..valuation_router import ValuationModelRegistration, ValuationModelRegistry, ValuationRouter

    return ValuationRouter(registry=ValuationModelRegistry((ValuationModelRegistration(
        model_id=MODEL_ID, model_type=MODEL_ID, model_factory=DirectOwnerCashValuationModel,
        facts_contract=QualityCompounderFacts, required_inputs=(*REQUIRED_INPUTS, "scenario_inputs"),
    ),)))
