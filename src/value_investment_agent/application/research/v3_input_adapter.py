"""Versioned research-input adapter for the economic-terminal RI path.

The legacy research_input module is source-hash bound by historical packages.
This module extends the typed descriptor contract without changing those bytes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping

from ...m1_valuation_package_builder import build_descriptor
from ...research_input import (
    ResearchInputDescriptor, ResearchSourceContract, finalize_input_descriptor,
)
from ...valuation_models.residual_income import QualityCompounderFacts
from ...valuation_models.residual_income_path_v2 import (
    ResidualIncomePathScenarioInputs as V2Scenario,
)
from ...valuation_models.residual_income_path_v3 import (
    ResidualIncomePathScenarioInputs as V3Scenario,
)
from ...domain.valuation.joint_capital_cash_path_v3 import TerminalEconomicContract


MODEL_VERSION = "residual-income-equity-path-v3"
RETENTION_CONTRACT = "annual-retention-v3-economic-terminal"
TERMINAL_CONTRACT_VERSION = "terminal-economic-contract-v1"
TERMINAL_MECHANISM = "recursive_capital_use_and_owner_distribution"
PROPOSAL_SCHEMA = "joint-capital-cash-path-proposal-v3"


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} requires a plain Decimal string")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def terminal_contract_payload(value: TerminalEconomicContract) -> dict[str, Any]:
    if not isinstance(value, TerminalEconomicContract):
        raise TypeError("typed v3 terminal economic contract required")
    return {
        "contract_version": TERMINAL_CONTRACT_VERSION,
        "terminal_mechanism": TERMINAL_MECHANISM,
        "terminal_start_year": 11,
        "first_distribution_timing": "end_of_terminal_year_1",
        "legacy_profit_dynamics": "constant_after_profit_scale_transition",
        "opening_book": str(value.opening_book),
        "opening_cash": str(value.opening_cash),
        "opening_unremitted": str(value.opening_unremitted),
        "opening_distribution_capacity": str(value.opening_distribution_capacity),
        "opening_operating_capital": str(value.opening_operating_capital),
        "opening_productive_capital": str(value.opening_productive_capital),
        "opening_cash_reference": str(value.opening_cash_reference),
        "cash_floor": str(value.cash_floor),
        "legacy_profit": str(value.legacy_profit),
        "operating_allocation": str(value.operating_allocation),
        "productive_marginal_return": str(value.productive_marginal_return),
        "liquidity_return": str(value.liquidity_return),
        "policy": {name: str(amount) for name, amount in value.policy},
        "commitment_occurrences": value.commitment_occurrences,
        "restricted_cash_release_cny": str(value.restricted_cash_release_cny),
        "restricted_cash_release_year": value.restricted_cash_release_year,
        "convergence_tolerance_cny": str(value.convergence_tolerance_cny),
        "max_tail_years": value.max_tail_years,
        "rationale": value.rationale,
    }


_TERMINAL_KEYS = frozenset(terminal_contract_payload(TerminalEconomicContract(
    opening_book=Decimal("1"), opening_cash=Decimal("0"),
    opening_unremitted=Decimal("0"), opening_distribution_capacity=Decimal("0"),
    opening_operating_capital=Decimal("1"), opening_productive_capital=Decimal("0"),
    opening_cash_reference=Decimal("0"), cash_floor=Decimal("0"),
    legacy_profit=Decimal("1"), operating_allocation=Decimal("0"),
    productive_marginal_return=Decimal("0"), liquidity_return=Decimal("0"),
    policy=(("target_payout_ratio", Decimal("1")),
            ("accessible_profit_ratio", Decimal("1")),
            ("reserve_ratio", Decimal("0")),
            ("net_maintenance_cash_cny", Decimal("0")),
            ("operating_wc_cash_cny", Decimal("0")),
            ("commitment_cash_cny", Decimal("0"))),
    commitment_occurrences=0, restricted_cash_release_cny=Decimal("0"),
    restricted_cash_release_year=None, convergence_tolerance_cny=Decimal("0.01"),
    max_tail_years=1000, rationale="schema sentinel",
)).keys())


def terminal_contract_from_payload(value: Mapping[str, Any]) -> TerminalEconomicContract:
    data = dict(value)
    if set(data) != _TERMINAL_KEYS:
        raise ValueError("exact v3 terminal economic contract fields required")
    if (data["contract_version"] != TERMINAL_CONTRACT_VERSION
            or data["terminal_mechanism"] != TERMINAL_MECHANISM
            or data["terminal_start_year"] != 11
            or data["first_distribution_timing"] != "end_of_terminal_year_1"
            or data["legacy_profit_dynamics"] != "constant_after_profit_scale_transition"):
        raise ValueError("unsupported v3 terminal economic mechanism")
    policy = data["policy"]
    expected_policy = {
        "target_payout_ratio", "accessible_profit_ratio", "reserve_ratio",
        "net_maintenance_cash_cny", "operating_wc_cash_cny", "commitment_cash_cny",
    }
    if not isinstance(policy, Mapping) or set(policy) != expected_policy:
        raise ValueError("exact v3 terminal cash policy required")
    for key in ("commitment_occurrences", "restricted_cash_release_year"):
        if data[key] is not None and (type(data[key]) is not int or data[key] < 0):
            raise ValueError(f"{key} must be a nonnegative integer or null")
    if type(data["max_tail_years"]) is not int or data["max_tail_years"] <= 0:
        raise ValueError("max_tail_years must be a positive integer")
    if not isinstance(data["rationale"], str) or not data["rationale"].strip():
        raise ValueError("terminal rationale is required")
    return TerminalEconomicContract(
        **{key: _decimal(data[key], key) for key in (
            "opening_book", "opening_cash", "opening_unremitted",
            "opening_distribution_capacity", "opening_operating_capital",
            "opening_productive_capital", "opening_cash_reference", "cash_floor",
            "legacy_profit", "operating_allocation", "productive_marginal_return",
            "liquidity_return", "restricted_cash_release_cny",
            "convergence_tolerance_cny")},
        policy=tuple((key, _decimal(policy[key], f"policy.{key}")) for key in sorted(policy)),
        commitment_occurrences=data["commitment_occurrences"],
        restricted_cash_release_year=data["restricted_cash_release_year"],
        max_tail_years=data["max_tail_years"], rationale=data["rationale"].strip(),
    )


def scenario_payload(value: V3Scenario) -> dict[str, Any]:
    if not isinstance(value, V3Scenario) or value.terminal_economic_contract is None:
        raise TypeError("typed v3 residual-income scenario required")
    return {
        "retention_contract": RETENTION_CONTRACT,
        "currency": value.currency,
        "cost_of_equity": str(value.cost_of_equity),
        "forecast_roes": [str(item) for item in value.forecast_roes],
        "forecast_retentions": [str(item) for item in value.forecast_retentions],
        "terminal_roe": str(value.terminal_roe),
        "terminal_growth": str(value.terminal_growth),
        "terminal_economic_contract": terminal_contract_payload(value.terminal_economic_contract),
    }


_SCENARIO_KEYS = frozenset({"retention_contract", "currency", "cost_of_equity",
    "forecast_roes", "forecast_retentions", "terminal_roe", "terminal_growth",
    "terminal_economic_contract"})


def scenario_from_payload(value: Mapping[str, Any]) -> V3Scenario:
    data = dict(value)
    if set(data) != _SCENARIO_KEYS or data["retention_contract"] != RETENTION_CONTRACT:
        raise ValueError("exact annual-retention-v3 scenario required")
    if data["currency"] != "CNY":
        raise ValueError("v3 residual-income scenario requires CNY")
    if (not isinstance(data["forecast_roes"], list)
            or not isinstance(data["forecast_retentions"], list)):
        raise ValueError("v3 forecast paths must be lists")
    return V3Scenario(
        cost_of_equity=_decimal(data["cost_of_equity"], "cost_of_equity"),
        forecast_roes=tuple(_decimal(item, "forecast_roes") for item in data["forecast_roes"]),
        forecast_retentions=tuple(_decimal(item, "forecast_retentions") for item in data["forecast_retentions"]),
        terminal_roe=_decimal(data["terminal_roe"], "terminal_roe"),
        terminal_growth=_decimal(data["terminal_growth"], "terminal_growth"),
        currency="CNY",
        terminal_economic_contract=terminal_contract_from_payload(data["terminal_economic_contract"]),
    )


def _v2_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    scenario = scenario_from_payload(value)
    return {
        "retention_contract": "annual-retention-v2", "currency": scenario.currency,
        "cost_of_equity": str(scenario.cost_of_equity),
        "forecast_roes": [str(item) for item in scenario.forecast_roes],
        "forecast_retentions": [str(item) for item in scenario.forecast_retentions],
        "terminal_roe": str(scenario.terminal_roe),
        "terminal_growth": str(scenario.terminal_growth),
    }


def facts_to_payload_v3(facts: QualityCompounderFacts) -> dict[str, Any]:
    if not isinstance(facts, QualityCompounderFacts) or not facts.scenario_inputs:
        raise TypeError("v3 facts require typed quality-compounder scenarios")
    if any(not isinstance(item, V3Scenario) for item in facts.scenario_inputs.values()):
        raise TypeError("not v3 quality-compounder facts")
    from ...research_input import facts_to_payload
    legacy = replace(facts, scenario_inputs={name: V2Scenario(
        cost_of_equity=item.cost_of_equity, forecast_roes=item.forecast_roes,
        forecast_retentions=item.forecast_retentions, terminal_roe=item.terminal_roe,
        terminal_growth=item.terminal_growth, currency=item.currency,
    ) for name, item in facts.scenario_inputs.items()})
    payload = facts_to_payload(legacy)
    payload["scenario_inputs"] = {name: scenario_payload(item)
                                  for name, item in facts.scenario_inputs.items()}
    return payload


def facts_from_payload_v3(payload: Mapping[str, Any]) -> QualityCompounderFacts:
    data = deepcopy(dict(payload))
    scenarios = data.get("scenario_inputs")
    if data.get("facts_type") != "quality_compounder" or not isinstance(scenarios, Mapping):
        raise ValueError("v3 financial facts require quality-compounder scenarios")
    v3 = {name: scenario_from_payload(item) for name, item in scenarios.items()}
    from ...research_input import facts_from_payload
    data["scenario_inputs"] = {name: _v2_payload(item) for name, item in scenarios.items()}
    legacy = facts_from_payload(data)
    return replace(legacy, scenario_inputs=v3)


def _validate_exact_proposal_choice(
    payload: Mapping[str, Any], *, root: Path,
) -> None:
    """Bind every v3 terminal field to one exact, hash-bound proposal choice.

    The predecessor source-bound validator covers the numeric RI inputs.  The
    terminal contract also contains capital-use mechanics, cash constraints,
    timing and rationale.  Those fields are derived by the proposal compiler,
    so the package must reproduce one proposal choice byte-for-value instead of
    merely carrying them inside a newly sealed descriptor hash.
    """
    from ..product.common import require_inside, sha256_file

    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("v3 descriptor requires a source catalog")
    proposals = [item for item in sources if isinstance(item, Mapping)
                 and str(item.get("id", "")).startswith("pending-joint-proposal-")]
    if len(proposals) != 1:
        raise ValueError("v3 descriptor requires one exact source-bound proposal")
    source = proposals[0]
    local_path = source.get("local_path")
    digest = source.get("sha256")
    if not isinstance(local_path, str) or not isinstance(digest, str) or len(digest) != 64:
        raise ValueError("v3 proposal source requires a local path and SHA-256")
    if source.get("id") != f"pending-joint-proposal-{digest.lower()}":
        raise ValueError("v3 proposal source identity must equal its SHA-256")
    path = require_inside(root, root / local_path, "v3 proposal source")
    if sha256_file(path) != digest.lower():
        raise ValueError("v3 proposal source hash mismatch")
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("v3 proposal source is not valid UTF-8 JSON") from exc
    if (not isinstance(proposal, Mapping)
            or proposal.get("schema_version") != PROPOSAL_SCHEMA
            or proposal.get("input_mode") != PROPOSAL_SCHEMA
            or proposal.get("action") != "no_order"
            or proposal.get("symbol") != payload.get("symbol")):
        raise ValueError("v3 proposal source identity differs from the package")

    facts = payload.get("facts")
    wanted_scenarios = facts.get("scenario_inputs") if isinstance(facts, Mapping) else None
    operating = facts.get("operating_inputs") if isinstance(facts, Mapping) else None
    if not isinstance(wanted_scenarios, Mapping) or not isinstance(operating, Mapping):
        raise ValueError("v3 proposal binding requires operating and scenario inputs")
    matches = []
    for choice in proposal.get("choices") or []:
        if not isinstance(choice, Mapping):
            continue
        actual = choice.get("actual_calculation_inputs")
        actual_scenarios = actual.get("scenarios") if isinstance(actual, Mapping) else None
        if not isinstance(actual_scenarios, Mapping) or set(actual_scenarios) != {"bear", "base", "bull"}:
            continue
        normalized = {}
        valid = True
        for name, row in actual_scenarios.items():
            if not isinstance(row, Mapping) or "forecast_roe" not in row or "forecast_roes" in row:
                valid = False
                break
            normalized[name] = deepcopy(dict(row))
            normalized[name]["forecast_roes"] = normalized[name].pop("forecast_roe")
        if (valid and normalized == dict(wanted_scenarios)
                and actual.get("start_book_equity") == operating.get("start_book_equity")
                and actual.get("ordinary_shares") == operating.get("ordinary_shares")):
            matches.append(choice.get("id"))
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise ValueError("v3 terminal economics do not match one exact proposal choice")


class V3ResearchInputDescriptor(ResearchInputDescriptor):
    def as_policy(self) -> dict[str, Any]:
        legacy_facts = replace(self.facts, scenario_inputs={name: V2Scenario(
            cost_of_equity=item.cost_of_equity, forecast_roes=item.forecast_roes,
            forecast_retentions=item.forecast_retentions, terminal_roe=item.terminal_roe,
            terminal_growth=item.terminal_growth, currency=item.currency,
        ) for name, item in self.facts.scenario_inputs.items()})
        values = {field.name: getattr(self, field.name) for field in fields(ResearchInputDescriptor)}
        values.update(facts=legacy_facts, input_sha256=None)
        payload = ResearchInputDescriptor(**values).as_policy()
        payload["facts"] = facts_to_payload_v3(self.facts)
        payload["input_sha256"] = self.input_sha256
        return payload


def build_v3_descriptor(payload: Mapping[str, Any], *, root: Path) -> V3ResearchInputDescriptor:
    data = deepcopy(dict(payload))
    if (data.get("dependencies") or {}).get("model_version") != MODEL_VERSION:
        raise ValueError("v3 descriptor requires the exact v3 model version")
    facts = data.get("facts")
    scenarios = facts.get("scenario_inputs") if isinstance(facts, Mapping) else None
    if not isinstance(scenarios, Mapping) or set(scenarios) != {"bear", "base", "bull"}:
        raise ValueError("v3 descriptor requires exact bear/base/bull scenarios")
    typed = {name: scenario_from_payload(item) for name, item in scenarios.items()}
    original = deepcopy(data)
    _validate_exact_proposal_choice(original, root=root)
    data["facts"] = deepcopy(dict(facts))
    data["facts"]["scenario_inputs"] = {name: _v2_payload(item) for name, item in scenarios.items()}
    compatibility = deepcopy(data)
    # The predecessor builder is source-hash bound. Reuse its parsing logic in
    # legacy-schema mode after the caller has independently restored/verified
    # historical implementation bytes, then reapply and validate the source contract.
    data["schema_version"] = "m1-valuation-package-v1"
    data.pop("source_contract", None)
    legacy = build_descriptor(data, root=root)
    source_contract = ResearchSourceContract.from_payload(original["source_contract"])
    legacy_values = {field.name: getattr(legacy, field.name) for field in fields(ResearchInputDescriptor)}
    legacy_values.update(distribution_result=None, source_contract=source_contract, input_sha256=None)
    bound_legacy = finalize_input_descriptor(ResearchInputDescriptor(**legacy_values))
    from ..product.source_bound_inputs import validate_source_bound_descriptor
    compatibility["schema_version"] = original["schema_version"]
    compatibility["source_contract"] = original["source_contract"]
    validate_source_bound_descriptor(compatibility, bound_legacy)
    values = {field.name: getattr(bound_legacy, field.name) for field in fields(ResearchInputDescriptor)}
    values.update(facts=replace(bound_legacy.facts, scenario_inputs=typed), input_sha256=None)
    descriptor = finalize_input_descriptor(V3ResearchInputDescriptor(**values))
    return descriptor


def build_predecessor_descriptor(payload: Mapping[str, Any], *, root: Path) -> ResearchInputDescriptor:
    """Parse a restored source-bound predecessor without re-reading live code bytes."""
    original = deepcopy(dict(payload))
    data = deepcopy(original)
    data["schema_version"] = "m1-valuation-package-v1"
    data.pop("source_contract", None)
    legacy = build_descriptor(data, root=root)
    values = {field.name: getattr(legacy, field.name) for field in fields(ResearchInputDescriptor)}
    values.update(
        distribution_result=None,
        source_contract=ResearchSourceContract.from_payload(original["source_contract"]),
        input_sha256=None,
    )
    descriptor = finalize_input_descriptor(ResearchInputDescriptor(**values))
    from ..product.source_bound_inputs import validate_source_bound_descriptor
    validate_source_bound_descriptor(original, descriptor)
    return descriptor


def build_descriptor_for_package(payload: Mapping[str, Any], *, root: Path) -> ResearchInputDescriptor:
    version = (payload.get("dependencies") or {}).get("model_version")
    if version == MODEL_VERSION:
        return build_v3_descriptor(payload, root=root)
    return build_descriptor(payload, root=root)
