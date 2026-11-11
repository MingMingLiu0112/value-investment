"""Read a completed D2 v4 cash-policy task as an immutable E2 input.

This is an adapter, not an estimate engine.  It does not create a valuation,
invent missing parent-cash facts, or convert conditional policy terms into an
approved main range.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .operating_cash_consumption_v2 import compile_verified_annual_candidates
from ...domain.research.operating_cash_consumption_v1 import consume_operating_earnings
from .agent_review.operating_horizon_draft_v3 import SCENARIOS, TERMS, VERSION as DRAFT_VERSION
from .agent_review.operating_horizon_task_v4 import CONTRACT, OperatingHorizonTaskService
from .agent_review.operating_horizon_task_v5_wc import CONTRACT as WC_CONTRACT
from .agent_review.operating_horizon_task_v6_split import CONTRACT as SPLIT_V6_CONTRACT
from .agent_review.operating_horizon_task_v2 import (
    CONTRACT as ANNUAL_CONTRACT,
    OperatingHorizonTaskService as AnnualOperatingTaskService,
)
from .agent_review.operating_annual_task_v3 import (
    CONTRACT as ANNUAL_V3_CONTRACT,
    OperatingHorizonTaskService as AnnualV3TaskService,
)
from .agent_review.operating_cash_policy_task_v1 import (
    CONTRACT as FOLLOWUP_CONTRACT,
    OperatingCashPolicyTaskService,
)
from .agent_review.operating_cash_policy_draft_v1 import VERSION as FOLLOWUP_DRAFT_VERSION

VERSION = "operating-horizon-cash-policy-e2-input-v1"


def _annual_opening_period(row: dict) -> str:
    """Use the verified FY operating baseline, never an interim report date."""
    paths = row.get("operating_paths")
    if not isinstance(paths, dict) or set(paths) != set(SCENARIOS):
        raise ValueError("THREE_OPERATING_BASELINES_REQUIRED")
    dates = {path.get("baseline_period") for path in paths.values()
             if isinstance(path, dict)}
    if len(dates) != 1 or any(not isinstance(day, str) for day in dates):
        raise ValueError("INCONSISTENT_OPERATING_BASELINE")
    opening = dates.pop()
    if not opening.endswith("-12-31"):
        raise ValueError("COMPLETE_FY_OPERATING_BASELINE_REQUIRED")
    return opening


def read_d2_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                  service=None) -> dict:
    """Cold-read a complete full or compact D2 policy task for E2 terms only."""
    if now.utcoffset() is None:
        raise ValueError("E2 cash-policy read requires timezone-aware time")
    if service is None:
        try:
            service = OperatingHorizonTaskService(root)
            task = service.read(task_id)
        except FileNotFoundError:
            service = OperatingCashPolicyTaskService(root)
            task = service.read(task_id)
    else:
        task = service.read(task_id)
    economic_validation = task.get("economic_validation")
    if isinstance(economic_validation, dict) and economic_validation.get("status") == "REJECTED":
        raise ValueError(economic_validation.get("reason") or "D2_ECONOMIC_VALIDATION_REJECTED")
    research_as_of = task.get("research_as_of")
    if not isinstance(research_as_of, str):
        raise ValueError("D2_CASH_POLICY_RESEARCH_TIME_REQUIRED")
    try:
        research_time = datetime.fromisoformat(research_as_of)
    except ValueError as error:
        raise ValueError("D2_CASH_POLICY_RESEARCH_TIME_INVALID") from error
    if research_time.utcoffset() is None or research_time > now:
        raise ValueError("D2_CASH_POLICY_NOT_AVAILABLE_AT_E2_CUTOFF")
    contracts = {CONTRACT: DRAFT_VERSION, WC_CONTRACT: DRAFT_VERSION,
                 SPLIT_V6_CONTRACT: DRAFT_VERSION,
                 FOLLOWUP_CONTRACT: FOLLOWUP_DRAFT_VERSION}
    contract = task.get("workflow")
    if (contract not in contracts or task.get("status") != "SUCCEEDED"
            or task.get("action") != "no_order" or task.get("formal_eligibility") is not False):
        raise ValueError("SUCCEEDED_BOUND_D2_CASH_POLICY_TASK_REQUIRED")
    research = task.get("research_result")
    if (not isinstance(research, dict) or research.get("schema_version") != contracts[contract]
            or research.get("cash_policy_appendix_status") != "COMPLETE_UNAPPROVED"
            or research.get("action") != "no_order"):
        raise ValueError("COMPLETE_UNAPPROVED_D2_CASH_POLICY_REQUIRED")
    if contract == SPLIT_V6_CONTRACT:
        responses = task.get("stage_responses")
        split_binding = research.get("split_contract")
        if (task.get("annual_status") != "SETTLED_VALIDATED"
                or task.get("cash_status") != "SETTLED_VALIDATED"
                or not isinstance(responses, dict) or set(responses) != {"annual", "cash"}
                or any(not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
                       for pin in responses.values())
                or not isinstance(split_binding, dict)
                or split_binding != task.get("cash_binding")
                or split_binding.get("action") != "no_order"
                or not isinstance(research.get("split_response_sha256"), dict)
                or set(research["split_response_sha256"]) != {"annual", "cash"}):
            raise ValueError("D2_V6_SPLIT_RESPONSE_BINDING_REQUIRED")
    years = research.get("years")
    if not isinstance(years, dict) or not years:
        raise ValueError("D2_V4_POLICY_YEARS_REQUIRED")
    completed_at = datetime.fromisoformat(task["updated_at"])
    if completed_at.utcoffset() is None or completed_at > now:
        raise ValueError("D2_CASH_POLICY_RESPONSE_AFTER_E2_CUTOFF")
    policies = {}
    for year, row in years.items():
        paths = row.get("shareholder_cash_paths") if isinstance(row, dict) else None
        if not isinstance(paths, dict) or set(paths) != set(SCENARIOS):
            raise ValueError("D2_V4_POLICY_SCENARIOS_REQUIRED")
        policies[year] = {}
        for scenario, path in paths.items():
            if (not isinstance(path, dict) or path.get("complete") is not True
                    or not isinstance(path.get("terms"), dict) or set(path["terms"]) != set(TERMS)):
                raise ValueError("D2_V4_POLICY_TERM_COMPLETENESS_REQUIRED")
            if contract == SPLIT_V6_CONTRACT and any(
                    not isinstance(term, dict)
                    or term.get("classification") != "FORECAST_ASSUMPTION"
                    or term.get("value") is None
                    for term in path["terms"].values()):
                raise ValueError("D2_V6_UNKNOWN_CASH_TERM_NOT_E2_INPUT")
            policies[year][scenario] = deepcopy(path)
    annual_candidates = {}
    annual_error = None
    task_fingerprint = task.get("context_fingerprint")
    if contract in {CONTRACT, WC_CONTRACT, SPLIT_V6_CONTRACT}:
        # The full v4 response carries the operating bridge. Keep it from the
        # same sealed task as the cash policy, instead of reusing a different
        # annual task by symbol or manufacturing an earnings path.
        context = service.source_loader(root=root, symbol=task["symbol"],
            binding=task["source_binding"], now=research_time)
        if contract == SPLIT_V6_CONTRACT:
            spec, _, _ = service._load(task_id)
            service._context(spec)
            task_fingerprint = spec["context_fingerprint"]
            if (spec["source_binding"] != task["source_binding"]
                    or spec["wc_source_binding"] != task["wc_source_binding"]):
                raise ValueError("D2_V6_TASK_SOURCE_PIN_CHANGED")
        if context["snapshot_fingerprint"] != task_fingerprint:
            raise ValueError("D2_V4_OPERATING_SOURCE_CONTEXT_CHANGED")
        for year, row in years.items():
            bridge = dict(paths=row["calculated_paths"], inputs=row["operating_paths"], action="no_order")
            try:
                earnings = consume_operating_earnings(context=context, bridge=bridge)
                earnings["task_id"] = task_id
                compiled = compile_verified_annual_candidates(consumed=earnings,
                    opening_date=_annual_opening_period(row), asof=research_as_of)
            except ValueError as error:
                annual_error = str(error)
                annual_candidates = {}
                break
            annual_candidates[year] = dict(scenarios=compiled["scenarios"],
                earnings=earnings["scenarios"], task_id=task_id)
    bindings = [deepcopy(task[key]) for key in ("record_binding", "source_binding") if isinstance(task.get(key), dict)]
    if len(bindings) != 2:
        raise ValueError("D2_V4_TASK_BINDINGS_REQUIRED")
    if contract in {WC_CONTRACT, SPLIT_V6_CONTRACT}:
        wc_binding = task.get("wc_source_binding")
        if (not isinstance(wc_binding, dict) or
                set(wc_binding) != {"registry", "originals", "history_sha256"}):
            raise ValueError("D2_WC_SOURCE_BINDING_REQUIRED")
        bindings.append(deepcopy(wc_binding))
    if contract == SPLIT_V6_CONTRACT:
        if (len(task["wc_source_binding"]["originals"]) < 2
                or not isinstance(task["wc_source_binding"]["history_sha256"], str)
                or len(task["wc_source_binding"]["history_sha256"]) != 64):
            raise ValueError("D2_V6_WC_SOURCE_PIN_INCOMPLETE")
        bindings.extend(deepcopy(task["stage_responses"][stage]) for stage in ("annual", "cash"))
    manifest = dict(schema_version=VERSION, task_id=task_id, symbol=task["symbol"],
        task_contract=contract, task_context_fingerprint=task_fingerprint,
        source_bindings=bindings, policy_years=sorted(policies),
        annual_operating_years=sorted(annual_candidates), action="no_order",
        formal_eligibility=False, main_range_adopted=False)
    if contract == SPLIT_V6_CONTRACT:
        manifest["split_contract"] = deepcopy(research["split_contract"])
        manifest["split_response_sha256"] = deepcopy(research["split_response_sha256"])
    return dict(status=("SOURCE_BOUND_D2_V6_CASH_POLICY_READY_FOR_E2" if contract == SPLIT_V6_CONTRACT
                        else "SOURCE_BOUND_D2_V4_CASH_POLICY_READY_FOR_E2"), action="no_order",
        formal_eligibility=False, main_range_adopted=False, condition_price=None,
        symbol=task["symbol"], task_id=task_id, task_binding=bindings[0], source_binding=bindings[1],
        research_as_of=research_as_of, context_fingerprint=task_fingerprint,
        policy_years=policies, annual_operating_candidates=annual_candidates,
        annual_operating_status=("ANNUAL_OPERATING_INPUT_UNASSESSABLE" if annual_error else
                                 "SAME_TASK_COMPILED" if annual_candidates else "SEPARATE_ANNUAL_INPUT_REQUIRED"),
        annual_operating_error=annual_error,
        input_manifest=manifest,
        input_fingerprint=hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        blockers=(["ANNUAL_OPERATING_INPUT_UNASSESSABLE"] if annual_error else []) + [
                  "PARENT_CASH_FACTS_AND_OPENING_CAPITAL_REQUIRED", "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED",
                  "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED"],
        scope=("CONDITIONAL_UNAPPROVED_D2_V6_POLICY_NOT_VALUATION_OR_PRICE"
               if contract == SPLIT_V6_CONTRACT
               else "CONDITIONAL_UNAPPROVED_D2_V4_POLICY_NOT_VALUATION_OR_PRICE"))


def read_v4_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                 service: OperatingHorizonTaskService | None = None) -> dict:
    """Backward-compatible name for the D2 policy-only E2 input reader."""
    return read_d2_cash_policy_e2_input(root=root, task_id=task_id, now=now, service=service)


def read_split_d2_e2_input(*, root: Path, annual_task_id: str, cash_task_id: str,
                           now: datetime, annual_service=None, cash_service=None) -> dict:
    """Join independently admitted D2 research only on identical sealed facts.

    Task success alone is insufficient: the cash terms must be complete, the
    operating bridge must compile, and the complete evidence corpus must agree.
    The result remains unapproved E2 input, never an adopted valuation.
    """
    if now.utcoffset() is None or annual_task_id == cash_task_id:
        raise ValueError("SPLIT_D2_IDENTITY_OR_CUTOFF_INVALID")
    root = Path(root).resolve()
    if annual_service is None:
        annual_service = AnnualV3TaskService(root)
        try:
            annual = annual_service.read(annual_task_id)
        except FileNotFoundError:
            annual_service = AnnualOperatingTaskService(root)
            annual = annual_service.read(annual_task_id)
    else:
        annual = annual_service.read(annual_task_id)
    cash_service = cash_service or OperatingCashPolicyTaskService(root)
    policy = read_d2_cash_policy_e2_input(
        root=root, task_id=cash_task_id, now=now, service=cash_service)
    if (annual.get("workflow") not in {ANNUAL_CONTRACT, ANNUAL_V3_CONTRACT}
            or annual.get("status") != "SUCCEEDED"
            or annual.get("action") != "no_order"
            or annual.get("formal_eligibility") is not False
            or not isinstance(annual.get("research_result"), dict)):
        raise ValueError("SUCCEEDED_BOUND_ANNUAL_D2_TASK_REQUIRED")
    if (annual.get("symbol") != policy["symbol"]
            or set(map(str, annual.get("years", []))) != set(policy["policy_years"])):
        raise ValueError("SPLIT_D2_SYMBOL_OR_YEARS_MISMATCH")
    annual_time = datetime.fromisoformat(annual["research_as_of"])
    annual_finished = datetime.fromisoformat(annual["updated_at"])
    if (annual_time.utcoffset() is None or annual_finished.utcoffset() is None
            or annual_time > now or annual_finished > now):
        raise ValueError("ANNUAL_D2_AFTER_E2_CUTOFF")
    annual_context = annual_service.source_loader(
        root=root, symbol=annual["symbol"], binding=annual["source_binding"],
        now=annual_time)
    cash_time = datetime.fromisoformat(policy["research_as_of"])
    cash_context = cash_service.source_loader(
        root=root, symbol=policy["symbol"], binding=policy["source_binding"],
        now=cash_time)
    if (annual_context.get("snapshot_fingerprint") != annual.get("context_fingerprint")
            or cash_context.get("snapshot_fingerprint") != policy.get("context_fingerprint")):
        raise ValueError("SPLIT_D2_SOURCE_CONTEXT_CHANGED")
    def corpus(context):
        return dict(symbol=context.get("symbol"), issuer_name=context.get("issuer_name"),
            financial_basis=context.get("financial_basis"),
            base_source_binding=context.get("base_source_binding"),
            supplemental_sources=context.get("supplemental_sources"),
            parent_cash_observation_receipts=context.get("parent_cash_observation_receipts"),
            evidence=context.get("evidence"),
            statement_basis_gaps=context.get("statement_basis_gaps"),
            scope_decomposition=context.get("scope_decomposition"))
    if corpus(annual_context) != corpus(cash_context):
        raise ValueError("SPLIT_D2_OFFICIAL_CORPUS_MISMATCH")
    years = annual["research_result"].get("years")
    if not isinstance(years, dict) or set(years) != set(policy["policy_years"]):
        raise ValueError("SPLIT_D2_OPERATING_YEARS_REQUIRED")
    annual_candidates = {}
    for year, row in years.items():
        bridge = dict(paths=row["calculated_paths"], inputs=row["operating_paths"],
                      action="no_order")
        earnings = consume_operating_earnings(context=annual_context, bridge=bridge)
        earnings["task_id"] = annual_task_id
        compiled = compile_verified_annual_candidates(
            consumed=earnings, opening_date=_annual_opening_period(row),
            asof=annual["research_as_of"])
        annual_candidates[year] = dict(scenarios=compiled["scenarios"],
            earnings=earnings["scenarios"], task_id=annual_task_id)
    manifest = dict(schema_version="split-d2-e2-input-v1", symbol=annual["symbol"],
        annual_contract=annual["workflow"],
        annual_task_id=annual_task_id, cash_task_id=cash_task_id,
        annual_record_binding=annual["record_binding"],
        cash_record_binding=policy["task_binding"],
        annual_source_binding=annual["source_binding"],
        cash_source_binding=policy["source_binding"],
        official_corpus_sha256=hashlib.sha256(json.dumps(corpus(annual_context),
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode()).hexdigest(),
        years=sorted(years), action="no_order", formal_eligibility=False)
    return dict(status="SOURCE_BOUND_SPLIT_D2_READY_FOR_E2", symbol=annual["symbol"],
        policy_years=policy["policy_years"], annual_operating_candidates=annual_candidates,
        annual_operating_status="SEPARATE_SAME_CORPUS_TASK_COMPILED",
        input_manifest=manifest, input_fingerprint=hashlib.sha256(json.dumps(manifest,
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False).encode()).hexdigest(),
        blockers=["PARENT_CASH_FACTS_AND_OPENING_CAPITAL_REQUIRED",
                  "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED",
                  "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED"],
        condition_price=None, main_range_adopted=False,
        formal_eligibility=False, action="no_order",
        scope="CONDITIONAL_UNAPPROVED_SPLIT_D2_NOT_VALUATION_OR_PRICE")
