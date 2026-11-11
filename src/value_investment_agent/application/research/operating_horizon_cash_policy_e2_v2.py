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


def read_v10_cash_policy_e2_input(*, root: Path, task_id: str, now: datetime,
                                   service=None) -> dict:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise ValueError("V10_E2_CUTOFF_REQUIRED")
    root = Path(root).resolve()
    service = service or OperatingHorizonTaskService(root)
    task = service.read(task_id)  # Durable read replays source, requests and both responses.
    if (task.get("workflow") != CONTRACT or task.get("status") != "SUCCEEDED"
            or task.get("action") != "no_order" or task.get("formal_eligibility") is not False
            or task.get("annual_status") != "SETTLED_VALIDATED"
            or task.get("cash_status") != "SETTLED_VALIDATED"):
        raise ValueError("V10_E2_SUCCEEDED_TWO_STAGE_TASK_REQUIRED")
    _time(task.get("research_as_of"), now)
    _time(task.get("updated_at"), now)
    pins = task.get("stage_responses")
    if (not isinstance(pins, dict) or set(pins) != {"annual", "cash"}
            or any(not isinstance(pin, dict) or set(pin) != {"path", "sha256"}
                   or not isinstance(pin["sha256"], str) or len(pin["sha256"]) != 64
                   for pin in pins.values())):
        raise ValueError("V10_E2_RESPONSE_PINS_REQUIRED")
    spec, state, _ = service._load(task_id)
    if (spec.get("task_contract") != CONTRACT or spec.get("source_binding") != task.get("source_binding")
            or state.get("stage_responses") != pins or state.get("cash_binding") != task.get("cash_binding")
            or set(state.get("stage_validated", [])) != {"annual", "cash"}):
        raise ValueError("V10_E2_TASK_PINS_CHANGED")
    context = service._context(spec)
    if context.get("snapshot_fingerprint") != spec.get("context_fingerprint"):
        raise ValueError("V10_E2_SOURCE_CONTEXT_CHANGED")
    research = task.get("research_result")
    if (not isinstance(research, dict) or research.get("cash_policy_appendix_status") != "COMPLETE_UNAPPROVED"
            or research.get("action") != "no_order" or research.get("split_contract") != task.get("cash_binding")):
        raise ValueError("V10_E2_COMPLETE_UNAPPROVED_REQUIRED")
    responses = research.get("split_response_sha256")
    if not isinstance(responses, dict) or set(responses) != {"annual", "cash"}:
        raise ValueError("V10_E2_RESPONSE_HASHES_REQUIRED")
    for stage in ("annual", "cash"):
        packet = service._packet(spec, state, stage)
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
    manifest = dict(schema_version=VERSION, task_id=task_id, task_contract=CONTRACT,
        symbol=task["symbol"], record_binding=deepcopy(task["record_binding"]),
        source_binding=deepcopy(task["source_binding"]),
        context_fingerprint=spec["context_fingerprint"], cash_binding=deepcopy(task["cash_binding"]),
        stage_responses=deepcopy(pins), split_response_sha256=deepcopy(responses),
        years=["2027"], action="no_order", formal_eligibility=False, main_range_adopted=False)
    fingerprint = hashlib.sha256(json.dumps(manifest, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    return dict(status="SOURCE_BOUND_D2_V10_CASH_POLICY_READY_FOR_E2", action="no_order",
        formal_eligibility=False, main_range_adopted=False, condition_price=None,
        symbol=task["symbol"], task_id=task_id, research_as_of=task["research_as_of"],
        policy_years=policies, annual_operating_candidates=candidates,
        annual_operating_status="SAME_TASK_COMPILED", input_manifest=manifest,
        input_fingerprint=fingerprint,
        blockers=["PARENT_CASH_FACTS_AND_OPENING_CAPITAL_REQUIRED",
                  "MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED",
                  "CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED"],
        scope="CONDITIONAL_UNAPPROVED_D2_V10_POLICY_NOT_VALUATION_OR_PRICE")
