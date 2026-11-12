"""Durable V17 cash-only continuation of one verified failed V16 annual packet."""

from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
import re

from . import operating_horizon_task_v16_live as v16
from . import operating_horizon_v17_source as source
from . import operating_horizon_request_v13 as request_v13
from . import operating_horizon_split_v13 as split
from . import operating_cash_policy_draft_v15 as cash_v15
from . import operating_task_v2 as live
from .task_execution_v1 import VERSION, _bytes, _hash, _now
from ...product.common import require_inside, write_new_bytes
from ....infrastructure.agent_runtime.provider import LLMResponse

CONTRACT = "operating-horizon-task-v17-2027-cash-repair"
STORE = "oh-v17-2027-cash-repair"


def implementation():
    return {**v16.implementation(), source.__name__: _hash(Path(source.__file__).read_bytes()),
            source.repair.__name__: _hash(Path(source.repair.__file__).read_bytes()),
            __name__: _hash(Path(__file__).read_bytes())}


class OperatingHorizonTaskService(v16.OperatingHorizonTaskService):
    def __init__(self, root, *, source_service, test_provider=None):
        if not isinstance(source_service, v16.OperatingHorizonTaskService):
            raise ValueError("V17_BOUND_V16_SERVICE_REQUIRED")
        super().__init__(root, test_provider=test_provider,
            source_loader=source_service.source_loader,
            source_loader_version=source_service.source_loader_version)
        self.base = require_inside(self.root, self.base.parent / STORE, "v17 cash tasks")
        self.source_service = source_service
        if (self.source_service.root.resolve() != self.root.resolve()
                or self.source_service.source_loader_version != self.source_loader_version
                or self.source_service.source_loader is not self.source_loader):
            raise ValueError("V17_SOURCE_SERVICE_CHANGED")

    def _replay(self, spec):
        context, packet, normalized, lineage = source.replay(self.source_service,
            spec["imported_annual"]["source_task_id"])
        if (spec["imported_annual"] != lineage or spec["source_binding"] != lineage["source_binding"]
                or spec["context_sha256"] != lineage["source_context_sha256"]):
            raise ValueError("V17_SOURCE_LINEAGE_CHANGED")
        request, binding = self._cash_request(context, packet, normalized, lineage)
        if spec["cash_request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V17_CASH_REQUEST_CHANGED")
        return context, packet, normalized, lineage, request, binding

    @staticmethod
    def _cash_request(context, packet, normalized, lineage):
        derived_text = OperatingHorizonTaskService._derived_text(packet, normalized)
        annual = replace(LLMResponse(**packet["response"]), text=derived_text)
        request, binding = request_v13.build_cash_request(context, [2027],
            source_binding=lineage["source_binding"], annual_response=annual,
            annual_generated_at=datetime.fromisoformat(packet["generated_at"]))
        return v16._v15_cash_request(request, context, lineage["source_binding"]), binding

    def create_imported(self, *, source_task_id, request_key, now=None):
        now = _now(now)
        if not isinstance(request_key, str) or re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_key) is None:
            raise ValueError("V17_IDENTITY_INVALID")
        context, packet, normalized, lineage = source.replay(self.source_service, source_task_id)
        request, _ = self._cash_request(context, packet, normalized, lineage)
        cfg = self._configuration()
        task_id = "rt-" + _hash(_bytes([CONTRACT, source_task_id,
            lineage["source_packet_binding"], normalized["derived_sha256"]]))[:32]
        directory = self._directory(task_id)
        with self._lock(directory):
            if (directory / "input.json").exists():
                spec, state, pin = self._load(task_id)
                if spec["request_key_sha256"] != _hash(request_key.encode("utf-8")):
                    raise ValueError("V17_REQUEST_CONFLICT")
                return self._view(spec, state, pin, now)
            spec = dict(schema_version=VERSION, task_id=task_id, workflow="operating_research",
                task_contract=CONTRACT, mode="TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING",
                symbol=context["symbol"], year=2027, years=[2027],
                request_key_sha256=_hash(request_key.encode("utf-8")), created_at=now.isoformat(),
                source_binding=lineage["source_binding"], context_sha256=lineage["source_context_sha256"],
                enriched_context_sha256=_hash(_bytes(v16.official.project_research_context(context))),
                cash_request_sha256=_hash(_bytes(request.__dict__)), config=cfg,
                implementation_sha256=implementation(), imported_annual=lineage, action="no_order")
            self._replay(spec)
            write_new_bytes(directory / "input.json", _bytes(spec))
            state = dict(status="QUEUED", attempts=0, provider_requests=0, new_llm_calls=0,
                usage=dict(prompt_tokens=0, completion_tokens=0), reserved_cost="0", settled_cost="0",
                reservations={}, stage_intents={}, stage_responses={}, stage_validated=["annual"],
                cash_binding=None, created_at=now.isoformat(), action="no_order",
                formal_eligibility=False, error_code=None)
            state, pin = self._save(spec, state, None, now)
            return self._view(spec, state, pin, now)

    def _load(self, task_id, *, recover=False):
        spec, state, pin = live.LiveOperatingTaskService._load(self, task_id, recover=recover)
        if (spec.get("task_contract") != CONTRACT or spec.get("years") != [2027]
                or spec.get("implementation_sha256") != implementation()
                or spec.get("mode") != ("TEST_ONLY_LIVE_CONTRACT" if self.test_provider else "LIVE_OPERATING")
                or set(state.get("stage_intents", {})) - {"cash"}
                or set(state.get("stage_responses", {})) - {"cash"}
                or state.get("stage_validated") not in (["annual"], ["annual", "cash"])):
            raise ValueError("V17_TASK_BINDING_INVALID")
        self._replay(spec)
        return spec, state, pin

    def _context(self, spec):
        return self._replay(spec)[0]

    def _imported(self, spec):
        context, packet, normalized, lineage, request, _ = self._replay(spec)
        derived_packet = deepcopy(packet)
        derived_packet["response"]["text"] = self._derived_text(packet, normalized)
        return request, lineage, context, derived_packet

    def _request_for_stage(self, spec, state, context, stage):
        if stage != "cash":
            raise ValueError("V17_ANNUAL_PROVIDER_FORBIDDEN")
        *_, request, binding = self._replay(spec)
        return request, binding

    def _verify_annual_checkpoint(self, spec, state, context):
        if "annual" not in state["stage_validated"]:
            raise ValueError("V17_ANNUAL_CHECKPOINT_REQUIRED")
        return self._replay(spec)[3]

    def _result(self, spec, state, context):
        if "cash" not in state["stage_responses"]:
            return None
        _, annual_packet, normalized, lineage, request, binding = self._replay(spec)
        cash_packet = self._packet(spec, state, "cash")
        if state["cash_binding"] != binding or cash_packet["request_sha256"] != spec["cash_request_sha256"]:
            raise ValueError("V17_CASH_BINDING_CHANGED")
        response = LLMResponse(**cash_packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", cash_packet)
        cash_result = cash_v15.validate_response(response,
            split._project(context, lineage["source_binding"]), [2027],
            datetime.fromisoformat(cash_packet["generated_at"]))
        annual_text = self._derived_text(annual_packet, normalized)
        result = split.validate_responses(replace(LLMResponse(**annual_packet["response"]), text=annual_text),
            response, context=context, years=[2027], source_binding=lineage["source_binding"],
            binding=binding, annual_generated_at=datetime.fromisoformat(annual_packet["generated_at"]),
            cash_generated_at=datetime.fromisoformat(cash_packet["generated_at"]))
        result["cash_policy_v15"] = cash_result
        result["v17_lineage"] = lineage
        return result

    @staticmethod
    def _derived_text(packet, normalized):
        payload = deepcopy(source.repair._payload(packet["response"]["text"]))
        for move in normalized["relocations"]:
            _, _, year, _, field = move["from"].split("/")
            payload["years"][year][field] = payload["years"][year]["operating_paths"].pop(field)
        text = source.repair.common._canonical(payload)
        if _hash(text.encode("utf-8")) != normalized["derived_sha256"]:
            raise ValueError("V17_DERIVED_HASH_CHANGED")
        return text

    def _view(self, spec, state, binding, now):
        value = deepcopy(state)
        value.update(record_binding=binding, task_id=spec["task_id"], symbol=spec["symbol"],
            workflow=CONTRACT, execution_mode=spec["mode"], action="no_order", formal_eligibility=False,
            condition_price=None, research_result=None, annual_status="IMPORTED_REPAIRED_V16",
            cash_status=self._stage_status(state, "cash"), imported_annual=spec["imported_annual"],
            source_binding=spec["source_binding"], research_as_of=spec["created_at"])
        try:
            self._replay(spec)
            if state["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}:
                try:
                    value["research_result"] = self._result(spec, state, self._context(spec))
                except split.FullValidatorBlocked as blocked:
                    if (state["status"] != "WAITING_EVIDENCE"
                            or state.get("cash_policy_status") != blocked.cash_policy_status
                            or state.get("full_validator_reason") != blocked.full_validator_reason):
                        raise
                    value["cash_policy_status"] = blocked.cash_policy_status
                    value["full_validator_reason"] = blocked.full_validator_reason
        except (ValueError, OSError, KeyError, TypeError):
            value.update(status="FAILED", error_code="V17_REPLAY_INVALID", research_result=None)
        return value

    def _drive(self, task_id, now, *, resume):
        try:
            return self._drive_once(task_id, now, resume=resume)
        except Exception:
            directory = self._directory(task_id)
            with self._lock(directory):
                spec, state, pin = self._load(task_id)
                if state["status"] == "CANCELLED":
                    return self._view(spec, state, pin, _now())
                intent = "cash" in state["stage_intents"]
                returned = "cash" in state["stage_responses"]
                code = ("V17_CASH_RESPONSE_REJECTED" if returned else
                        "V17_CASH_PROVIDER_AMBIGUOUS" if intent else "V17_TASK_EXECUTION_FAILED")
                state, pin = self._save(spec, state, pin, _now(), status="FAILED", error_code=code)
                return self._view(spec, state, pin, _now())
