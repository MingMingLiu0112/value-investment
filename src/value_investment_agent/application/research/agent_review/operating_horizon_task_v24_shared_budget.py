"""V24 source-bound full-schema transport with shared-budget verification."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from . import operating_horizon_task_v23_full_schema as prior
from . import operating_horizon_annual_v3 as annual
from . import operating_cash_policy_draft_v16_generic as cash
from . import operating_draft_v1 as common
from .operating_horizon_native_transport_v1 import normalize_scenario
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v24-full-schema-shared-budget-2027"
STORE = "oh-v24-full-schema-shared-budget-2027"
SCENARIOS = ("bear", "base", "bull")
STAGES = (*SCENARIOS, "cash")


def implementation():
    return {**prior.implementation(), __name__: _hash(Path(__file__).read_bytes())}


def scenario_request(context, scenario, cap):
    if scenario not in SCENARIOS:
        raise ValueError("V24_SCENARIO_INVALID")
    whole = annual.build_request(context, [2027], cap)
    basis, plans = annual.prior.prior.annual_plan(context, [2027])
    ids = [row["id"] for row in context["evidence"]]
    refs = dict(type="array", minItems=1, maxItems=8, uniqueItems=True,
                items=dict(type="string", enum=ids))
    value = dict(type="object", additionalProperties=False,
                 required=["type", "lower", "upper", "unit"],
                 properties=dict(type=dict(type="string", enum=["range", "unknown"]),
                                 lower=dict(type=["number", "null"]),
                                 upper=dict(type=["number", "null"]),
                                 unit=dict(type="string", enum=["ratio", "CNY", "not_quantified"])))
    driver = dict(type="object", additionalProperties=False,
                  required=["driver_id", "value", "baseline_anchor_ids", "rationale"],
                  properties=dict(driver_id=dict(type="string", enum=[
                      "revenue_activity_volume", "realization_mix_change", "unit_cost_change",
                      "fixed_cogs_share", "opex_change", "surcharge_ratio", "other_pretax_cny"]),
                      value=value, baseline_anchor_ids=refs,
                      rationale=dict(type="string", minLength=1, maxLength=600)))
    capital = dict(type="object", additionalProperties=False,
                   required=["assumption_id", "value", "baseline_anchor_ids", "rationale"],
                   properties=dict(assumption_id=dict(type="string", enum=[
                       "capital_investment", "funding_access", "terminal"]),
                       value=value, baseline_anchor_ids=refs,
                       rationale=dict(type="string", minLength=1, maxLength=600)))
    case = dict(type="object", additionalProperties=False,
                required=["conditional_mechanism", "mechanism_source_ids", "contrary_evidence_ids"],
                properties=dict(conditional_mechanism=dict(type="string", minLength=12, maxLength=600),
                                mechanism_source_ids=refs, contrary_evidence_ids=refs))
    schema = dict(type="object", additionalProperties=False,
                  required=["scenario", "drivers", "capital_assumptions", "unit_cost_mechanism",
                            "unit_cost_case", "counter_evidence", "reopen_condition"],
                  properties=dict(scenario=dict(type="string", const=scenario),
                                  drivers=dict(type="array", minItems=7, maxItems=7, items=driver),
                                  capital_assumptions=dict(type="array", minItems=3, maxItems=3, items=capital),
                                  unit_cost_mechanism=dict(type="string", minLength=1, maxLength=120),
                                  unit_cost_case=case,
                                  counter_evidence=dict(type="array", minItems=1, maxItems=5,
                                                        items=dict(type="string", minLength=1, maxLength=600)),
                                  reopen_condition=dict(type="string", minLength=12, maxLength=600)))
    user = common._canonical(dict(source_context=context,
        deterministic_basis=annual.prior.prior.prior._prompt_basis(basis),
        locked_annual_plan=plans["2027"],
        historical_cost_counterevidence=annual.cost_counterevidence(context),
        scenario=scenario))
    if len(user) > 64000:
        raise ValueError("V24_CONTEXT_OVER_BUDGET")
    return replace(whole, system=whole.system + " V24: Return exactly one native scenario object. "
        "Use drivers as seven objects with driver_id/value/baseline_anchor_ids/rationale; "
        "capital_assumptions as capital_investment/funding_access/terminal objects; "
        "never return years, operating_paths, label, thesis, recommendation or approval.",
        user=user, output_schema=schema, max_completion_tokens=whole.max_completion_tokens,
        # The configured gateway only offers json_object.  Supplying the full
        # local schema (rather than inherited prose for an older envelope) is
        # necessary for the provider to emit this native V24 shape.
        transport_output_contract=None)


def _native_flat(response, scenario, context):
    _, plans = annual.prior.prior.annual_plan(context, [2027])
    plan = plans["2027"]
    normalized = normalize_scenario(response.text, scenario,
                                    period_start=plan["period_start"], period_end=plan["period_end"])
    text = common._canonical(normalized)
    return LLMResponse(text, response.prompt_tokens, response.completion_tokens, response.model_id)


def assemble_annual(responses, context, generated_at):
    if set(responses) != set(SCENARIOS):
        raise ValueError("V24_SCENARIOS_INCOMPLETE")
    flat = {name: _native_flat(responses[name], name, context) for name in SCENARIOS}
    # ``prior`` is V22, which expects provider-native text.  ``flat`` has
    # already been normalized here, so hand it to the unchanged V21 annual
    # assembler exactly once rather than applying the native adapter twice.
    return prior.prior.prior.assemble_annual(flat, context, generated_at)


class OperatingHorizonTaskService(prior.OperatingHorizonTaskService):
    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self.base = require_inside(self.root, self.base.parent / STORE, "v24 full-schema shared-budget tasks")

    def _load(self, task_id, *, recover=False):
        spec, state, pin = prior.prior.prior.prior.live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        valid = [list(STAGES[:n]) for n in range(len(STAGES) + 1)]
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [2027]
                or spec.get("action") != "no_order" or state.get("action") != "no_order"
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - set(STAGES)
                or set(state.get("stage_responses", {})) - set(STAGES)
                or state.get("stage_validated") not in valid):
            raise ValueError("V24_TASK_BINDING_INVALID")
        self._context(spec)
        return spec, state, pin

    def _context(self, spec):
        if (spec["implementation_sha256"] != implementation()
                or spec["source_loader_binding"] != self._loader_binding()
                or spec.get("shared_budget_root") != (str(self.root) if self.test_provider is not None
                    else str(self.shared_budget_root))):
            raise ValueError("V24_IMPLEMENTATION_OR_LOADER_CHANGED")
        context = self.source_loader(root=self.root, symbol=spec["symbol"],
            binding=spec["source_binding"], now=datetime.fromisoformat(spec["created_at"]))
        if (context.get("symbol") != spec["symbol"] or context.get("source_binding") != spec["source_binding"]
                or context.get("snapshot_fingerprint") != spec["context_fingerprint"]
                or _hash(_bytes(context)) != spec["context_sha256"]):
            raise ValueError("V24_SOURCE_CHANGED")
        projected = cash._source(context, spec["source_binding"])
        expected = {name: _hash(_bytes(scenario_request(projected, name,
            spec["config"]["max_completion_tokens_cap"]).__dict__)) for name in SCENARIOS}
        if expected != spec["scenario_request_sha256"]:
            raise ValueError("V24_REQUEST_CHANGED")
        return context

    def _request_for_stage(self, spec, state, context, stage):
        if stage in SCENARIOS:
            return scenario_request(cash._source(context, spec["source_binding"]), stage,
                                    spec["config"]["max_completion_tokens_cap"]), None
        if stage != "cash":
            raise ValueError("V24_STAGE_INVALID")
        aggregate, _ = self._annual_checkpoint(spec, state, context)
        return cash.build_staged_cash_request(context, spec["source_binding"], aggregate,
                                              self._annual_generated_at(spec, state))

    def _annual_generated_at(self, spec, state):
        return datetime.fromisoformat(self._packet(spec, state, "bull")["generated_at"])

    def _annual_checkpoint(self, spec, state, context):
        if not set(SCENARIOS) <= set(state["stage_validated"]):
            raise ValueError("V24_ANNUAL_CHECKPOINT_REQUIRED")
        responses = {}
        for name in SCENARIOS:
            packet = self._packet(spec, state, name)
            request, _ = self._request_for_stage(spec, state, context, name)
            if packet["request_sha256"] != _hash(_bytes(request.__dict__)):
                raise ValueError("V24_REQUEST_CHANGED")
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
            raise ValueError("V24_CASH_BINDING_CHANGED")
        response = LLMResponse(**packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", packet)
        return cash.validate_staged_responses(aggregate, response, context=context,
            source_binding=spec["source_binding"], binding=binding,
            annual_generated_at=self._annual_generated_at(spec, state),
            cash_generated_at=datetime.fromisoformat(packet["generated_at"]))

    def _verify_stage_settlement(self, spec, state, stage, packet):
        """Verify the same shared D1 ledger used for reservation and settlement."""
        intent = state["stage_intents"][stage]
        response = LLMResponse(**packet["response"])
        actual = self._cost(response.prompt_tokens, response.completion_tokens, spec["config"])
        reservation = intent["reservation"]
        charged = state["reservations"].get(reservation, {})
        if (charged.get("status") != "SETTLED" or Decimal(charged.get("actual_cost", "-1")) != actual):
            raise ValueError("V24_SETTLEMENT_UNVERIFIED")
        root = self.root if self.test_provider is not None else self.shared_budget_root
        if root is None:
            raise PermissionError("V24_SHARED_BUDGET_ROOT_REQUIRED")
        budget = prior.prior.prior.prior.live.LiveOperatingTaskService(root)
        directory = require_inside(budget.base, budget.base / "budget" / charged["budget_day"],
                                   "daily research budget")
        with budget._lock(directory):
            files = sorted((directory / "versions").glob("*.json"))
            if not files or len(files) > 512:
                raise ValueError("V24_DAILY_BUDGET_MISSING")
            previous = None
            for number, path in enumerate(files, 1):
                pin = budget._binding(path)
                row = budget._bound(pin)
                if (path.name != f'{number:04d}-{pin["sha256"]}.json'
                        or row.get("previous") != previous or row.get("version") != number):
                    raise ValueError("V24_DAILY_BUDGET_CHANGED")
                previous = pin
            if (directory / "current.json").read_bytes() != _bytes(previous):
                raise ValueError("V24_DAILY_BUDGET_HEAD_CHANGED")
            if row["records"].get(reservation) != dict(status="SETTLED", cost=str(actual)):
                raise ValueError("V24_DAILY_BUDGET_SETTLEMENT_CHANGED")

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
            value.update(status="FAILED", error_code="V24_REPLAY_INVALID",
                         annual_result=None, research_result=None)
        return value

    def create(self, *, symbol, request_key, years, now=None):
        now = _now(now)
        if (years != [2027] or not isinstance(symbol, str) or re.fullmatch(r"[0-9]{6}", symbol) is None
                or not isinstance(request_key, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None):
            raise ValueError("V24_IDENTITY_INVALID")
        cfg = self._configuration()
        if self.test_provider is None:
            import os
            if cfg["model_id"] != "deepseek-flash":
                raise PermissionError("V24_EXACT_MODEL_REQUIRED")
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
                    raise ValueError("V24_REQUEST_CONFLICT")
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
                code = ("V24_" + stage.upper() + "_RESPONSE_REJECTED" if stage in state["stage_responses"] else
                        "V24_" + stage.upper() + "_PROVIDER_AMBIGUOUS" if stage in state["stage_intents"] else
                        "V24_TASK_EXECUTION_FAILED")
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
                        raise ValueError("V24_RUN_BUDGET_EXHAUSTED")
                    request_sha = _hash(_bytes(request.__dict__))
                    reservation = _hash(_bytes([CONTRACT, task_id, stage, request_sha]))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    intents, reservations = deepcopy(state["stage_intents"]), deepcopy(state["reservations"])
                    intents[stage] = dict(request_sha256=request_sha, reservation=reservation, budget_day=day)
                    reservations[reservation] = dict(status="RESERVED", cost=str(reserve), budget_day=day)
                    self._daily_budget(day, reservation, reserve, cfg)
                    state, pin = self._save(spec, state, pin, now, status="RUNNING",
                        stage_intents=intents, cash_binding=cash_binding or state["cash_binding"],
                        reservations=reservations, reserved_cost=str(reserve),
                        provider_requests=state["provider_requests"] + 1, attempts=state["attempts"] + 1)
                response = provider.complete(request)
                generated = _now()
                packet = dict(stage=stage, request_sha256=request_sha,
                    context_sha256=spec["enriched_context_sha256"], implementation_sha256=spec["implementation_sha256"],
                    response=response.__dict__, generated_at=generated.isoformat(), action="no_order")
                with self._lock(directory):
                    spec, state, pin = self._load(task_id)
                    path = directory / ("response-" + stage + ".json")
                    write_new_bytes(path, _bytes(packet))
                    responses = deepcopy(state["stage_responses"]); responses[stage] = self._binding(path)
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
                        _native_flat(response, stage, cash._source(context, spec["source_binding"]))
                        if stage == "bull":
                            self._annual_checkpoint(spec, {**state, "stage_validated": list(SCENARIOS)}, context)
                    else:
                        result = self._result(spec, state, context)
                        if result.get("status") == "WAITING_EVIDENCE":
                            state, pin = self._save(spec, state, pin, generated,
                                stage_validated=list(STAGES), status="WAITING_EVIDENCE",
                                error_code="V24_EVIDENCE_INCOMPLETE")
                            return self._view(spec, state, pin, generated)
                    state, pin = self._save(spec, state, pin, generated,
                                            stage_validated=list(state["stage_validated"]) + [stage])
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                self._result(spec, state, self._context(spec))
                state, pin = self._save(spec, state, pin, _now(), status="SUCCEEDED", error_code=None)
                return self._view(spec, state, pin, _now())


