"""Replay the accepted annual stress arithmetic without admitting a financing balance."""
from decimal import Decimal, InvalidOperation
import json

from .direct_owner_cash_policy_capital_v1 import validate_policy_debt


def stress_reconciliation(service, spec, state):
    basis = spec.get("policy_capital_basis") or {}
    if (basis.get("scope") != "ALL_PARENT_LIABILITIES_UPPER_BOUND_NOT_FINANCING_FACT"
            or spec.get("terminal_response_wire") not in {"NOTE_GRID_FLAT_TERMINAL_V1", "NOTE_GRID_FLAT_TERMINAL_V3"}
            or state.get("error_code") != "BEAR_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID"):
        return None
    packet = service._bound(state["responses"]["bear.policy"])
    if (packet.get("source_fingerprint") != spec["source_fingerprint"]
            or packet.get("scenario") != "bear.policy"):
        raise ValueError("PARENT_POLICY_SOURCE_BINDING_MISMATCH")
    policy = json.loads(packet["response"]["text"])
    path = validate_policy_debt(basis, policy)
    terminal_arithmetic = None
    unbound_policy_terms = []
    operating_cash_bridge = None
    if spec.get("terminal_response_wire") == "NOTE_GRID_FLAT_TERMINAL_V3":
        for binding in state.get("returned_responses", ()):
            sealed = service._bound(binding)
            if (sealed.get("scenario") != "bear.terminal"
                    or sealed.get("source_fingerprint") != spec["source_fingerprint"]):
                continue
            try:
                draft = json.loads(sealed["response"]["text"])
                from .parent_bear_terminal_response_v2 import _normalize_terms
                for name, term in draft["policy"].items():
                    try:
                        _normalize_terms({"cost_of_equity": term, "policy": {}})
                    except ValueError:
                        unbound_policy_terms.append(name)
                operating_ref = state["responses"]["bear.operating"]
                operating = service._bound(operating_ref)
                if (operating.get("scenario") != "bear.operating"
                        or operating.get("source_fingerprint") != spec["source_fingerprint"]):
                    raise ValueError("PARENT_OPERATING_SOURCE_BINDING_MISMATCH")
                annual = json.loads(operating["response"]["text"])
                fields = ("revenue", "cost", "other_operating_cash")
                series = annual["series"]
                revenue, cost, other_cash = (Decimal(series[key]["values"][-1]) for key in fields)
                submitted = draft["policy"]["operating_cash"]
                if isinstance(submitted, dict):
                    submitted = submitted["values"][0]
                cfo = revenue - cost + other_cash
                operating_cash_bridge = dict(
                    forecast_year=annual["years"][-1],
                    continuity_cash_cny=str(cfo),
                    rejected_cash_cny=str(submitted),
                    gap_cny=str(Decimal(submitted) - cfo),
                    evidence_anchors=sorted({anchor for key in fields for anchor in series[key]["evidence_anchors"]}),
                    source_sha256=operating_ref["sha256"],
                    status="CONDITIONAL_CONTINUITY_REQUIRES_TERMINAL_SUPPORT",
                )
                term = draft["policy"]["interest_outside_cfo"]
                interest = term["values"][0] if isinstance(term, dict) else term
                terminal_arithmetic = terminal_financing_arithmetic(path[-1]["closing_debt_cny"], interest)
            except (KeyError, IndexError, TypeError, ValueError, InvalidOperation):
                continue
    return dict(status="FINANCING_BALANCE_UNVERIFIED", scope=basis["scope"],
                terminal_arithmetic=terminal_arithmetic,
                operating_cash_bridge=operating_cash_bridge,
                legacy_terminal_review_available=spec.get("terminal_response_wire") == "NOTE_GRID_FLAT_TERMINAL_V1",
                unbound_policy_terms=sorted(set(unbound_policy_terms)),
                annual_path=path, stress_closing_cny=path[-1]["closing_debt_cny"],
                verified_financing_balance_cny=None, action="no_order")

def review_sealed_terminal(service, task_id, binding, now):
    """Rebuild the original request and check the normalized reply without paying again."""
    from datetime import datetime
    from . import parent_note_grid_task_service_v1 as grid
    from .parent_bear_terminal_response_v2 import (
        normalize_bear_terminal_response, sealed_bear_terminal_diagnostic)
    spec, state, _ = service._load(task_id)
    if (spec["spec_binding"] != binding or spec.get("terminal_response_wire") != "NOTE_GRID_FLAT_TERMINAL_V1"
            or stress_reconciliation(service, spec, state) is None):
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


def terminal_financing_arithmetic(closing_debt_cny, interest_outside_cfo_cny):
    """Recompute the implied percentage from numeric amounts in a sealed draft."""
    from decimal import Decimal, InvalidOperation

    try:
        debt = Decimal(closing_debt_cny)
        interest = Decimal(interest_outside_cfo_cny)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("PARENT_TERMINAL_FINANCING_AMOUNT_INVALID") from error
    if any(not value.is_finite() or value < 0 for value in (debt, interest)):
        raise ValueError("PARENT_TERMINAL_FINANCING_AMOUNT_INVALID")
    if debt == 0 and interest > 0:
        raise ValueError("PARENT_TERMINAL_INTEREST_WITHOUT_DEBT")
    return {
        "closing_debt_cny": str(debt),
        "interest_outside_cfo_cny": str(interest),
        "implied_annual_interest_percent": str(interest * 100 / debt) if debt else None,
        "classification": "REJECTED_DRAFT_ARITHMETIC_ONLY",
    }
