"""Use a compact cash transport while retaining V25 task and evidence validation."""

from datetime import datetime
from pathlib import Path

from . import operating_horizon_task_v25_canonical as v25
from . import operating_cash_request_compact as compact
from .operating_cash_policy_draft_v16_generic import (
    _payload, _source, common, full, validate_response,
)
from .task_execution_v1 import _bytes, _hash


class CompactCashTaskService(v25.OperatingHorizonTaskService):
    """Select this transport only for newly created cash-constraint tasks."""

    def _loader_binding(self):
        binding = super()._loader_binding()
        # Python source semantics are unchanged by Git checkout newline conversion.
        sources = {compact.__name__: compact.__file__, __name__: __file__}
        return {**binding, "cash_transport": {
            name: _hash(Path(path).read_text(encoding="utf-8").encode("utf-8"))
            for name, path in sources.items()
        }}

    def _request_for_stage(self, spec, state, context, stage):
        if stage != "cash":
            return super()._request_for_stage(spec, state, context, stage)
        annual, _ = self._annual_checkpoint(spec, state, context)
        return compact.build_compact_cash_request(
            context, spec["source_binding"], annual, self._annual_generated_at(spec, state))

    def _result(self, spec, state, context):
        if not set(v25.STAGES) <= set(state["stage_responses"]):
            return None
        annual, _ = self._annual_checkpoint(spec, state, context)
        packet = self._packet(spec, state, "cash")
        request, binding = self._request_for_stage(spec, state, context, "cash")
        if binding != state["cash_binding"] or packet["request_sha256"] != _hash(_bytes(request.__dict__)):
            raise ValueError("V25_CASH_BINDING_CHANGED")
        response = v25.LLMResponse(**packet["response"])
        self._usage(response, request, spec["config"]["model_id"])
        self._verify_stage_settlement(spec, state, "cash", packet)
        generated = datetime.fromisoformat(packet["generated_at"])
        if generated.utcoffset() is None or generated < self._annual_generated_at(spec, state):
            raise ValueError("V16_GENERIC_CASH_TIME_INVALID")
        if response.model_id != annual.model_id:
            raise ValueError("V16_GENERIC_RESPONSE_MODEL_MISMATCH")
        source_binding = spec["source_binding"]
        cash = validate_response(response, context, source_binding, generated)
        pending = dict(status="WAITING_EVIDENCE", reason="CASH_POLICY_INCOMPLETE",
                       cash_policy_status=cash["cash_policy_appendix_status"],
                       stage_binding=binding, annual_result_sha256=binding["annual_result_sha256"],
                       cash_result=cash, action="no_order", formal_eligibility=False)
        if cash["cash_policy_appendix_status"] != "COMPLETE_UNAPPROVED":
            return pending
        combined = _payload(annual.text)
        row = combined["years"]["2027"]
        for path in row["operating_paths"].values():
            path.pop("unit_cost_case")
        row["shareholder_cash_paths"] = _payload(response.text)["years"]["2027"]["shareholder_cash_paths"]
        try:
            result = full.validate_response(common._canonical(combined),
                _source(context, source_binding, generated_at=generated), [2027], generated)
        except ValueError as error:
            return {**pending, "reason": "FULL_VALIDATOR_REJECTED", "full_validator_reason": str(error)}
        return dict(result, stage_binding=binding, cash_policy_result=cash,
                    split_contract=binding, split_response_sha256={
                        "annual": binding["annual_response_sha256"],
                        "cash": _hash(response.text.encode("utf-8")),
                    }, cash_request_sha256=binding["cash_request_sha256"],
                    action="no_order", formal_eligibility=False)
