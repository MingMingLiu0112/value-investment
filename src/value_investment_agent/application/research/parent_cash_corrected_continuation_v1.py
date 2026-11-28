"""Continue the native nine-stage worker with two independently replayed Bear stages."""
from decimal import Decimal
import os
from pathlib import Path
import re

from . import parent_cash_policy_correction_v1 as correction
from .agent_review import parent_cash_task_v3 as native
from ..product.common import require_inside, write_new_bytes

VERSION = "bear-policy-terminal-continuation-v1"
MARKER = "corrected_policy_continuation"
ANNUAL = {"bear.operating", "bear.policy"}


def _pin(service, folder, name, digest):
    path = require_inside(folder, folder / name, "corrected policy artifact")
    binding = dict(path=path.relative_to(service.root).as_posix(), sha256=digest)
    return binding, service._bound(binding)


def _records(service, parent_id, digest):
    folder = correction._folder(service, parent_id)
    binding, receipt = _pin(service, folder, "receipt.json", digest)
    if (receipt.get("status") != "CORRECTION_VERIFIED" or receipt.get("task_id") != parent_id
            or receipt.get("schema_version") != correction.VERSION or receipt.get("next_stage") != "bear.terminal"
            or receipt.get("stage") != "bear.policy" or receipt.get("action") != "no_order"
            or receipt.get("formal_eligibility") is not False):
        raise ValueError("PARENT_VERIFIED_CORRECTION_REQUIRED")
    # The correction v1 reader compares canonical objects. Also bind original file bytes before dispatch.
    response, packet = _pin(service, folder, "response.json", receipt["correction_response_sha256"])
    _, intent = _pin(service, folder, "intent.json", receipt["intent_sha256"])
    dispatch = {k: receipt[k] for k in ("intent_sha256", "correction_request_sha256")}
    _pin(service, folder, "dispatch.json", correction._digest(dispatch))
    context = native.json.loads(intent["original_request"]["user"])["source_context"]
    policy = correction._object(packet["response"]["text"])
    return binding, receipt, response, _limitations(policy, context)


def _child_id(parent_id, digest):
    return "rt-" + correction._digest([VERSION, parent_id, digest])[:32]


def history_fields(service, parent_id, head, correction_fields):
    result = {"financing_policy_terminal_continuation_available": False}
    failed = correction_fields.get("financing_policy_correction_source_sha256")
    if failed is None:
        return result
    path = correction._folder(service, parent_id) / "receipt.json"
    try:
        digest = service._binding(path)["sha256"]
        _, receipt, _, limits = _records(service, parent_id, digest)
        if receipt["original_response"]["sha256"] == failed and receipt["parent_head"] == head:
            result.update(financing_policy_terminal_continuation_available=True,
                          financing_policy_correction_receipt_sha256=digest,
                          annual_input_limitations=limits, adoptable_valuation=False,
                          financing_policy_terminal_task_id=_child_id(parent_id, digest))
    except (OSError, ValueError, TypeError, KeyError):
        pass
    return result


def _limitations(policy, context):
    years, series = policy["years"], policy["series"]
    capex = [Decimal(a) + Decimal(b) for a, b in zip(
        series["maintenance_capex"]["values"], series["growth_capex"]["values"], strict=True)]
    investments = [Decimal(x) for x in series["investment_cash_received"]["values"]]
    limits = []
    for field, values, floor_name in (("investment_cash_received", investments, "annual_investment_receipts_floor"),
                                      ("total_capex", capex, "annual_capex_floor")):
        if len(values) < 2 or len(set(values)) != 1:
            continue
        item = dict(field=field, first_year=years[0], through_year=years[-1], annual_cny=str(values[0]),
                    classification="UNCHANGED_ANNUAL_FORECAST_RECURRENCE_UNVERIFIED")
        floor = context.get(floor_name)
        if floor and floor["year"] == years[0] and Decimal(floor["minimum_cny"]) == values[0]:
            item.update(observed_through=floor["observed_through"],
                        classification="INTERIM_CASH_REPEATED_AS_ANNUAL_FORECAST_RECURRENCE_UNVERIFIED")
        limits.append(item)
    return limits


class ContinuationService(native.ParentCashTaskServiceV3):
    def _inputs(self, parent_id, digest, registered_spec):
        pin, receipt, response, limits = _records(self, parent_id, digest)
        parent, state, head = self._load(parent_id)
        if (head != receipt["parent_head"] or parent["spec_binding"] != registered_spec
                or receipt["registered_spec"] != registered_spec or MARKER in parent
                or not parent.get("implemented_distribution_receipt_binding")
                or parent.get("gross_capex_plan_binding") is not None):
            raise ValueError("PARENT_CORRECTION_SOURCE_MISMATCH")
        failed = receipt["original_response"]["sha256"]
        annual, terminal = correction.replay_for_terminal(self, parent_id, failed, digest)
        if correction._digest(vars(terminal)) != receipt["next_request_sha256"]:
            raise ValueError("PARENT_CORRECTED_TERMINAL_REQUEST_CHANGED")
        spent = Decimal(parent.get("ancestor_spend", "0")) + Decimal(state["settled_cost"]) + Decimal(receipt["settled_cost_cny"])
        child = dict(parent, task_id=_child_id(parent_id, digest), ancestor_spend=str(spent),
                     replay_from_stage="bear.terminal")
        child.pop("seed", None)
        child.pop("forked_at", None)
        child[MARKER] = dict(version=VERSION, parent_task_id=parent_id, correction_receipt=pin,
                             original_request_sha256=receipt["original_request_sha256"],
                             correction_request_sha256=receipt["correction_request_sha256"],
                             original_response=receipt["original_response"], terminal_request_sha256=receipt["next_request_sha256"],
                             implementation_sha256=native._hash(Path(__file__).read_bytes()),
                             annual_input_limitations=limits)
        return child, {"bear.operating": receipt["operating_response"], "bear.policy": response}, annual

    def continue_policy(self, parent_id, receipt_sha256, registered_spec, *, now=None):
        if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
            raise ValueError("PARENT_CORRECTION_RECEIPT_PIN_REQUIRED")
        child, responses, _ = self._inputs(parent_id, receipt_sha256, registered_spec)
        now = native._now(now)
        directory = self._directory(child["task_id"])
        with self._lock(directory):
            input_path = directory / "input.json"
            if input_path.exists():
                if input_path.read_bytes() != native._bytes(child):
                    raise ValueError("PARENT_CORRECTED_CHILD_INPUT_CHANGED")
                if (directory / "current.json").exists() or any((directory / "versions").glob("*.json")):
                    spec, state, head = self._load(child["task_id"])
                    return self._view(spec, state, head, now)
            else:
                if self.test_provider is None and not os.environ.get(child["config"]["api_key_env"]):
                    raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
                write_new_bytes(input_path, native._bytes(child))
            state = dict(status="QUEUED", error_code=None, responses=responses, reservations={}, reserved_cost="0",
                         settled_cost="0", provider_requests=0, new_llm_calls=0,
                         usage=dict(prompt_tokens=0, completion_tokens=0), formal_eligibility=False, action="no_order")
            state, head = self._save(child, state, None, now)
            return self._view(child, state, head, now)

    def _view(self, spec, state, binding, now):
        view = super()._view(spec, state, binding, now)
        if MARKER in spec:
            view.update({MARKER: spec[MARKER]}, reused_from_task_id=spec[MARKER]["parent_task_id"],
                        reused_stages=sorted(ANNUAL), adoptable_valuation=False,
                        annual_input_limitations=spec[MARKER]["annual_input_limitations"])
        return view

    def _wire(self, spec, stage, request, *, root=None):
        wire = super()._wire(spec, stage, request, root=root)
        if MARKER in spec and stage == "terminal" and native.json.loads(request.user)["scenario"] == "bear":
            if correction._digest(vars(wire)) != spec[MARKER]["terminal_request_sha256"]:
                raise ValueError("PARENT_CORRECTED_TERMINAL_REQUEST_CHANGED")
        return wire

    def _stage_outputs(self, spec, state, now, *, verified_context=None):
        if MARKER not in spec:
            return super()._stage_outputs(spec, state, now, verified_context=verified_context)
        link = spec[MARKER]
        expected, annual_pins, annual = self._inputs(link["parent_task_id"], link["correction_receipt"]["sha256"],
                                                      spec["spec_binding"])
        if expected != spec or any(state["responses"].get(k) != v for k, v in annual_pins.items()):
            raise ValueError("PARENT_CORRECTED_CHILD_LINEAGE_CHANGED")
        self._verify_charges(state)
        charges = state["reservations"]
        stages = [charge["scenario"] for charge in charges.values()]
        if ANNUAL.intersection(stages) or len(stages) != len(set(stages)):
            raise ValueError("PARENT_CORRECTED_CHILD_DUPLICATE_STAGE")
        for stage, pin in state["responses"].items():
            if stage in ANNUAL:
                continue
            key = Path(pin["path"]).stem.removeprefix("response-")
            path = self._directory(spec["task_id"]) / f"response-{key}.json"
            if (pin["path"] != path.relative_to(self.root).as_posix() or pin not in state.get("returned_responses", ())
                    or charges.get(key, {}).get("scenario") != stage or charges[key]["status"] != "SETTLED"):
                raise ValueError("PARENT_CORRECTED_CHILD_RESPONSE_NOT_SETTLED")
        # Native replay handles Base and Bull unchanged. Bear's only local response consumes
        # the independently authenticated annual prefix, under its actual terminal request hash.
        others = {k: v for k, v in state["responses"].items() if k not in ANNUAL and k != "bear.terminal"}
        context = verified_context if verified_context is not None else self._context(spec, now)
        outputs = super()._stage_outputs(spec, dict(state, responses=others), now, verified_context=context)
        outputs["bear"] = dict(annual)
        terminal = state["responses"].get("bear.terminal")
        if terminal is not None:
            packet = self._bound(terminal)
            req = correction._stage_request(self, spec, context, "terminal", annual)
            wire = self._wire(spec, "terminal", req, root=self.root)
            if (packet["scenario"] != "bear.terminal" or packet["action"] != "no_order"
                    or packet["source_fingerprint"] != context["input_fingerprint"]
                    or packet["request_sha256"] != correction._digest(vars(wire))):
                raise ValueError("PARENT_CORRECTED_TERMINAL_RESPONSE_CHANGED")
            parsed = self._parse_stage(spec, "terminal", native.LLMResponse(**packet["response"]),
                                       request=req, source_fingerprint=context["input_fingerprint"])
            self._preflight_terminal(spec, req, parsed)
            outputs["bear"]["terminal"] = parsed
        return outputs
