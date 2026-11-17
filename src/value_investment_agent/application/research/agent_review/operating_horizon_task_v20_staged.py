"""Versioned three-call annual transport over the unchanged annual-v3 validator.

Each call supplies one scenario. A malformed or incomplete response ends the
task; no text repair, provider retry, or partial economic admission occurs.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v19_generic as prior
from . import operating_horizon_annual_v3 as annual
from . import operating_cash_policy_draft_v16_generic as cash
from . import operating_draft_v1 as common
from .operating_driver_draft_v2 import _payload, _exact
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v20-three-scenario-2027"
STORE = "oh-v20-2027"
SCENARIOS = ("bear", "base", "bull")
STAGES = (*SCENARIOS, "cash")


def implementation():
    return {**prior.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def scenario_request(context, scenario, cap):
    if scenario not in SCENARIOS:
        raise ValueError("V20_SCENARIO_INVALID")
    whole = annual.build_request(context, [2027], cap)
    schema = deepcopy(whole.output_schema)
    paths = schema["properties"]["years"]["properties"]["2027"]["properties"]["operating_paths"]
    paths["properties"] = {scenario: paths["properties"][scenario]}
    paths["required"] = [scenario]
    # The schema and the short wire instruction must describe the same object.
    return replace(whole, output_schema=schema,
        transport_output_contract=(
            "Return one valid JSON object, with no prefix or suffix. Exact top key years; "
            "years has only 2027; year has estimate_kind,operating_paths,"
            "counter_evidence,reopen_condition. operating_paths has exactly one key: "
            f"{scenario}. Include every driver, capital assumption, unit_cost_mechanism "
            "and unit_cost_case required by the attached schema. No other scenario."),
        system=whole.system + f" V20: Produce ONLY the {scenario} scenario for 2027; "
            "do not include another scenario or a second JSON object. This is unapproved research.")


def assemble_annual(responses, context, generated_at):
    if set(responses) != set(SCENARIOS):
        raise ValueError("V20_SCENARIOS_INCOMPLETE")
    rows = {}
    for scenario in SCENARIOS:
        rows[scenario] = validate_scenario_shape(responses[scenario].text, scenario)
    # The estimate kind is a locked year property; each scenario may supply
    # different counterevidence and re-open conditions. Retain all three with
    # explicit labels instead of silently selecting one model response.
    first = rows["bear"]
    for row in rows.values():
        if row["estimate_kind"] != first["estimate_kind"]:
            raise ValueError("V20_ESTIMATE_KIND_CONFLICT")
        if any(not isinstance(row[key], str) or not row[key].strip()
               for key in ("counter_evidence", "reopen_condition")):
            raise ValueError("V20_SCENARIO_REASONS_MISSING")
    combined = dict(years={"2027": dict(
        estimate_kind=first["estimate_kind"],
        operating_paths={name: rows[name]["operating_paths"][name] for name in SCENARIOS},
        counter_evidence="; ".join(f"{name}: {rows[name]['counter_evidence']}" for name in SCENARIOS),
        reopen_condition="; ".join(f"{name}: {rows[name]['reopen_condition']}" for name in SCENARIOS))})
    text = common._canonical(combined)
    model = responses["bear"].model_id
    if any(response.model_id != model for response in responses.values()):
        raise ValueError("V20_MODEL_CHANGED_BETWEEN_SCENARIOS")
    aggregate = LLMResponse(text, sum(r.prompt_tokens for r in responses.values()),
                            sum(r.completion_tokens for r in responses.values()), model)
    # The original validator still owns the entire economic and evidence contract.
    result = annual.validate_response(aggregate, context, [2027], generated_at)
    return aggregate, result


def validate_scenario_shape(text, scenario):
    payload = _payload(text)
    _exact(payload, ("years",))
    _exact(payload["years"], ("2027",))
    row = payload["years"]["2027"]
    _exact(row, ("estimate_kind", "operating_paths", "counter_evidence", "reopen_condition"))
    _exact(row["operating_paths"], (scenario,))
    path = row["operating_paths"][scenario]
    _exact(path, ("baseline_period", "period_start", "period_end", "drivers",
                  "capital_assumptions", "unit_cost_mechanism", "unit_cost_case"))
    if not isinstance(path["drivers"], dict) or not isinstance(path["capital_assumptions"], list):
        raise ValueError("V20_SCENARIO_STRUCTURE_INVALID")
    return row


class OperatingHorizonTaskService(prior.OperatingHorizonTaskService):
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.base = require_inside(self.root, self.base.parent / STORE, "v20 staged tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = prior.live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        validated = state.get("stage_validated")
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [2027]
                or spec.get("action") != "no_order" or state.get("action") != "no_order"
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or validated not in [list(STAGES[:n]) for n in range(len(STAGES) + 1)]):
            raise ValueError("V20_TASK_BINDING_INVALID")
        self._context(spec)
        return spec, state, pin

    def _context(self, spec):
        if (spec["implementation_sha256"] != implementation()
                or spec["source_loader_binding"] != self._loader_binding()
                or spec.get("shared_budget_root") != (str(self.root) if self.test_provider is not None
                    else str(self.shared_budget_root))):
            raise ValueError("V20_IMPLEMENTATION_OR_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context.get("symbol") != spec["symbol"]
                or context.get("source_binding") != spec["source_binding"]
                or context.get("snapshot_fingerprint") != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V20_SOURCE_CHANGED")
        projected = cash._source(context, spec["source_binding"])
        expected = {name: _hash(_bytes(scenario_request(projected, name,
            spec["config"]["max_completion_tokens_cap"]).__dict__)) for name in SCENARIOS}
        if expected != spec["scenario_request_sha256"]:
            raise ValueError("V20_REQUEST_CHANGED")
        return context

    def _request_for_stage(self, spec, state, context, stage):
        if stage in SCENARIOS:
            return scenario_request(cash._source(context, spec["source_binding"]), stage,
                spec["config"]["max_completion_tokens_cap"]), None
        if stage != "cash":
            raise ValueError("V20_STAGE_INVALID")
        aggregate, _ = self._annual_checkpoint(spec, state, context)
        return cash.build_staged_cash_request(context, spec["source_binding"], aggregate,
            self._annual_generated_at(spec, state))

    def _annual_generated_at(self, spec, state):
        return datetime.fromisoformat(self._packet(spec, state, "bull")["generated_at"])

    def _annual_checkpoint(self, spec, state, context):
        if not set(SCENARIOS) <= set(state["stage_validated"]):
            raise ValueError("V20_ANNUAL_CHECKPOINT_REQUIRED")
        responses = {}
        for name in SCENARIOS:
            packet = self._packet(spec, state, name)
            request, _ = self._request_for_stage(spec, state, context, name)
            if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
                raise ValueError("V20_REQUEST_CHANGED")
            response = LLMResponse(**packet["response"])
            self._usage(response, request, spec["config"]["model_id"])
            self._verify_stage_settlement(spec, state, name, packet)
            responses[name] = response
        return assemble_annual(responses, cash._source(context, spec["source_binding"]),
            self._annual_generated_at(spec, state))

    def _result(self, spec, state, context):
        if not set(STAGES) <= set(state["stage_responses"]):
            return None
        aggregate, _ = self._annual_checkpoint(spec, state, context)
        packet = self._packet(spec, state, "cash")
        request, binding = self._request_for_stage(spec, state, context, "cash")
        if binding != state["cash_binding"] or packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V20_CASH_BINDING_CHANGED")
        response = LLMResponse(**packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", packet)
        return cash.validate_staged_responses(aggregate, response, context=context,
            source_binding=spec["source_binding"], binding=binding,
            annual_generated_at=self._annual_generated_at(spec, state),
            cash_generated_at=datetime.fromisoformat(packet["generated_at"]))

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], source_binding=spec["source_binding"],
            research_as_of=spec["created_at"], action="no_order", formal_eligibility=False,
            condition_price=None, annual_result=None, research_result=None,
            annual_status={name: self._stage_status(state, name) for name in SCENARIOS},
            cash_status=self._stage_status(state, "cash"))
        try:
            context = self._context(spec)
            if set(SCENARIOS) <= set(state["stage_validated"]):
                _, value["annual_result"] = self._annual_checkpoint(spec, state, context)
            if state["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}:
                value["research_result"] = self._result(spec, state, context)
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V20_REPLAY_INVALID",
                         annual_result=None, research_result=None)
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (years != [2027] or not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V20_IDENTITY_INVALID")
        cfg = self._configuration()
        if self.test_provider is None:
            if cfg["model_id"] != "deepseek-flash":
                raise PermissionError("V20_EXACT_MODEL_REQUIRED")
            import os
            if not os.environ.get(cfg["api_key_env"]):
                raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
        context = self.source_loader(root=self.root, symbol=symbol, now=now)
        projected = cash._source(context, context["source_binding"])
        requests = {name: _hash(_bytes(scenario_request(projected, name,
            cfg["max_completion_tokens_cap"]).__dict__)) for name in SCENARIOS}
        mode = "TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING"
        task_id = "rt-" + _hash(_bytes([CONTRACT, mode, symbol, years, context["source_binding"]]))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if spec["config"] != cfg or spec["request_key_sha256"] != _hash(request_key.encode()):
                    raise ValueError("V20_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode=mode, symbol=symbol, year=2027, years=years,
                request_key_sha256=_hash(request_key.encode()), created_at=now.isoformat(),
                source_binding=context["source_binding"], context_sha256=_hash(_bytes(context)),
                context_fingerprint=context["snapshot_fingerprint"],
                shared_budget_root=str(self.root if self.test_provider else self.shared_budget_root),
                enriched_context_sha256=_hash(_bytes(context)), source_loader_binding=self._loader_binding(),
                config=cfg, scenario_request_sha256=requests,
                implementation_sha256=implementation(), action="no_order")
            self._context(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0", settled_cost="0",
                reservations={}, stage_intents={}, stage_responses={}, stage_validated=[],
                cash_binding=None, created_at=now.isoformat(), action="no_order",
                formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _drive(self, task_id, now, *, resume):
        try:
            return self._drive_once(task_id, now, resume=resume)
        except Exception:
            directory = self._directory(task_id)
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, pin, _now())
                stage = STAGES[len(state["stage_validated"])] if len(state["stage_validated"]) < len(STAGES) else "cash"
                code = ("V20_" + stage.upper() + "_RESPONSE_REJECTED" if stage in state["stage_responses"] else
                        "V20_" + stage.upper() + "_PROVIDER_AMBIGUOUS" if stage in state["stage_intents"] else
                        "V20_TASK_EXECUTION_FAILED")
                state, pin = self._save(spec, state, pin, _now(), status="FAILED", error_code=code)
                return self._view(spec, state, pin, _now())

    def _drive_once(self, task_id, now, *, resume):
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            for stage in STAGES:
                with self._lock(directory):
                    spec, state, pin = self._load(task_id, recover=resume)
                    if state["status"] in {"CANCELLED", "SUCCEEDED", "FAILED", "WAITING_EVIDENCE"}:
                        return self._view(spec, state, pin, now)
                    context = self._context(spec)
                    if stage in state["stage_validated"]:
                        continue
                    if stage in state["stage_intents"] or state["status"] not in {"QUEUED", "RUNNING"}:
                        return self._view(spec, state, pin, now)
                    request, cash_binding = self._request_for_stage(spec, state, context, stage)
                    provider, cfg = self._provider(spec), spec["config"]
                    reserve = self._cost(len(_bytes(request.__dict__)) + 4096,
                                         request.max_completion_tokens, cfg)
                    if Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"])):
                        raise ValueError("V20_RUN_BUDGET_EXHAUSTED")
                    request_sha = _hash(_bytes(request.__dict__))
                    reservation = _hash(_bytes([CONTRACT, task_id, stage, request_sha]))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    intents = deepcopy(state["stage_intents"])
                    intents[stage] = dict(request_sha256=request_sha, reservation=reservation, budget_day=day)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation] = dict(status="RESERVED", cost=str(reserve), budget_day=day)
                    self._daily_budget(day, reservation, reserve, cfg)
                    state, pin = self._save(spec, state, pin, now, status="RUNNING",
                        stage_intents=intents, cash_binding=cash_binding or state["cash_binding"],
                        reservations=reservations, reserved_cost=str(reserve),
                        provider_requests=state["provider_requests"] + 1, attempts=state["attempts"] + 1)
                response = provider.complete(request)
                generated = _now()
                packet = dict(stage=stage, request_sha256=request_sha,
                    context_sha256=spec["enriched_context_sha256"],
                    implementation_sha256=spec["implementation_sha256"],
                    response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    path = directory / ("response-" + stage + ".json")
                    write_new_bytes(path, _bytes(packet))
                    responses = deepcopy(state["stage_responses"])
                    responses[stage] = self._binding(path)
                    state, pin = self._save(spec, state, pin, generated, stage_responses=responses)
                    self._usage(response, request, cfg["model_id"])
                    actual = self._cost(response.prompt_tokens, response.completion_tokens, cfg)
                    self._daily_budget(day, reservation, actual, cfg, settle=True)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                    state, pin = self._save(spec, state, pin, generated, reservations=reservations,
                        reserved_cost="0", settled_cost=str(Decimal(state["settled_cost"]) + actual),
                        usage=dict(prompt_tokens=state["usage"]["prompt_tokens"] + response.prompt_tokens,
                                   completion_tokens=state["usage"]["completion_tokens"] + response.completion_tokens))
                    self._verify_stage_settlement(spec, state, stage, packet)
                    context = self._context(spec)
                    if stage in SCENARIOS:
                        validate_scenario_shape(response.text, stage)
                        if stage == "bull":
                            self._annual_checkpoint(spec, {**state, "stage_validated": list(SCENARIOS)}, context)
                    else:
                        result = self._result(spec, state, context)
                        if result.get("status") == "WAITING_EVIDENCE":
                            state, pin = self._save(spec, state, pin, generated,
                                stage_validated=list(STAGES), status="WAITING_EVIDENCE",
                                error_code="V20_EVIDENCE_INCOMPLETE")
                            return self._view(spec, state, pin, generated)
                    state, pin = self._save(spec, state, pin, generated,
                        stage_validated=list(state["stage_validated"]) + [stage])
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                self._result(spec, state, self._context(spec))
                state, pin = self._save(spec, state, pin, _now(), status="SUCCEEDED", error_code=None)
                return self._view(spec, state, pin, _now())
