"""Explicit native V3 task dispatch for verified four-column parent statements."""
from copy import deepcopy
from datetime import datetime
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

from .agent_review import parent_cash_task_v3 as native
from .agent_review.task_execution_v1 import _bytes, _hash, _now
from .direct_owner_cash_agent_draft_v2 import POLICY, SCENARIOS, _load_spec
from .direct_owner_cash_staged_v3 import staged_parent_cash_request_v3
from .parent_cash_corrected_continuation_v1 import ContinuationService
from .parent_note_grid_sources_v1 import VERSION
from . import parent_note_grid_task_inputs_v1 as inputs
from . import parent_note_grid_task_kernel_v1 as kernel
from ..product.common import write_new_bytes
from ...infrastructure.agent_runtime.provider import LLMResponse, OpenAICompatibleChatProvider

MARKER = "note_grid_source_version"
TASK_VERSION = native.VERSION
STAGE_ORDER, STAGES = native.STAGE_ORDER, native.STAGES


def implementation():
    from . import parent_note_grid_agent_facts_v1, parent_note_grid_sources_v1, parent_note_grid_case_v1
    from ...infrastructure.filings import parent_note_grid_v1
    from . import fresh_issuer_distribution_v1, company_profile_sources_v2
    from ...infrastructure.filings import official_report_acquisition
    modules = (inputs, kernel, fresh_issuer_distribution_v1, company_profile_sources_v2, official_report_acquisition, parent_note_grid_case_v1, parent_note_grid_agent_facts_v1, parent_note_grid_sources_v1, parent_note_grid_v1)
    return native._implementation() | {m.__name__: _hash(Path(m.__file__).read_bytes()) for m in modules} | {
        __name__: _hash(Path(__file__).read_bytes())}


class ParentCashService(ContinuationService):
    def create(self, *, spec_binding, request_key, now=None, seed_task_id=None,
               replay_from_stage=None, gross_capex_plan_binding=None):
        source = _load_spec(self.root, spec_binding)
        if source.get("source_adapter_version") != VERSION:
            return super().create(spec_binding=spec_binding, request_key=request_key, now=now, seed_task_id=seed_task_id,
                                  replay_from_stage=replay_from_stage, gross_capex_plan_binding=gross_capex_plan_binding)
        if any(x is not None for x in (seed_task_id, replay_from_stage, gross_capex_plan_binding)):
            raise ValueError("NOTE_GRID_CROSS_VERSION_SEED_UNSUPPORTED")
        if not isinstance(request_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key):
            raise ValueError("PARENT_REQUEST_KEY_INVALID")
        now = _now(now)
        task_id = "rt-" + _hash((TASK_VERSION + ":" + request_key).encode())[:32]
        directory = self._directory(task_id)
        mode = "TEST_ONLY_PARENT_CASH_V3" if self.test_provider is not None else "LIVE_PARENT_CASH_V3"
        with self._lock(directory):
            if (directory / "input.json").exists():
                old, state, head = self._load(task_id)
                if old.get(MARKER) != VERSION or old["spec_binding"] != spec_binding or old["mode"] != mode:
                    raise ValueError("PARENT_REQUEST_KEY_CONFLICT")
                return self._view(old, state, head, now)
            cfg = self._configuration()
            if cfg["model_id"] != "deepseek-flash" or cfg["max_completion_tokens_cap"] < 1024:
                raise ValueError("PARENT_MODEL_CONTRACT_INVALID")
            if self.test_provider is None and not os.environ.get(cfg["api_key_env"]):
                raise PermissionError("MODEL_CREDENTIAL_REQUIRED")
            context = inputs.task_context(root=self.root, spec_binding=spec_binding, now=now)
            spec = dict(schema_version=TASK_VERSION, task_id=task_id, mode=mode, spec_binding=spec_binding,
                        source_fingerprint=context["input_fingerprint"], config=cfg, created_at=now.isoformat(),
                        shared_budget_root=str(self.shared_budget_root), implementation_sha256=implementation(),
                        policy_capital_basis=native.policy_capital.opening_debt_basis(source["opening"], context["facts"]),
                        operating_series_wire="INPUTS_ONLY_V2", terminal_distribution_preflight=True,
                        action="no_order", **{MARKER: VERSION})
            from .parent_cash_task_completion_v1 import preflight_parent_cash_task
            from .parent_note_grid_case_v1 import verified_descriptors
            case, paid = preflight_parent_cash_task(self, spec_binding)
            verified_descriptors(self.root, source, self._bound(case))
            spec.update(case_package_binding=case, implemented_distribution_receipt_binding=paid,
                        mandatory_cash_classification="DISJOINT_V1")
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", responses={}, reservations={}, provider_requests=0,
                         usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0", settled_cost="0",
                         action="no_order", formal_eligibility=False, error_code=None, new_llm_calls=0)
            state, head = self._save(spec, state, None, now)
            return self._view(spec, state, head, now)

    def _view(self, spec, state, binding, now):
        result = super()._view(spec, state, binding, now)
        if MARKER in spec:
            result.update(adoptable_valuation=False, source_adapter_version=VERSION)
        return result

    def _implementation_matches(self, spec):
        if MARKER not in spec:
            return super()._implementation_matches(spec)
        return spec[MARKER] == VERSION and spec["implementation_sha256"] == implementation()

    def _context(self, spec, now):
        if MARKER not in spec:
            return super()._context(spec, now)
        if (not self._implementation_matches(spec) or self._configuration() != spec["config"]
                or spec["shared_budget_root"] != str(self.shared_budget_root)):
            raise PermissionError("MODEL_AUTHORIZATION_CHANGED")
        context = inputs.task_context(root=self.root, spec_binding=spec["spec_binding"], now=now)
        if (context["input_fingerprint"] != spec["source_fingerprint"]
                or context["implemented_distribution"]["receipt_binding"] != spec["implemented_distribution_receipt_binding"]):
            raise ValueError("PARENT_SOURCE_CHANGED")
        return context

    def _assemble(self, spec, drafts, now):
        if MARKER not in spec:
            return super()._assemble(spec, drafts, now)
        self._context(spec, now)
        return kernel.assemble_parent_cash_drafts_v2(root=self.root, spec_binding=spec["spec_binding"],
            drafts=drafts, generated_at=now, implemented_distribution=spec.get("implemented_distribution_receipt_binding"))

    def run(self, task_id, *, now=None):
        with self._lock(self._directory(task_id)):
            spec, _, _ = self._load(task_id)
        if MARKER not in spec:
            return super().run(task_id, now=now)
        if (spec["mode"] == "TEST_ONLY_PARENT_CASH_V3") != (self.test_provider is not None):
            raise PermissionError("NOTE_GRID_TRANSPORT_MODE_MISMATCH")
        return self._run_note_grid(task_id, now=now)

    def _run_note_grid(self, task_id, *, now=None):
        now = _now(now)
        directory = self._directory(task_id)
        with self._lock(directory, "execution"):
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] != "QUEUED":
                    return self._view(spec, state, binding, now)
                if any(row["scenario"] not in state["responses"] for row in state["reservations"].values()):
                    raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                self._drafts(spec, state, now)
                state, binding = self._save(spec, state, binding, now, status="RUNNING")
            for stage_id in STAGE_ORDER:
                scenario, stage = stage_id.split(".")
                with self._lock(directory):
                    spec, state, binding = self._load(task_id)
                    if state["status"] == "CANCELLED":
                        return self._view(spec, state, binding, _now())
                    if stage_id in state["responses"]:
                        if stage == "policy":
                            context = self._context(spec, _now())
                            stages = self._stage_outputs(spec, state, _now(),
                                verified_context=context)[scenario]
                            try:
                                kernel.preflight_annual_cash_upper_bound_v3(root=self.root,
                                    spec_binding=spec["spec_binding"], evaluated_at=_now(),
                                    context=context, operating=stages["operating"],
                                    policy=stages["policy"])
                            except (ValueError, OSError, KeyError, TypeError) as error:
                                detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                                code = ("PARENT_V3_ECONOMIC_" + detail
                                    if isinstance(error, ValueError) and re.fullmatch(
                                        r"(?:(?:DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT|PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_(?:BELOW_REALISED_CASH|UNSUPPORTED)|PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH):20[0-9]{2}|"
                                    r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:"
                                    r"(?:debt_repayment|new_borrowing))", detail)
                                    else detail if isinstance(error, ValueError) and re.fullmatch(
                                        r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:(?:new_borrowing|debt_repayment)", detail)
                                    else "PARENT_V3_ANNUAL_CASH_PREFLIGHT_REJECTED")
                                state, binding = self._save(spec, state, binding, _now(),
                                    status="FAILED", error_code=f"{stage_id.upper().replace('.', '_')}_{code}")
                                return self._view(spec, state, binding, _now())
                        continue
                    if any(row["scenario"] == stage_id for row in state["reservations"].values()):
                        raise ValueError("PARENT_AMBIGUOUS_CALL_NO_RESEND")
                    context = self._context(spec, _now())
                    cfg = spec["config"]
                    prior = self._stage_outputs(spec, state, _now(), verified_context=context)[scenario]
                    if set(prior) != set(STAGES[:STAGES.index(stage)]):
                        raise ValueError("PARENT_V3_STAGE_ORDER_INVALID")
                    try:
                        request = staged_parent_cash_request_v3(root=self.root,
                            spec_binding=spec["spec_binding"], scenario=scenario, stage=stage,
                            prior_drafts=prior, generated_at=datetime.fromisoformat(spec["created_at"]),
                            verified_context=context,
                            max_completion_tokens=cfg["max_completion_tokens_cap"])
                    except ValueError as error:
                        if stage != "terminal" or str(error) != "PARENT_V3_FORECAST_DEBT_NEGATIVE":
                            raise
                        state, binding = self._save(spec, state, binding, _now(), status="FAILED",
                            error_code=f"{scenario.upper()}_TERMINAL_PARENT_V3_FORECAST_DEBT_NEGATIVE")
                        return self._view(spec, state, binding, _now())
                    wire_request = self._wire(spec, stage, request, root=self.root)
                    prompt_cap = len(_bytes(wire_request.__dict__)) + 4096
                    reserve = (Decimal(prompt_cap) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(request.max_completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    if (state["provider_requests"] >= len(STAGE_ORDER) or
                            Decimal(spec.get("ancestor_spend", "0")) + Decimal(state["reserved_cost"]) +
                            Decimal(state["settled_cost"]) + reserve > Decimal(str(cfg["max_run_cost"]))):
                        state, binding = self._save(spec, state, binding, _now(),
                            status="FAILED", error_code="PARENT_TASK_BUDGET_EXHAUSTED")
                        return self._view(spec, state, binding, _now())
                    reservation = _hash(os.urandom(32))
                    day = _now().astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
                    self.daily._daily_budget(day, reservation, reserve, cfg)
                    reservations = deepcopy(state["reservations"])
                    reservations[reservation] = dict(scenario=stage_id, status="RESERVED",
                        cost=str(reserve), day=day)
                    state, binding = self._save(spec, state, binding, _now(),
                        reservations=reservations, reserved_cost=str(Decimal(state["reserved_cost"]) + reserve),
                        provider_requests=state["provider_requests"] + 1,
                        new_llm_calls=state["new_llm_calls"] + (self.test_provider is None))
                response_recorded = False
                provider_returned = False
                try:
                    provider = self.test_provider or OpenAICompatibleChatProvider(**{k:cfg[k]
                        for k in ("endpoint", "model_id", "api_key_env", "timeout_seconds",
                                  "max_completion_tokens_cap", "response_format_mode", "thinking_mode") if k in cfg})
                    response = provider.complete(wire_request)
                    provider_returned = True
                    if (not isinstance(response, LLMResponse) or response.tool_calls
                            or type(response.prompt_tokens) is not int or type(response.completion_tokens) is not int
                            or not 0 <= response.prompt_tokens <= prompt_cap
                            or not 0 <= response.completion_tokens <= request.max_completion_tokens
                            or response.model_id != cfg["model_id"]):
                        raise ValueError("PARENT_PROVIDER_RESPONSE_INVALID")
                    actual = (Decimal(response.prompt_tokens) * Decimal(str(cfg["input_cost_per_million"])) +
                        Decimal(response.completion_tokens) * Decimal(str(cfg["output_cost_per_million"]))) / Decimal(1000000)
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        self.daily._daily_budget(day, reservation, actual, cfg, settle=True)
                        reservations = deepcopy(state["reservations"])
                        reservations[reservation].update(status="SETTLED", actual_cost=str(actual))
                        usage = {key:state["usage"][key] + getattr(response, key)
                            for key in ("prompt_tokens", "completion_tokens")}
                        state, binding = self._save(spec, state, binding, _now(), reservations=reservations,
                            usage=usage, reserved_cost=str(Decimal(state["reserved_cost"]) - reserve),
                            settled_cost=str(Decimal(state["settled_cost"]) + actual))
                        packet = dict(scenario=stage_id, request_sha256=_hash(_bytes(wire_request.__dict__)),
                            source_fingerprint=spec["source_fingerprint"], response=response.__dict__, action="no_order")
                        path = directory / ("response-" + reservation + ".json")
                        write_new_bytes(path, _bytes(packet))
                        response_recorded = True
                        response_binding = self._binding(path)
                        state, binding = self._save(spec, state, binding, _now(),
                            returned_responses=state.get("returned_responses", []) + [response_binding])
                    parsed_stage = self._parse_stage(spec, stage, response, request=request,
                        source_fingerprint=spec["source_fingerprint"])
                    if stage == "terminal":
                        self._preflight_terminal(spec, request, parsed_stage)
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] == "CANCELLED":
                            return self._view(spec, state, binding, _now())
                        responses = deepcopy(state["responses"])
                        responses[stage_id] = response_binding
                        state, binding = self._save(spec, state, binding, _now(), responses=responses)
                    if stage == "policy":
                        kernel.preflight_annual_cash_upper_bound_v3(root=self.root,
                            spec_binding=spec["spec_binding"], evaluated_at=_now(),
                            context=context,
                            operating=prior["operating"], policy=parsed_stage)
                except Exception as error:
                    if response_recorded:
                        detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                        code = ("PARENT_V3_ECONOMIC_" + detail
                                if isinstance(error, ValueError) and re.fullmatch(
                                    r"(?:(?:DIRECT_OWNER_UNFUNDED_CASH_REQUIREMENT|PARENT_V3_ANNUAL_CAPEX_BELOW_REALISED_CASH|PARENT_V3_ANNUAL_INVESTMENT_RECEIPTS_(?:BELOW_REALISED_CASH|UNSUPPORTED)|PARENT_V3_ANNUAL_INTEREST_BELOW_REALISED_CASH):20[0-9]{2}|"
                                    r"PARENT_V3_ANNUAL_FINANCING_BELOW_REALISED_CASH:20[0-9]{2}:"
                                    r"(?:debt_repayment|new_borrowing))", detail)
                                else detail if isinstance(error, ValueError)
                                and (detail == "PARENT_DRAFT_TERM_SOURCE_INVALID"
                                     or re.fullmatch(r"PARENT_V3_[A-Z0-9_]{1,90}", detail)
                                     or re.fullmatch(
                                         r"PARENT_FINANCING_(?:ABOVE_DISCLOSED_PROCEEDS|BELOW_CONTRACTUAL_PRINCIPAL):20[0-9]{2}",
                                         detail)
                                     or re.fullmatch(r"PARENT_V3_POLICY_(?:DEBT_INTEREST_UNSUPPORTED|COUPON_COVERAGE_LOW):20[0-9]{2}", detail)
                                     or re.fullmatch(r"PARENT_V3_MANDATORY_CASH_DUPLICATES_FINANCING_INTEREST:20[0-9]{2}", detail)
                                     or (re.fullmatch(r"PARENT_V3_POLICY_CNY_WIRE_INVALID:20[0-9]{2}:[a-z_]+", detail)
                                         and detail.rsplit(":", 1)[-1] in POLICY))
                                else "PARENT_DRAFT_REJECTED_OR_UNPUBLISHED")
                    elif not provider_returned and isinstance(error, HTTPError):
                        status = error.code
                        code = (f"PARENT_PROVIDER_HTTP_{status}_UNSETTLED"
                                if type(status) is int and 100 <= status <= 599
                                else "PARENT_PROVIDER_HTTP_ERROR_UNSETTLED")
                    elif not provider_returned and isinstance(error, URLError):
                        code = ("PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                                if isinstance(error.reason, TimeoutError)
                                else "PARENT_PROVIDER_CONNECTION_AMBIGUOUS")
                    elif provider_returned and isinstance(error, OSError):
                        code = "PARENT_RESPONSE_SETTLEMENT_OR_PERSISTENCE_FAILED"
                    elif isinstance(error, TimeoutError):
                        code = "PARENT_PROVIDER_TIMEOUT_AMBIGUOUS"
                    elif isinstance(error, ValueError) and "completion token cap" in str(error):
                        code = "PARENT_PROVIDER_COMPLETION_CAP_REACHED"
                    elif isinstance(error, ValueError) and "truncated" in str(error):
                        code = "PARENT_PROVIDER_RESPONSE_INCOMPLETE"
                    elif provider_returned and isinstance(error, ValueError) and str(error) == "PARENT_PROVIDER_RESPONSE_INVALID":
                        code = "PARENT_PROVIDER_RESPONSE_INVALID"
                    else:
                        code = "PARENT_PROVIDER_OR_SETTLEMENT_AMBIGUOUS"
                    with self._lock(directory):
                        spec, state, binding = self._load(task_id)
                        if state["status"] != "CANCELLED":
                            state, binding = self._save(spec, state, binding, _now(),
                                status="FAILED", error_code=f"{stage_id.upper().replace('.', '_')}_{code}")
                        return self._view(spec, state, binding, _now())
            with self._lock(directory):
                spec, state, binding = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, binding, _now())
                try:
                    drafts = self._drafts(spec, state, _now())
                    if set(drafts) != set(SCENARIOS):
                        raise ValueError("PARENT_V3_INCOMPLETE_THREE_SCENARIOS")
                    self._assemble(spec, drafts, _now())
                except (ValueError, KeyError, TypeError, OSError) as error:
                    detail = str(error).replace("PARENT_V2_", "PARENT_V3_", 1)
                    code = ("PARENT_V3_ECONOMIC_" + detail
                            if isinstance(error, ValueError)
                            and re.fullmatch(r"(?:DIRECT_OWNER|DIRECT_INPUT|PARENT_V3)_[A-Z0-9_]{1,90}(?::20[0-9]{2})?", detail)
                            else "PARENT_V3_ECONOMIC_CONTRACT_REJECTED")
                    state, binding = self._save(spec, state, binding, _now(),
                        status="FAILED", error_code=code)
                    return self._view(spec, state, binding, _now())
                state, binding = self._save(spec, state, binding, _now(), status="SUCCEEDED")
                return self._view(spec, state, binding, _now())
