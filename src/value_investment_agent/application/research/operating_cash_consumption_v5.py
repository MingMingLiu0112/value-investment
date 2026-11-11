"""Consume a strictly equivalent format repair without upgrading economic eligibility."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
from . import operating_cash_consumption_v2 as prior
from .agent_review.operating_horizon_sources_v1 import build_operating_horizon_source_context as build_operating_source_context
from ...domain.research.operating_cash_consumption_v1 import consume_operating_earnings
from ...domain.research.operating_scope_decomposition_v1 import validate_scope_decomposition

VERSION = "operating-cash-consumption-v5"


def _registered_horizon_tasks(*, root, symbol):
    """Read every durable annual-task contract without restoring stale success.

    v3 is a one-off JSON-repair contract and remains historical evidence. New
    annual research is written by v1, so reading v3 alone would falsely hide a
    newly completed task. The newest committed task across contracts remains
    decisive even when that task has failed.
    """
    from .agent_review import operating_horizon_task_v1 as horizon_v1
    from .agent_review import operating_horizon_task_v2 as horizon_v2
    from .agent_review import operating_horizon_task_v3 as horizon_v3

    records = []
    for contract, service_type in (
        ("operating-horizon-task-v1", horizon_v1.OperatingHorizonTaskService),
        ("operating-horizon-task-v2", horizon_v2.OperatingHorizonTaskService),
        ("operating-horizon-task-v3", horizon_v3.OperatingHorizonTaskService),
    ):
        for task in service_type(root).list_for_symbol(symbol):
            records.append(dict(task, task_contract_version=contract))
    return records


def _scope_decomposition_status(scope_decomposition, *, known_evidence_ids):
    """Classify only an explicit, source-bound operating-scope assessment.

    Annual research may remain readable without this assessment, but it cannot
    silently imply that a company has no consolidation or scope-change effect.
    This status does not adopt a forecast, a shareholder-cash policy, or a
    valuation conclusion.
    """
    if scope_decomposition is None:
        return "SCOPE_CHANGE_APPLICABILITY_NOT_DECLARED"
    if set(scope_decomposition) != {"scope_change_expected", "contributions"}:
        raise ValueError("SCOPE_DECOMPOSITION_DECLARATION_INVALID")
    expected = scope_decomposition["scope_change_expected"]
    if type(expected) is not bool:
        raise ValueError("SCOPE_CHANGE_EXPECTATION_INVALID")
    contributions = validate_scope_decomposition(
        scope_decomposition["contributions"],
        known_evidence_ids=known_evidence_ids,
        scope_change_expected=expected,
    )
    return "SCOPE_CHANGE_VERIFIED" if expected else "STABLE_SCOPE_VERIFIED"


def read_annual_supplement(*, root, symbol, now):
    tasks = _registered_horizon_tasks(root=root, symbol=symbol)
    if not tasks:
        return dict(status="NOT_STARTED", action="no_order", years={})
    # Latest request is visible even when failed. Do not silently restore an older success.
    task = max(tasks, key=lambda row: (row["created_at"], row["task_id"]))
    if now.utcoffset() is None:
        raise ValueError("AWARE_SUPPLEMENT_CUTOFF_REQUIRED")
    for key in ("created_at", "updated_at", "research_as_of"):
        available = datetime.fromisoformat(task[key])
        if available.utcoffset() is None or available > now:
            raise ValueError("HORIZON_TASK_AFTER_CONSUMPTION_CUTOFF")
    if task.get("repair_requested_at"):
        requested=datetime.fromisoformat(task["repair_requested_at"])
        if requested.utcoffset() is None or requested > now:
            raise ValueError("HORIZON_REPAIR_AFTER_CONSUMPTION_CUTOFF")
    if task.get("execution_mode") != "LIVE_OPERATING":
        return dict(task_id=task["task_id"], status="TEST_ONLY_NOT_REAL_RESEARCH",
            execution_mode=task.get("execution_mode"), action="no_order", years={}, formal_eligibility=False)
    output = dict(task_id=task["task_id"], task_status=task["status"], execution_mode=task["execution_mode"],
        status="PENDING", action="no_order", formal_eligibility=False,
        independent_review="REQUIRED_NOT_APPROVED", years={},
        record_binding=task["record_binding"], research_as_of=task["research_as_of"],
        repair_of=task.get("repair_of"), repair_requested_at=task.get("repair_requested_at"),
        semantic_preservation=task.get("semantic_preservation"))
    if task["status"] != "SUCCEEDED":
        output.update(status=task["status"], reason=task.get("error_code"))
        return output
    ctx = build_operating_source_context(root=root, symbol=symbol,
        binding=task["source_binding"], now=datetime.fromisoformat(task["research_as_of"]))
    if ctx["snapshot_fingerprint"] != task["context_fingerprint"]:
        raise ValueError("HORIZON_SOURCE_CONTEXT_CHANGED")
    scope_status = _scope_decomposition_status(
        ctx.get("scope_decomposition"),
        known_evidence_ids={item["id"] for item in ctx["evidence"]},
    )
    research = task["research_result"]
    generated = datetime.fromisoformat(research["generated_at"])
    if generated.utcoffset() is None or generated > now:
        raise ValueError("HORIZON_RESPONSE_AFTER_CONSUMPTION_CUTOFF")
    if research["symbol"] != symbol or research["formal_eligibility"] is not False:
        raise ValueError("HORIZON_ISSUER_OR_QUALIFICATION_MISMATCH")
    # E2 consumes the explicit v2 cost-mechanism contract.  The older v1
    # annual draft is still a valid unapproved D2 research artifact, but it
    # has no lawful default for this required input and therefore cannot be
    # silently promoted into a shareholder-cash candidate.
    if research.get("schema_version") != "operating-horizon-draft-v2":
        output.update(status="D2_DRAFT_CONTRACT_NOT_E2_COMPATIBLE",
            reason="UNIT_COST_MECHANISM_CONTRACT_REQUIRED",
            draft_schema_version=research.get("schema_version"))
        return output
    for year, row in research["years"].items():
        bridge = dict(paths=row["calculated_paths"], inputs=row["operating_paths"], action="no_order")
        earnings = consume_operating_earnings(context=ctx, bridge=bridge)
        earnings["task_id"] = task["task_id"]
        compiled = prior.compile_verified_annual_candidates(consumed=earnings,
            opening_date=ctx["financial_basis"], asof=task["research_as_of"])
        output["years"][year] = dict(estimate_kind=row["estimate_kind"],
            counter_evidence=row["counter_evidence"], reopen_condition=row["reopen_condition"],
            scenarios=compiled["scenarios"], earnings=earnings["scenarios"],
            unit_cost_mechanisms=row["unit_cost_mechanisms"],
            quantification_status=research["quantification_status"],
            capital_assumptions={name:p["capital_assumptions"] for name,p in row["operating_paths"].items()})
    output.update(status="ANNUAL_SUPPLEMENT_COMPILED_NOT_CASH_POLICY",
        source_binding=task["source_binding"], context_fingerprint=task["context_fingerprint"],
        research_as_of=task["research_as_of"], cash_model_ready=False, condition_price=None,
        scope_decomposition_status=scope_status,
        limitation="Whole-year estimates are not actuals. No selected coherent main path, cash policy, terminal, or approval is supplied.")
    return output


def read_operating_cash_consumption(*, root, task, now):
    from . import operating_cash_consumption_v4 as historical
    result = historical.read_operating_cash_consumption(root=root, task=task, now=now)
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
    raw=json.dumps(dict(prior=result["preceding_consumption_fingerprint"], supplement=supplement,
        implementation=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),
        sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(",", ":")).encode()
    result["consumption_fingerprint"] = hashlib.sha256(raw).hexdigest()
    return result
