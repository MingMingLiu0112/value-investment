"""Prepare source-bound parent-cash observations for an admitted D2 task.

This is deliberately an E2 preparation boundary, rather than a shortcut to a
cash policy.  It turns separately retained official reports into one immutable
input manifest that later policy/economic work can consume, without treating
historical cash movements as forecast cash capacity.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from .parent_cash_research import replay_bound_parent_cash_observations


SCHEMA = "operating-cash-followup-preparation-v1"


def prepare_operating_cash_followup(*, root: Path, task: dict, issuer_name: str,
                                   receipt_bindings: list[dict], now: datetime) -> dict:
    """Bind official parent-cash observations to one successful D2 task.

    No caller-supplied cash amount is accepted. The result deliberately leaves
    maintenance, working capital, remittances, payout, cash floor and valuation
    unavailable until separate source-bound economic research supplies them.
    """
    base = dict(schema_version=SCHEMA, action="no_order", formal_eligibility=False,
                main_range_adopted=False, condition_price=None, valuation=None)
    if not isinstance(task, dict):
        raise ValueError("OPERATING_TASK_REQUIRED")
    if (task.get("status") != "SUCCEEDED"
            or task.get("scope") != "LIVE_LLM_OPERATING_RESEARCH_NOT_ADMITTED"
            or task.get("action") != "no_order"
            or not isinstance(task.get("symbol"), str)):
        return dict(base, status="NOT_READY", reason="SUCCEEDED_SOURCE_BOUND_D2_TASK_REQUIRED")
    research_as_of = datetime.fromisoformat(task["research_as_of"])
    if research_as_of.utcoffset() is None or now.utcoffset() is None or research_as_of > now:
        raise ValueError("OPERATING_CASH_FOLLOWUP_CLOCK_INVALID")
    observations = replay_bound_parent_cash_observations(
        root=root, symbol=task["symbol"], issuer_name=issuer_name,
        receipt_bindings=receipt_bindings, now=now)
    identity = dict(
        task_id=task.get("task_id"), symbol=task["symbol"], research_as_of=task["research_as_of"],
        task_context_fingerprint=task.get("context_fingerprint"),
        task_source_binding=task.get("source_binding"),
        observation_source_bindings=observations["source_bindings"],
        implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    return dict(base,
        status="SOURCE_BOUND_PARENT_CASH_OBSERVATIONS_READY_FOR_POLICY",
        symbol=task["symbol"], task_id=task.get("task_id"), research_as_of=task["research_as_of"],
        task_source_binding=deepcopy(task.get("source_binding")),
        observations=observations,
        input_manifest=identity,
        input_fingerprint=hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False).encode()).hexdigest(),
        current_blockers=[
            dict(code="EXPLICIT_SAME_PERIOD_CASH_POLICY_REQUIRED", stage="shareholder_cash",
                 explanation="Historical parent-cash observations do not establish maintenance/WC, remittance, payout or cash-floor terms."),
            dict(code="MAIN_ECONOMIC_RANGE_ADOPTION_REQUIRED", stage="economic_research",
                 explanation="The D2 paths remain conditional research witnesses, not an adopted main valuation range."),
            dict(code="CURRENT_CAPITAL_DISTRIBUTION_EVENT_QUOTE_ALIGNMENT_REQUIRED", stage="condition_price",
                 explanation="Financial-period capital/distribution facts are not yet aligned to an eligible current quote."),
        ],
        limitation="No FCFE, distributable cash, policy threshold, valuation or price action is inferred.")
