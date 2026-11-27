"""Resume a sealed v2 Bear terminal rejection with a debt-conditioned wire."""
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
import json
from pathlib import Path

from . import parent_note_grid_terminal_service_v2 as v2
from .agent_review.task_execution_v1 import _bytes, _hash, _now
from ..product.common import write_new_bytes
from ...infrastructure.agent_runtime.provider import LLMResponse

frozen = v2.frozen
WIRE = "NOTE_GRID_FLAT_TERMINAL_V3"
BASE_BLOCKER = v2.BASE_BLOCKER


def implementation():
    return v2.implementation() | {__name__: _hash(Path(__file__).read_bytes())}


REVIEW_KEYS = ("required_return_basis", "implied_interest_rate", "principal_rollover", "unsupported_commitment")


def _review_wire(flat, observation):
    payload = json.loads(flat.user)
    fields = flat.output_schema["properties"]
    debt = Decimal(payload["forecast_closing_debt_after_annual_years"]["value_cny"])
    if not debt.is_finite() or debt < 0:
        raise ValueError("PARENT_V3_INVALID_CLOSING_DEBT")
    zero, refinancing = fields["financing"]["anyOf"]
    fields["financing"] = refinancing if debt else zero
    payload["sealed_counterevidence"] = observation
    payload["required_return_review"] = dict(
        method_reference="https://pages.stern.nyu.edu/~adamodar/pdfiles/dcfrates.pdf",
        currency="CNY", classification="CONDITIONAL_RESEARCH_HURDLE", unit="annual decimal fraction",
        response_schema=fields["cost_of_equity"],
        basis="CAPM requires a currency-matched risk-free rate, beta and equity risk premium. Without dated market inputs, 10% can only be a conditional research hurdle. Explain the parent equity risk using identified source evidence. Distinguish "
              "observed risk from the assumed premium. Give contrary evidence and a dated "
              "or observable change that would reopen the estimate.")
    payload["terminal_financing_review"] = dict(
        forecast_debt_cny=str(debt), classification="CONDITIONAL_FORECAST_NOT_VERIFIED_DEBT",
        response_schema=fields["financing"],
        basis="Reconcile closing debt to annual borrowing and repayments. For positive debt "
              "explain conditional rollover, matched principal flows and positive cash interest "
              "outside CFO. Address contrary funding evidence and an observable reopen trigger.")
    notes = v2._object(**{key: dict(type="string", minLength=12) for key in REVIEW_KEYS})
    fields["counterevidence_review"] = notes
    flat.output_schema["required"].append("counterevidence_review")
    payload["terminal_response_fields"] = flat.output_schema["required"]
    return replace(flat, user=_bytes(payload).decode("utf-8"), transport_output_contract=(
        flat.transport_output_contract + " Include counterevidence_review with separate explanations of required_return_basis, implied_interest_rate, principal_rollover and unsupported_commitment. Follow required_return_review and terminal_financing_review. "
        "cost_of_equity is an object with values (one decimal string), evidence_anchors, "
        "mechanism, counter_evidence and reopen_condition. Use the balance-specific financing schema."))


class ParentCashService(v2.ParentCashService):
    def _implementation_matches(self, spec):
        if spec.get("terminal_response_wire") == WIRE:
            return spec.get(frozen.grid.MARKER) == frozen.grid.VERSION and spec["implementation_sha256"] == implementation()
        return super()._implementation_matches(spec)

    def _wire(self, spec, stage, request, *, root=None):
        if spec.get("terminal_response_wire") != WIRE:
            return super()._wire(spec, stage, request, root=root)
        view = dict(spec, terminal_response_wire=v2.WIRE)
        wire = super()._wire(view, stage, request, root=root)
        return _review_wire(wire, spec["sealed_counterevidence"]) if v2._bear_terminal(view, stage, request) else wire

    def _parse_stage(self, spec, stage, response, request, source_fingerprint):
        if spec.get("terminal_response_wire") == WIRE:
            spec = dict(spec, terminal_response_wire=v2.WIRE)
            if v2._bear_terminal(spec, stage, request):
                if response.tool_calls or not isinstance(response.text, str) or len(response.text) > 100_000:
                    raise ValueError("NOTE_GRID_TERMINAL_V3_RESPONSE_INVALID")
                body = json.loads(response.text, object_pairs_hook=frozen.grid.native._identical_prose_duplicate_only)
                review = body.pop("counterevidence_review", None) if isinstance(body, dict) else None
                if (not isinstance(review, dict) or set(review) != set(REVIEW_KEYS)
                        or any(not isinstance(note, str) or len(note.strip()) < 12 for note in review.values())
                        or not isinstance(body.get("counter_evidence"), str)):
                    raise ValueError("NOTE_GRID_TERMINAL_V3_COUNTEREVIDENCE_REQUIRED")
                body["counter_evidence"] += " " + " ".join(key + ": " + review[key] for key in REVIEW_KEYS)
                response = replace(response, text=_bytes(body).decode("utf-8"))
        return super()._parse_stage(spec, stage, response, request, source_fingerprint)

    @staticmethod
    def _preflight_terminal(spec, request, parsed):
        if spec.get("terminal_response_wire") == WIRE:
            spec = dict(spec, terminal_response_wire=v2.WIRE)
        return v2.ParentCashService._preflight_terminal(spec, request, parsed)

    def _chain_spend(self, spec, state):
        total = Decimal(0)
        expected = None
        seen = set()
        while True:
            if spec["task_id"] in seen or not self._implementation_matches(spec):
                raise ValueError("NOTE_GRID_TERMINAL_V3_CHAIN_INVALID")
            seen.add(spec["task_id"])
            self._verify_charges(state)
            settled = Decimal(state["settled_cost"])
            prior = Decimal(spec.get("ancestor_spend", "0"))
            if expected is not None and settled + prior != expected:
                raise ValueError("NOTE_GRID_TERMINAL_V3_CHAIN_SPEND_MISMATCH")
            total += settled
            seed = spec.get("seed")
            if seed is None:
                if prior != 0:
                    raise ValueError("NOTE_GRID_TERMINAL_V3_CHAIN_SPEND_MISMATCH")
                return total
            expected = prior
            spec, state, head = self._load(seed["task_id"])
            if head != seed["head"] or spec["task_id"] != seed["task_id"]:
                raise ValueError("NOTE_GRID_TERMINAL_V3_CHAIN_HEAD_CHANGED")

    def run(self, task_id, *, now=None):
        try:
            return super().run(task_id, now=now)
        except v2._BaseFinancingBlocked:
            directory = self._directory(task_id)
            with self._lock(directory, "execution"), self._lock(directory):
                spec, state, head = self._load(task_id)
                if state["status"] == "FAILED" and state.get("error_code") == BASE_BLOCKER:
                    return self._view(spec, state, head, _now(now))
                if (spec.get("terminal_response_wire") != WIRE or state["status"] != "RUNNING"
                        or not v2._base_financing_unverified(spec)
                        or set(state["responses"]) != frozen.PREFIX | {"bear.terminal"}
                        or Decimal(state["reserved_cost"]) != 0
                        or any(row["scenario"] != "bear.terminal" or row["status"] != "SETTLED"
                               for row in state["reservations"].values())
                        or len(state["reservations"]) != 1):
                    raise
                at = _now(now)
                self._verify_charges(state)
                state, head = self._save(spec, state, head, at, status="FAILED", error_code=BASE_BLOCKER)
                return self._view(spec, state, head, at)

    def continue_bear_terminal_v3(self, predecessor, binding, *, now=None):
        now = _now(now)
        parent, failed, head = self._load(predecessor)
        mode = "TEST_ONLY_PARENT_CASH_V3" if self.test_provider is not None else "LIVE_PARENT_CASH_V3"
        if (parent.get(frozen.grid.MARKER) != frozen.grid.VERSION
                or parent.get("terminal_response_wire") != v2.WIRE
                or not self._implementation_matches(parent) or not parent.get("seed")
                or parent["mode"] != mode or parent["spec_binding"] != binding or failed["status"] != "FAILED"
                or not (failed.get("error_code") or "").startswith("BEAR_TERMINAL_") or set(failed["responses"]) != frozen.PREFIX
                or Decimal(failed["reserved_cost"]) != 0
                or any(row["status"] != "SETTLED" for row in failed["reservations"].values())):
            raise ValueError("NOTE_GRID_TERMINAL_V3_PREDECESSOR_INELIGIBLE")
        context = self._context(parent, now)
        outputs = self._stage_outputs(parent, failed, now, verified_context=context)
        request = frozen.grid.staged_parent_cash_request_v3(root=self.root, spec_binding=binding,
            scenario="bear", stage="terminal", prior_drafts=outputs["bear"],
            generated_at=datetime.fromisoformat(parent["created_at"]), verified_context=context,
            max_completion_tokens=parent["config"]["max_completion_tokens_cap"])
        original_wire = self._wire(parent, "terminal", request, root=self.root)
        diagnostic = v2.wire.sealed_bear_terminal_diagnostic(self, predecessor, wire_request=original_wire)
        if not diagnostic or diagnostic["stage"] != "bear.terminal":
            raise ValueError("NOTE_GRID_TERMINAL_V3_REJECTED_RESPONSE_REQUIRED")
        refs = [ref for ref in failed["returned_responses"] if ref["sha256"] == diagnostic["response_sha256"]]
        if len(refs) != 1 or self._load(predecessor)[2] != head:
            raise ValueError("NOTE_GRID_TERMINAL_V3_PREDECESSOR_CHANGED")
        response = self._bound(refs[0])["response"]
        try:
            v2._validated_response(LLMResponse(**response), request)
        except ValueError as error:
            if failed["error_code"] != "BEAR_TERMINAL_" + str(error):
                raise ValueError("NOTE_GRID_TERMINAL_V3_REJECTION_CHANGED") from error
        else:
            raise ValueError("NOTE_GRID_TERMINAL_V3_REJECTION_REQUIRED")
        raw = json.loads(response["text"], object_pairs_hook=frozen.grid.native._identical_prose_duplicate_only)
        if (response.get("tool_calls") or not isinstance(raw, dict)
                or not isinstance(raw.get("cost_of_equity"), str) or raw.get("financing", False) is not None):
            raise ValueError("NOTE_GRID_TERMINAL_V3_SEALED_SHAPE_REQUIRED")
        debt = Decimal(json.loads(original_wire.user)["forecast_closing_debt_after_annual_years"]["value_cny"])
        def amount(field):
            term = raw["policy"][field]
            values = term.get("values", [term.get("value")])
            if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], str):
                raise ValueError("NOTE_GRID_TERMINAL_V3_SEALED_AMOUNT_INVALID")
            value = Decimal(values[0])
            if not value.is_finite() or value < 0:
                raise ValueError("NOTE_GRID_TERMINAL_V3_SEALED_AMOUNT_INVALID")
            return value

        interest = amount("interest_outside_cfo")
        observation = dict(response_binding=refs[0], classification="REJECTED_MODEL_OBSERVATIONS",
            required_return=raw["cost_of_equity"], forecast_stress_balance_cny=str(debt),
            cash_interest_cny=str(interest), implied_annual_interest_percent=str(interest * 100 / debt) if debt else None,
            new_borrowing_cny=str(amount("new_borrowing")), repayment_cny=str(amount("debt_repayment")),
            financing=None, terminal_commitments_cny=str(amount("commitments_outside_capex")),
            prior_commitment_assessment=raw.get("prior_commitment_assessment"))
        from .parent_cash_task_completion_v1 import preflight_parent_cash_task
        case, paid = preflight_parent_cash_task(self, binding, symbol=context["symbol"])
        if case != parent["case_package_binding"] or paid != parent["implemented_distribution_receipt_binding"]:
            raise ValueError("NOTE_GRID_TERMINAL_REGISTRATION_CHANGED")
        spend = self._chain_spend(parent, failed)
        if spend >= Decimal(str(parent["config"]["max_run_cost"])):
            raise ValueError("PARENT_TASK_BUDGET_EXHAUSTED")
        task_id = "rt-" + _hash(_bytes([WIRE, predecessor, head]))[:32]
        seed = dict(task_id=predecessor, head=head, responses=dict(failed["responses"]))
        spec = dict(parent, task_id=task_id, seed=seed, ancestor_spend=str(spend),
            terminal_response_wire=WIRE, replay_from_stage="bear.terminal",
            sealed_counterevidence=observation, implementation_sha256=implementation())
        # Preserve created_at so frozen replay reconstructs the original two request hashes.
        state = dict(status="QUEUED", responses=dict(seed["responses"]), reservations={},
            provider_requests=0, usage=dict(prompt_tokens=0, completion_tokens=0),
            reserved_cost="0", settled_cost="0", action="no_order", formal_eligibility=False,
            error_code=None, new_llm_calls=0)
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                old, saved, pin = self._load(task_id)
                if old != spec:
                    raise ValueError("PARENT_REQUEST_KEY_CONFLICT")
                return self._view(old, saved, pin, now)
            self._stage_outputs(spec, state, now, verified_context=context)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)
