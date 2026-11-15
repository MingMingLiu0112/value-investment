"""Compact cash-only request for an independently validated annual checkpoint."""

from dataclasses import replace
from hashlib import sha256

from . import operating_cash_policy_draft_v16_generic as cash
from . import operating_draft_v1 as common

VERSION = "operating-cash-request-compact-v1"
MAX_REQUEST_CHARS = 76000


def build_compact_cash_request(context, source_binding, annual_response, annual_generated_at):
    """Retain calculated paths and bind the complete input without repeating drivers."""
    projected = cash._source(context, source_binding, generated_at=annual_generated_at)
    annual = cash.annual.validate_response(annual_response, projected, [2027], annual_generated_at)
    response_text = annual_response.text if hasattr(annual_response, "text") else annual_response
    response_hash = sha256(response_text.encode("utf-8")).hexdigest()
    row = annual["years"]["2027"]
    summary = {
        "year": "2027",
        "estimate_kind": row["estimate_kind"],
        "baseline_period": row["operating_paths"]["base"]["baseline_period"],
        "calculated_paths": row["calculated_paths"],
        "annual_response_sha256": response_hash,
    }
    request = cash.build_request(context, source_binding)
    user = request.user + "\nVALIDATED_ANNUAL_CALCULATIONS=" + common._canonical(summary)
    if len(user) > MAX_REQUEST_CHARS:
        raise ValueError("COMPACT_CASH_REQUEST_OVER_BUDGET")
    request = replace(request, user=user, system=request.system +
        " Reconcile each cash scenario to its corresponding validated annual calculation. "
        "Place counter_evidence and reopen_condition within each individual bear, base, and bull "
        "cash object as strings. The shareholder_cash_paths object contains exactly those three keys.")
    def digest(value):
        return sha256(common._canonical(value).encode("utf-8")).hexdigest()

    return request, {
        "version": VERSION,
        "source_context_sha256": digest(context),
        "source_binding_sha256": digest(source_binding),
        "annual_response_sha256": response_hash,
        "annual_result_sha256": digest(annual),
        "annual_summary_sha256": digest(summary),
        "cash_request_sha256": digest(request.__dict__),
        "action": "no_order",
    }


def prepare_cash_only_continuation(service, task_id):
    """Reverify the immutable annual checkpoint and bind a distinct cash request."""
    from . import operating_horizon_task_v25_canonical as v25

    if not isinstance(service, v25.OperatingHorizonTaskService):
        raise ValueError("V25_CONTINUATION_SERVICE_REQUIRED")
    with service._lock(service._directory(task_id)):
        spec, state, record_binding = service._load(task_id)
        if (state.get("status") != "FAILED"
                or state.get("error_code") != "V25_TASK_EXECUTION_FAILED"
                or state.get("stage_validated") != list(v25.SCENARIOS)
                or "cash" in state.get("stage_intents", {})
                or "cash" in state.get("stage_responses", {})
                or state.get("cash_binding") is not None):
            raise ValueError("V25_CONTINUATION_REQUIRES_UNSENT_CASH_STAGE")
        context = service._context(spec)
        try:
            service._request_for_stage(spec, state, context, "cash")
        except ValueError as error:
            if str(error) != "V16_GENERIC_STAGED_REQUEST_OVER_BUDGET":
                raise
        else:
            raise ValueError("V25_CONTINUATION_ORIGINAL_SIZE_FAILURE_REQUIRED")
        annual, _ = service._annual_checkpoint(spec, state, context)
        request, binding = build_compact_cash_request(
            context, spec["source_binding"], annual, service._annual_generated_at(spec, state))
        return request, {
            **binding, "source_task_id": task_id, "source_task_state": record_binding,
            "source_binding": spec["source_binding"],
            "annual_stage_responses": {name: state["stage_responses"][name] for name in v25.SCENARIOS},
        }
