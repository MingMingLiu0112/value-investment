"""Resume a settled malformed terminal without repurchasing accepted stages."""
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from . import parent_note_grid_task_service_v1 as grid
from .agent_review.task_execution_v1 import _bytes, _hash, _now
from ..product.common import write_new_bytes

WIRE = "NOTE_GRID_FLAT_TERMINAL_V1"
ERROR = "BEAR_TERMINAL_PARENT_V3_INVALID_JSON"
PREFIX = {"bear.operating", "bear.policy"}


class ParentCashService(grid.ParentCashService):
    def _implementation_matches(self, spec):
        if spec.get("terminal_response_wire") != WIRE:
            return super()._implementation_matches(spec)
        pins = grid.implementation() | {__name__: _hash(Path(__file__).read_bytes())}
        return spec.get(grid.MARKER) == grid.VERSION and spec["implementation_sha256"] == pins

    def _wire(self, spec, stage, request, *, root=None):
        wire = super()._wire(spec, stage, request, root=root)
        if stage == "terminal" and spec.get("terminal_response_wire") == WIRE:
            flat = grid.native._flat_terminal_review_request(
                wire, distribution_reference=spec["implemented_distribution_receipt_binding"])
            contract = ("Return exactly one JSON object. Write cost_of_equity first, then "
                        + ", ".join(k for k in flat.output_schema["required"] if k != "cost_of_equity")
                        + ". All fields are siblings. Do not wrap them in terminal. "
                        "Use exactly these policy fields: "
                        + ", ".join(flat.output_schema["properties"]["policy"]["required"])
                        + ". Every policy item and cost_of_equity has values (one decimal string), "
                        "evidence_anchors, mechanism, counter_evidence and reopen_condition. "
                        "Retain the stationary cash, financing and distribution checks in the input. "
                        "Total parent liabilities are a stress ceiling, not a repayment schedule.")
            return replace(flat, transport_output_contract=contract)
        return wire

    def _parse_stage(self, spec, stage, response, request, source_fingerprint):
        if stage == "terminal" and spec.get("terminal_response_wire") == WIRE:
            response = grid.native._unpack_flat_terminal_review_response(response)
        return super()._parse_stage(spec, stage, response, request, source_fingerprint)

    def continue_terminal(self, predecessor, active_binding, *, now=None):
        now = _now(now)
        parent, previous, head = self._load(predecessor)
        if (parent.get(grid.MARKER) != grid.VERSION or parent.get("seed")
                or parent["spec_binding"] != active_binding or previous["status"] != "FAILED"
                or previous["error_code"] != ERROR or set(previous["responses"]) != PREFIX
                or Decimal(previous["reserved_cost"]) != 0
                or any(row["status"] != "SETTLED" for row in previous["reservations"].values())
                or parent["mode"] != ("TEST_ONLY_PARENT_CASH_V3" if self.test_provider is not None
                                       else "LIVE_PARENT_CASH_V3")):
            raise ValueError("NOTE_GRID_TERMINAL_PREDECESSOR_INELIGIBLE")
        context = self._context(parent, now)
        from .parent_cash_task_completion_v1 import preflight_parent_cash_task
        case, paid = preflight_parent_cash_task(self, active_binding, symbol=context["symbol"])
        if case != parent["case_package_binding"] or paid != parent["implemented_distribution_receipt_binding"]:
            raise ValueError("NOTE_GRID_TERMINAL_REGISTRATION_CHANGED")
        spend = Decimal(previous["settled_cost"])
        if spend >= Decimal(str(parent["config"]["max_run_cost"])):
            raise ValueError("PARENT_TASK_BUDGET_EXHAUSTED")
        task_id = "rt-" + _hash(_bytes([WIRE, predecessor, head]))[:32]
        seed = dict(task_id=predecessor, head=head, responses=previous["responses"])
        spec = dict(parent, task_id=task_id, seed=seed, ancestor_spend=str(spend),
                    terminal_response_wire=WIRE, replay_from_stage="bear.terminal",
                    implementation_sha256=grid.implementation() | {__name__: _hash(Path(__file__).read_bytes())})
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
            # This checks parent head, charge ledger, request hashes and both parsers.
            self._stage_outputs(spec, state, now, verified_context=context)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)
