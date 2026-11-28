"""Versioned continuation of a sealed Bear terminal shape failure."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path

from . import parent_bear_terminal_response_v2 as wire
from . import parent_note_grid_terminal_resume as frozen
from .agent_review.task_execution_v1 import _bytes, _hash, _now
from ..product.common import write_new_bytes
from ...domain.valuation.direct_parent_owner_cash_v1 import _terminal_financing

WIRE = wire.WIRE
ERROR = "BEAR_TERMINAL_PARENT_DRAFT_TERM_SOURCE_INVALID"
BASE_BLOCKER = "PARENT_V3_BASE_OPENING_FINANCING_BALANCE_UNVERIFIED"


def implementation():
    return frozen.grid.implementation() | {
        module.__name__: _hash(Path(module.__file__).read_bytes()) for module in (frozen, wire)
    } | {__name__: _hash(Path(__file__).read_bytes())}


def _object(**fields):
    return dict(type="object", additionalProperties=False, required=list(fields), properties=fields)


def _terminal_wire(request, distribution, commitment):
    flat = frozen.grid.native._flat_terminal_review_request(request, distribution_reference=distribution)
    prose = dict(type="string", minLength=12)
    flat.output_schema["properties"].update(
        max_transition_years=dict(type="integer", minimum=1, maximum=100),
        financing=dict(anyOf=[dict(type="null"), _object(
            mode=dict(const="CONSTANT_DEBT_REFINANCING"), rationale=prose, counter_evidence=prose,
            reopen_condition=prose, coverage=_object(interest_outside_cfo=dict(const=True),
                debt_scope=dict(const="ALL_EXISTING_TERMINAL_DEBT")))]),
        remaining_scheduled_events=dict(type="array", items=_object(event_id=dict(type="string"),
            status=dict(enum=["CONSUMED", "UNRESOLVED"]), distribution_total_cny=dict(type="string"),
            mechanism=prose)),
    )
    schema = flat.output_schema
    schema["properties"]["prior_commitment_assessment"] = _object(
        evidence_status=dict(enum=["SUPPORTED", "INSUFFICIENT_EVIDENCE"]), explanation=prose)
    schema["required"].append("prior_commitment_assessment")
    payload = json.loads(flat.user)
    payload["terminal_response_fields"] = schema["required"]
    payload["prior_rejected_commitment_observation"] = commitment
    return replace(flat, user=_bytes(payload).decode("utf-8"),
        transport_output_contract=(
            "Return exactly one flat JSON object with these fields: "
            + ", ".join(schema["required"])
            + ". Policy has exactly: " + ", ".join(schema["properties"]["policy"]["required"])
            + ". Only cost_of_equity and policy terms use singleton values (one decimal string), "
            "evidence_anchors, mechanism, counter_evidence and reopen_condition. "
            "max_transition_years is an integer 1–100. financing is null for zero terminal debt; "
            "otherwise use mode CONSTANT_DEBT_REFINANCING, rationale, counter_evidence, "
            "reopen_condition and coverage with interest_outside_cfo=true and "
            "debt_scope=ALL_EXISTING_TERMINAL_DEBT. "
            "Each event has event_id, status, distribution_total_cny and mechanism. "
            "Mark the implemented distribution CONSUMED with the exact ID and amount in "
            "source_context.implemented_distribution; flag outstanding events UNRESOLVED. "
            "Do not pay a consumed distribution again. prior_commitment_assessment has "
            "evidence_status SUPPORTED or INSUFFICIENT_EVIDENCE and a specific explanation. "
            "The prior amount is a rejected model observation. Identify source and timing, "
            "or explain the lack of support and the basis for the proposed terminal treatment. "
            "Preserve real verified commitments and the parent cash, profit, payout and financing checks. "
            "Treat parent total liabilities only as a stress ceiling."
        ))



def _validated_response(response, request):
    if response.tool_calls:
        raise ValueError("PARENT_V3_TERMINAL_DRIVER_TOOL_CALL_FORBIDDEN")
    if not isinstance(response.text, str) or len(response.text) > 100_000:
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_INVALID_JSON")
    try:
        packet = json.loads(response.text, object_pairs_hook=frozen.grid.native._identical_prose_duplicate_only)
    except (json.JSONDecodeError, RecursionError) as error:
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_INVALID_JSON") from error
    assessment = packet.pop("prior_commitment_assessment", None) if isinstance(packet, dict) else None
    if (not isinstance(assessment, dict) or set(assessment) != {"evidence_status", "explanation"}
            or assessment["evidence_status"] not in ("SUPPORTED", "INSUFFICIENT_EVIDENCE")
            or not isinstance(assessment["explanation"], str) or len(assessment["explanation"].strip()) < 12):
        raise ValueError("PARENT_V3_TERMINAL_PRIOR_COMMITMENT_ASSESSMENT_REQUIRED")
    if not isinstance(packet.get("rationale"), str):
        raise ValueError("PARENT_V3_TERMINAL_REVIEW_FIELDS_INVALID")
    packet["rationale"] += " Prior commitment review (" + assessment["evidence_status"] + "): " + assessment["explanation"]
    normalized = wire.normalize_bear_terminal_response(replace(response, text=_bytes(packet).decode("utf-8")))
    value = json.loads(normalized.text)
    terminal = value["terminal"]
    years = terminal["max_transition_years"]
    if type(years) is not int or not 1 <= years <= 100:
        raise ValueError("PARENT_V3_TERMINAL_TRANSITION_YEARS_INVALID")
    payload = json.loads(request.user)
    distribution = payload["source_context"]["implemented_distribution"]
    paid = distribution["distribution"]
    events = terminal["remaining_scheduled_events"]
    if not isinstance(events, list):
        raise ValueError("PARENT_V3_TERMINAL_EVENTS_INVALID")
    consumed = 0
    for event in events:
        if (not isinstance(event, dict)
                or set(event) != {"event_id", "status", "distribution_total_cny", "mechanism"}
                or not isinstance(event["mechanism"], str) or len(event["mechanism"].strip()) < 12):
            raise ValueError("PARENT_V3_TERMINAL_EVENTS_INVALID")
        if event["status"] == "UNRESOLVED":
            raise ValueError("PARENT_V3_TERMINAL_UNRESOLVED_SCHEDULED_EVENTS")
        if (event["status"] != "CONSUMED" or event["event_id"] != distribution["event_id"]
                or event["distribution_total_cny"] != paid["total_cny"]
                or date.fromisoformat(paid["paid_date"]).year > payload["terminal_reference_year"]):
            raise ValueError("PARENT_V3_TERMINAL_CONSUMED_EVENT_MISMATCH")
        consumed += 1
    if consumed != 1:
        raise ValueError("PARENT_V3_TERMINAL_CONSUMED_EVENT_REQUIRED")
    # The frozen parser sees outstanding events only; the sealed response keeps the audit item.
    terminal["remaining_scheduled_events"] = []
    return replace(normalized, text=_bytes(value).decode("utf-8"))


def _bear_terminal(spec, stage, request):
    return (spec.get("terminal_response_wire") == WIRE and stage == "terminal"
            and json.loads(request.user)["scenario"] == "bear")


class _BaseFinancingBlocked(ValueError):
    pass


def _base_financing_unverified(spec):
    basis = spec.get("policy_capital_basis", {})
    return basis.get("scope") != "SPECIFIED_OPENING_DEBT_BASIS" or basis.get("fact_field") == "liabilities_cny"


class ParentCashService(frozen.ParentCashService):
    def _implementation_matches(self, spec):
        if spec.get("terminal_response_wire") != WIRE:
            return super()._implementation_matches(spec)
        return spec.get(frozen.grid.MARKER) == frozen.grid.VERSION and spec["implementation_sha256"] == implementation()

    def _wire(self, spec, stage, request, *, root=None):
        if (spec.get("terminal_response_wire") == WIRE and stage == "operating"
                and json.loads(request.user)["scenario"] == "base" and _base_financing_unverified(spec)):
            raise _BaseFinancingBlocked(BASE_BLOCKER)
        request = super()._wire(spec, stage, request, root=root)
        if _bear_terminal(spec, stage, request):
            return _terminal_wire(request, spec["implemented_distribution_receipt_binding"],
                                  spec["prior_rejected_commitment_observation"])
        return request

    def _parse_stage(self, spec, stage, response, request, source_fingerprint):
        if _bear_terminal(spec, stage, request):
            response = _validated_response(response, request)
        return super()._parse_stage(spec, stage, response, request, source_fingerprint)

    @staticmethod
    def _preflight_terminal(spec, request, parsed):
        frozen.ParentCashService._preflight_terminal(spec, request, parsed)
        if not _bear_terminal(spec, "terminal", request):
            return
        terminal = parsed["terminal"]
        projected = json.loads(request.user)["forecast_closing_debt_after_annual_years"]
        flow = {key: Decimal(terminal["policy"][key]["values"][0])
                for key in ("debt_repayment", "new_borrowing", "interest_outside_cfo")}
        terms = {} if terminal["financing"] is None else {"financing": terminal["financing"]}
        try:
            _terminal_financing(terms, {"debt": Decimal(projected["value_cny"])}, flow)
        except ValueError as error:
            raise ValueError("PARENT_V3_TERMINAL_TYPED_FINANCING_REJECTED") from error
    def run(self, task_id, *, now=None):
        try:
            return super().run(task_id, now=now)
        except _BaseFinancingBlocked:
            directory = self._directory(task_id)
            with self._lock(directory, "execution"), self._lock(directory):
                spec, state, head = self._load(task_id)
                if state["status"] == "FAILED" and state.get("error_code") == BASE_BLOCKER:
                    return self._view(spec, state, head, _now(now))
                if (spec.get("terminal_response_wire") != WIRE or state["status"] != "RUNNING"
                        or not _base_financing_unverified(spec)
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

    def continue_bear_terminal_v2(self, predecessor, binding, *, now=None):
        now = _now(now)
        parent, failed, head = self._load(predecessor)
        mode = "TEST_ONLY_PARENT_CASH_V3" if self.test_provider is not None else "LIVE_PARENT_CASH_V3"
        if (parent.get(frozen.grid.MARKER) != frozen.grid.VERSION
                or parent.get("terminal_response_wire") != frozen.WIRE
                or not self._implementation_matches(parent) or not parent.get("seed")
                or parent["mode"] != mode or parent["spec_binding"] != binding or failed["status"] != "FAILED"
                or failed["error_code"] != ERROR or set(failed["responses"]) != frozen.PREFIX
                or Decimal(failed["reserved_cost"]) != 0
                or any(row["status"] != "SETTLED" for row in failed["reservations"].values())):
            raise ValueError("NOTE_GRID_TERMINAL_V2_PREDECESSOR_INELIGIBLE")
        context = self._context(parent, now)
        outputs = self._stage_outputs(parent, failed, now, verified_context=context)
        request = frozen.grid.staged_parent_cash_request_v3(root=self.root, spec_binding=binding,
            scenario="bear", stage="terminal", prior_drafts=outputs["bear"],
            generated_at=datetime.fromisoformat(parent["created_at"]), verified_context=context,
            max_completion_tokens=parent["config"]["max_completion_tokens_cap"])
        original_wire = self._wire(parent, "terminal", request, root=self.root)
        diagnostic = wire.sealed_bear_terminal_diagnostic(self, predecessor, wire_request=original_wire)
        if (not diagnostic or diagnostic["status"] != "REJECTED_RESPONSE_DIAGNOSTIC_ONLY"
                or diagnostic["stage"] != "bear.terminal" or diagnostic["wire_shape"] != "FLAT_SINGLETON_TERMS"
                or not diagnostic["term_shape_counts"]["value"]):
            raise ValueError("NOTE_GRID_TERMINAL_V2_SEALED_SHAPE_REQUIRED")
        matches = [ref for ref in failed["returned_responses"] if ref["sha256"] == diagnostic["response_sha256"]]
        if len(matches) != 1 or self._load(predecessor)[2] != head:
            raise ValueError("NOTE_GRID_TERMINAL_V2_PREDECESSOR_CHANGED")
        packet = self._bound(matches[0])
        raw = wire._read_flat(packet["response"]["text"])
        if wire._normalize_terms(raw) != diagnostic["term_shape_counts"]:
            raise ValueError("NOTE_GRID_TERMINAL_V2_SEALED_SHAPE_REQUIRED")
        amount = Decimal(raw["policy"]["commitments_outside_capex"]["values"][0])
        if not amount.is_finite() or amount < 0:
            raise ValueError("NOTE_GRID_TERMINAL_V2_COMMITMENT_OBSERVATION_INVALID")
        commitment = dict(amount_cny=str(amount), classification="UNVERIFIED_REJECTED_MODEL_OBSERVATION",
                          response_binding=matches[0])
        from .parent_cash_task_completion_v1 import preflight_parent_cash_task
        case, paid = preflight_parent_cash_task(self, binding, symbol=context["symbol"])
        if case != parent["case_package_binding"] or paid != parent["implemented_distribution_receipt_binding"]:
            raise ValueError("NOTE_GRID_TERMINAL_REGISTRATION_CHANGED")
        first = parent["seed"]
        ancestor, previous, original_head = self._load(first["task_id"])
        if (ancestor.get("seed") or original_head != first["head"]
                or Decimal(parent["ancestor_spend"]) != Decimal(previous["settled_cost"])):
            raise ValueError("NOTE_GRID_TERMINAL_V2_ANCESTOR_SPEND_MISMATCH")
        spend = Decimal(previous["settled_cost"]) + Decimal(failed["settled_cost"])
        if spend >= Decimal(str(parent["config"]["max_run_cost"])):
            raise ValueError("PARENT_TASK_BUDGET_EXHAUSTED")
        task_id = "rt-" + _hash(_bytes([WIRE, predecessor, head]))[:32]
        seed = dict(task_id=predecessor, head=head, responses=dict(failed["responses"]))
        spec = dict(parent, task_id=task_id, seed=seed, ancestor_spend=str(spend),
            terminal_response_wire=WIRE, replay_from_stage="bear.terminal",
            prior_rejected_commitment_observation=commitment, implementation_sha256=implementation())
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
