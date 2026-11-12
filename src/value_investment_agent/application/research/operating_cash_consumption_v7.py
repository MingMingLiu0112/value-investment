"""Consume a strictly transport-normalized D2 response without granting approval.

This is intentionally a narrow bridge for a retained failed v2 response and its
single, semantics-equivalent repair response.  It never marks either task as
successful and never makes the resulting annual supplement a cash policy.
"""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path

from . import operating_cash_consumption_v5 as prior
from .agent_review import operating_horizon_transport_admission_v1 as transport
from .agent_review import operating_horizon_task_v3 as repair
from .agent_review.operating_horizon_sources_v1 import build_operating_horizon_source_context
from ...domain.research.operating_cash_consumption_v1 import consume_operating_earnings
from ...domain.research.operating_scope_decomposition_v1 import validate_scope_decomposition
from . import operating_cash_consumption_v2 as annual_compiler

VERSION = "operating-cash-consumption-v7"


def _scope_decomposition_status(scope_decomposition, *, known_evidence_ids):
    """Return an explicit, non-valuation status for supplied D2 scope evidence."""
    if scope_decomposition is None:
        return "SCOPE_CHANGE_APPLICABILITY_NOT_DECLARED"
    contributions = validate_scope_decomposition(
        scope_decomposition, known_evidence_ids=known_evidence_ids,
    )
    return ("SCOPE_CHANGE_VERIFIED" if any(
        item.scope_kind == "NEWLY_CONSOLIDATED" for item in contributions
    ) else "STABLE_SCOPE_VERIFIED")


def _failed_repair(root, symbol):
    service = repair.OperatingHorizonTaskService(root)
    directory = service._directory(repair.SINGLE_TASK_ID)
    if not (directory / "input.json").is_file():
        return None
    with service._lock(directory):
        spec, state, pin = service._load(repair.SINGLE_TASK_ID)
    if spec["symbol"] != symbol or state["status"] != "FAILED":
        return None
    return spec, state, pin


def _compile(*, root, symbol, now, admitted):
    binding = admitted["transport_binding"]
    original_service = transport.v2.OperatingHorizonTaskService(root)
    with original_service._lock(original_service._directory(binding["original_task_id"])):
        spec, state, _ = original_service._load(binding["original_task_id"])
    if spec["symbol"] != symbol:
        raise ValueError("TRANSPORT_ADMISSION_SOURCE_IDENTITY_CHANGED")
    context = build_operating_horizon_source_context(
        root=root, symbol=symbol, binding=spec["source_binding"],
        now=datetime.fromisoformat(spec["created_at"]),
    )
    if context["snapshot_fingerprint"] != admitted["snapshot_fingerprint"]:
        raise ValueError("TRANSPORT_ADMISSION_CONTEXT_CHANGED")
    # The retained v2 provider response predates the scope contract.  Its annual
    # drivers remain readable, but cannot become a shareholder-cash input until
    # a source-bound legacy/new-consolidation bridge is supplied.
    scope_status = _scope_decomposition_status(
        admitted.get("scope_decomposition"),
        known_evidence_ids={item["id"] for item in context["evidence"]},
    )
    result = dict(
        task_id=binding["original_task_id"],
        transport_admission=deepcopy(binding),
        status="ANNUAL_SUPPLEMENT_TRANSPORT_NORMALIZED_ECONOMIC_REVIEW_REQUIRED",
        transport_status=admitted["transport_status"],
        execution_mode=spec["mode"], action="no_order", formal_eligibility=False,
        independent_review="REQUIRED_NOT_APPROVED", years={},
        source_binding=spec["source_binding"], context_fingerprint=spec["context_fingerprint"],
        research_as_of=spec["created_at"], cash_model_ready=False, condition_price=None,
        scope_decomposition_status=scope_status,
        limitation=("Provider transport formatting was normalized under a retained-byte contract. "
                    "Economic evidence remains conditional: no selected main path, cash policy, "
                    "terminal value or approval is supplied."),
    )
    for year, row in admitted["years"].items():
        bridge = dict(paths=row["calculated_paths"], inputs=row["operating_paths"], action="no_order")
        earnings = consume_operating_earnings(context=context, bridge=bridge)
        earnings["task_id"] = binding["original_task_id"]
        compiled = annual_compiler.compile_verified_annual_candidates(
            consumed=earnings, opening_date=context["financial_basis"], asof=spec["created_at"],
        )
        result["years"][year] = dict(
            estimate_kind=row["estimate_kind"], counter_evidence=row["counter_evidence"],
            reopen_condition=row["reopen_condition"], scenarios=compiled["scenarios"],
            earnings=earnings["scenarios"], unit_cost_mechanisms=row["unit_cost_mechanisms"],
            quantification_status=admitted["quantification_status"],
            capital_assumptions={name: path["capital_assumptions"]
                                 for name, path in row["operating_paths"].items()},
        )
    return result


def read_annual_supplement(*, root, symbol, now):
    failed = _failed_repair(root, symbol)
    if failed is None:
        return prior.read_annual_supplement(root=root, symbol=symbol, now=now)
    spec, state, _ = failed
    if now.utcoffset() is None:
        raise ValueError("AWARE_SUPPLEMENT_CUTOFF_REQUIRED")
    for value in (spec["created_at"], spec["repair_requested_at"], state["updated_at"]):
        clock = datetime.fromisoformat(value)
        if clock.utcoffset() is None or clock > now:
            raise ValueError("HORIZON_TASK_AFTER_CONSUMPTION_CUTOFF")
    admitted = transport.admit(
        root=root,
        original_task_id=spec["repair_of"]["task_id"],
        repair_task_id=spec["task_id"], now=now,
    )
    return _compile(root=root, symbol=symbol, now=now, admitted=admitted)


def read_operating_cash_consumption(*, root, task, now):
    result = prior.read_operating_cash_consumption(root=root, task=task, now=now)
    try:
        supplement = read_annual_supplement(root=root, symbol=task["symbol"], now=now)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        supplement = dict(status="UNASSESSABLE", reason=str(error), years={}, action="no_order")
    if supplement["status"] == "NOT_STARTED":
        return result
    history = list(result.get("annual_research_supplement_history", []))
    for previous in (result.get("historical_annual_research_supplement"), result.get("annual_research_supplement")):
        if previous and previous not in history:
            history.append(previous)
    result["annual_research_supplement_history"] = history
    result["historical_annual_research_supplement"] = result.get("annual_research_supplement")
    result["annual_research_supplement"] = supplement
    result["preceding_consumption_fingerprint"] = result.get("consumption_fingerprint")
    raw = json.dumps(
        dict(prior=result["preceding_consumption_fingerprint"], supplement=supplement,
             implementation=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
        sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
    ).encode()
    result["consumption_fingerprint"] = hashlib.sha256(raw).hexdigest()
    return result
