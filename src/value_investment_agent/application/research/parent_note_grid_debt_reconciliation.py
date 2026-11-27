"""Replay the accepted annual stress arithmetic without admitting a financing balance."""
import json

from .direct_owner_cash_policy_capital_v1 import validate_policy_debt


def stress_reconciliation(service, spec, state):
    basis = spec.get("policy_capital_basis") or {}
    if (basis.get("scope") != "ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"
            or spec.get("terminal_response_wire") != "NOTE_GRID_FLAT_TERMINAL_V1"
            or state.get("error_code") != "BEAR_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID"):
        return None
    packet = service._bound(state["responses"]["bear.policy"])
    if (packet.get("source_fingerprint") != spec["source_fingerprint"]
            or packet.get("scenario") != "bear.policy"):
        raise ValueError("PARENT_POLICY_SOURCE_BINDING_MISMATCH")
    policy = json.loads(packet["response"]["text"])
    path = validate_policy_debt(basis, policy)
    return dict(status="FINANCING_BALANCE_UNVERIFIED", scope=basis["scope"],
                annual_path=path, stress_closing_cny=path[-1]["closing_debt_cny"],
                verified_financing_balance_cny=None, action="no_order")

def review_sealed_terminal(service, task_id, binding, now):
    """Rebuild the original request and check the normalized reply without paying again."""
    from datetime import datetime
    from . import parent_note_grid_task_service_v1 as grid
    from .parent_bear_terminal_response_v2 import (
        normalize_bear_terminal_response, sealed_bear_terminal_diagnostic)
    spec, state, _ = service._load(task_id)
    if spec["spec_binding"] != binding or stress_reconciliation(service, spec, state) is None:
        raise ValueError("NOTE_GRID_SEALED_TERMINAL_NOT_APPLICABLE")
    context = service._context(spec, now)
    prior = service._stage_outputs(spec, state, now, verified_context=context)["bear"]
    request = grid.staged_parent_cash_request_v3(root=service.root, spec_binding=binding,
        scenario="bear", stage="terminal", prior_drafts=prior, verified_context=context,
        generated_at=datetime.fromisoformat(spec["created_at"]),
        max_completion_tokens=spec["config"]["max_completion_tokens_cap"])
    wire = service._wire(spec, "terminal", request, root=service.root)
    diagnostic = sealed_bear_terminal_diagnostic(service, task_id, wire_request=wire)
    if not diagnostic or diagnostic["wire_shape"] != "FLAT_SINGLETON_TERMS":
        raise ValueError("NOTE_GRID_REJECTED_TERMINAL_BINDING_INVALID")
    pin = next(p for p in state["returned_responses"] if p["sha256"] == diagnostic["response_sha256"])
    normalized = normalize_bear_terminal_response(grid.LLMResponse(**service._bound(pin)["response"]))
    error = None
    try:
        stage = grid.ParentCashService._parse_stage(service, spec, "terminal", normalized,
            request=request, source_fingerprint=spec["source_fingerprint"])
        service._preflight_terminal(spec, request, stage)
    except ValueError as exc:
        error = str(exc)
    return dict(status="BLOCKED", task_id=task_id, action="no_order",
                reason="NOTE_GRID_FINANCING_BALANCE_UNVERIFIED", term_shapes=diagnostic["term_shape_counts"],
                terminal_validation_error=error, response_sha256=pin["sha256"],
                debt_reconciliation=stress_reconciliation(service, spec, state),
                new_llm_calls=0, formal_eligibility=False)
