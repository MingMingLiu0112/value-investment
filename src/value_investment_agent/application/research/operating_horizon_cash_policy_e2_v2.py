"""Admit a replayed V10 two-stage research task as conditional E2 input."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

from .agent_review.operating_horizon_task_v10_live import (
    CONTRACT, OperatingHorizonTaskService,
)
from .agent_review.operating_horizon_draft_v3 import SCENARIOS, TERMS, RATIO_TERMS
from .operating_horizon_cash_policy_e2_v1 import _annual_opening_period
from .operating_cash_consumption_v2 import compile_verified_annual_candidates
from ...domain.research.operating_cash_consumption_v1 import consume_operating_earnings

VERSION = "operating-horizon-cash-policy-e2-input-v2"


def _time(value, now):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError("V10_E2_TIME_INVALID") from error
    if parsed.utcoffset() is None or parsed > now:
        raise ValueError("V10_E2_TIME_INVALID")
    return parsed


def _read_bound_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                     contract: str, task_service, version: str,
                                     label: str, service=None, allow_imported_v12=False) -> dict:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("V10_E2_CUTOFF_REQUIRED")
    root = Path(root).resolve()
    service = service or task_service(root)
    task = service.read(task_id)  # Durable read replays source, requests and both responses.
    spec, state, _ = service._load(task_id)
    imported = allow_imported_v12 and "imported_annual" in spec
    if (task.get("workflow") != contract or task.get("status") != "SUCCEEDED"
            or task.get("action") != "no_order" or task.get("formal_eligibility") is not False
            or task.get("annual_status") != ("IMPORTED_V12" if imported else "SETTLED_VALIDATED")
            or task.get("cash_status") != "SETTLED_VALIDATED"):
        raise ValueError("V10_E2_SUCCEEDED_TWO_STAGE_TASK_REQUIRED")
    _time(task.get("research_as_of"), now)
    _time(task.get("updated_at"), now)
    pins = task.get("stage_responses")
    if (not isinstance(pins, dict) or set(pins) != ({"cash"} if imported else {"annual", "cash"})
            or any(not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
                   or not isinstance(pin["sha256"], str) or len(pin["sha256"]) != 64
                   for pin in pins.values())):
        raise ValueError("V10_E2_RESPONSE_PINS_REQUIRED")
    mode = spec.get("mode")
    if (mode not in {"LIVE_OPERATING", "TEST_ONLY_LIVE_CONTRACT"}
            or task.get("execution_mode") != mode):
        raise ValueError("V10_E2_EXECUTION_MODE_INVALID")
    if (spec.get("task_contract") != contract or spec.get("source_binding") != task.get("source_binding")
            or state.get("stage_responses") != pins or state.get("cash_binding") != task.get("cash_binding")
            or set(state.get("stage_validated", [])) != {"annual", "cash"}
            or (imported and (state.get("stage_intents", {}).get("annual") is not None
                              or "annual" in state.get("stage_responses", {})))):
        raise ValueError("V10_E2_TASK_PINS_CHANGED")
    context = service._context(spec)
    if (context.get("snapshot_fingerprint") != spec.get("context_fingerprint") if not imported
            else hashlib.sha256(json.dumps(context, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
                != spec.get("context_sha256")):
        raise ValueError("V10_E2_SOURCE_CONTEXT_CHANGED")
    if imported:
        from .agent_review.operating_horizon_carryover_v13 import replay_cash
        pin = spec["imported_annual"]
        _, lineage, source_context, annual_packet = replay_cash(root, pin["source_task_id"],
            expected_source_binding=pin["source_binding"],
            expected_context_sha256=pin["source_context_sha256"],
            expected_annual_response_sha256=pin["source_annual_response_sha256"],
            expected_budget_day=pin["source_budget_day"])
        if (lineage != pin or source_context != context
                or task.get("imported_annual", {}).get("source_annual_result_sha256")
                   != pin["source_annual_result_sha256"]):
            raise ValueError("V10_E2_IMPORTED_LINEAGE_CHANGED")
        if _time(annual_packet.get("generated_at"), now) > _time(task["research_as_of"], now):
            raise ValueError("V13_E2_IMPORTED_ANNUAL_AFTER_RESEARCH_ASOF")
    research = task.get("research_result")
    if (not isinstance(research, dict) or research.get("cash_policy_appendix_status") != "COMPLETE_UNAPPROVED"
            or research.get("action") != "no_order" or research.get("split_contract") != task.get("cash_binding")):
        raise ValueError("V10_E2_COMPLETE_UNAPPROVED_REQUIRED")
    responses = research.get("split_response_sha256")
    if not isinstance(responses, dict) or set(responses) != {"annual", "cash"}:
        raise ValueError("V10_E2_RESPONSE_HASHES_REQUIRED")
    for stage in ("annual", "cash"):
        packet = annual_packet if imported and stage == "annual" else service._packet(spec, state, stage)
        _time(packet.get("generated_at"), now)
        actual = hashlib.sha256(packet["response"]["text"].encode("utf-8")).hexdigest()
        if responses[stage] != actual:
            raise ValueError("V10_E2_RESPONSE_HASH_CHANGED")
    years = research.get("years")
    if not isinstance(years, dict) or set(years) != {"2027"}:
        raise ValueError("V10_E2_YEAR_REQUIRED")
    policies, candidates = {}, {}
    for year, row in years.items():
        paths = row.get("shareholder_cash_paths") if isinstance(row, dict) else None
        if not isinstance(paths, dict) or set(paths) != set(SCENARIOS):
            raise ValueError("V10_E2_POLICY_SCENARIOS_REQUIRED")
        policies[year] = {}
        for scenario, path in paths.items():
            if (not isinstance(path, dict) or path.get("complete") is not True
                    or not isinstance(path.get("terms"), dict) or set(path["terms"]) != set(TERMS)):
                raise ValueError("V10_E2_CASH_TERMS_INCOMPLETE")
            for name, term in path["terms"].items():
                if not isinstance(term, dict) or term.get("classification") != "FORECAST_ASSUMPTION":
                    raise ValueError("V10_E2_UNKNOWN_CASH_TERM")
                value = term.get("value")
                try:
                    number = Decimal(value) if isinstance(value, str) else Decimal("NaN")
                except InvalidOperation:
                    number = Decimal("NaN")
                unit = "ratio" if name in RATIO_TERMS else "CNY"
                if (not number.is_finite() or number < 0 or (unit == "ratio" and number > 1)
                        or term.get("unit") != unit):
                    raise ValueError("V10_E2_CASH_TERM_INVALID")
            policies[year][scenario] = deepcopy(path)
        bridge = dict(paths=row["calculated_paths"], inputs=row["operating_paths"], action="no_order")
        earnings = consume_operating_earnings(context=context, bridge=bridge)
        earnings["task_id"] = task_id
        compiled = compile_verified_annual_candidates(consumed=earnings,
            opening_date=_annual_opening_period(row), asof=task["research_as_of"])
        candidates[year] = dict(scenarios=compiled["scenarios"],
            earnings=earnings["scenarios"], task_id=task_id)
    manifest = dict(schema_version=version, task_id=task_id, task_contract=contract,
        symbol=task["symbol"], record_binding=deepcopy(task["record_binding"]),
        source_binding=deepcopy(task["source_binding"]),
        context_fingerprint=spec.get("context_fingerprint"), cash_binding=deepcopy(task["cash_binding"]),
        stage_responses=deepcopy(pins), split_response_sha256=deepcopy(responses),
        years=["2027"], execution_mode=mode, action="no_order",
        formal_eligibility=False, main_range_adopted=False)
    if imported:
        manifest.pop("context_fingerprint")
        manifest.update(context_sha256=spec["context_sha256"],
            annual_origin="V12_EXTERNAL", imported_annual=deepcopy(lineage),
            annual_response_binding=deepcopy(lineage["source_annual_response_binding"]))
    fingerprint = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return dict(status=(f"SOURCE_BOUND_D2_{label}_CASH_POLICY_READY_FOR_E2"
                        if mode == "LIVE_OPERATING" else "TEST_ONLY_E2_CONTRACT_REPLAY"),
        execution_mode=mode, action="no_order",
        formal_eligibility=False, main_range_adopted=False, condition_price=None,
        symbol=task["symbol"], task_id=task_id, research_as_of=task["research_as_of"],
        policy_years=policies, annual_operating_candidates=candidates,
        annual_operating_status=("IMPORTED_V12_COMPILED" if imported else "SAME_TASK_COMPILED"), input_manifest=manifest,
        input_fingerprint=fingerprint,
        blockers=["PARENT_CASH_FACTS_AND_OPENING_CAPITAL_REQUIRED",
                  "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED",
                  "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED"],
        scope=(f"CONDITIONAL_UNAPPROVED_D2_{label}_POLICY_NOT_VALUATION_OR_PRICE"
               if mode == "LIVE_OPERATING" else "TEST_ONLY_NOT_REAL_RESEARCH_OR_VALUATION"))


def read_v10_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    return _read_bound_cash_policy_e2_input(
        root=root, task_id=task_id, now=now, contract=CONTRACT,
        task_service=OperatingHorizonTaskService, version=VERSION,
        label="V10", service=service)
