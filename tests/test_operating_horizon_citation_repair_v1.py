"""TEST_ONLY: no provider, network, task mutation or budget charge."""
from copy import deepcopy
from datetime import timedelta
import hashlib
import json

import pytest

from test_operating_horizon_draft_v2 import context, NOW, valid
from value_investment_agent.application.research.agent_review import operating_horizon_citation_repair_v1 as repair
from value_investment_agent.application.research.agent_review import operating_horizon_split_v7 as split
from value_investment_agent.application.research.agent_review.task_execution_v1 import _bytes, _hash
from value_investment_agent.infrastructure.agent_runtime.provider import LLMResponse


class SealedTask:
    def __init__(self, ctx, *, damage="citation"):
        self.ctx = deepcopy(ctx)
        self.original = valid()
        row = self.original["years"]["2026"]["operating_paths"]["bull"]["drivers"]["unit_cost_change"]
        row["evidence_ids"][0] = "operating-statement:forged"
        if damage == "number":
            row["upper"] = "999999"
        self.original_text = json.dumps(self.original, ensure_ascii=False)
        self.request = split.build_annual_request(self.ctx, [2026], source_binding={"test": "pin"},
            max_completion_tokens=1024)
        self.source_hash = _hash(_bytes(self.ctx))
        self.spec = {"task_contract": "operating-horizon-task-v7-split", "action": "no_order",
            "years": [2026], "config": {"model_id": "TEST_ONLY", "max_completion_tokens_cap": 1024}}
        self.state = {"status": "FAILED", "stage_validated": [],
            "stage_responses": {"annual": "sealed"}, "stage_intents": {"annual": "sealed"}}
        self.packet = {"request_sha256": _hash(_bytes(self.request.__dict__)),
            "generated_at": NOW.isoformat(),
            "response": dict(text=self.original_text, prompt_tokens=100,
                completion_tokens=40, model_id="TEST_ONLY", tool_calls=0)}
        self.reads = 0

    def _load(self, task_id):
        assert task_id == "rt-sealed-test"
        self.reads += 1
        return self.spec, self.state, {"sha256": "sealed"}

    def _context(self, spec):
        if _hash(_bytes(self.ctx)) != self.source_hash:
            raise ValueError("SOURCE_HASH_CHANGED")
        return deepcopy(self.ctx)

    def _packet(self, spec, state, stage):
        assert stage == "annual"
        return deepcopy(self.packet)

    def _source_binding(self, spec):
        return {"test": "pin"}

    def _usage(self, response, request, model):
        assert response.model_id == model

    def _verify_stage_settlement(self, spec, state, stage, packet):
        assert stage == "annual"


def proposal(task, replacement="test:revenue"):
    request = repair.build_request(task, "rt-sealed-test")
    problem = json.loads(request.user)["problems"][0]
    return json.dumps({"version": repair.VERSION,
        "original_response_sha256": hashlib.sha256(task.original_text.encode()).hexdigest(),
        "replacements": [{"path": problem["path"], "invalid_id": problem["invalid_id"],
            "replacement_id": replacement, "support_quote": "TEST_ONLY reported row"}]})


def test_exact_citation_only_repair_revalidates_and_preserves_original(context):
    task = SealedTask(context)
    before = deepcopy((task.spec, task.state, task.packet, task.original_text))
    request = repair.build_request(task, "rt-sealed-test")
    body = json.loads(request.user)
    assert request.max_completion_tokens == 512
    assert body["problems"][0]["original_rationale"]
    assert "operating-statement:forged" not in body["admissible_evidence"]
    result = repair.validate_repair(task, "rt-sealed-test", proposal(task),
        repair_generated_at=NOW + timedelta(minutes=1))
    fixed = json.loads(result["corrected_annual_response"])
    original = deepcopy(task.original)
    original["years"]["2026"]["operating_paths"]["bull"]["drivers"]["unit_cost_change"]["evidence_ids"][0] = "test:revenue"
    assert fixed == original
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["research_admission"] is False and result["requires_semantic_evidence_review"]
    assert (task.spec, task.state, task.packet, task.original_text) == before


def test_fake_id_and_changed_number_or_text_are_rejected(context):
    task = SealedTask(context)
    with pytest.raises(ValueError, match="UNAUTHORIZED_CHANGE"):
        repair.validate_repair(task, "rt-sealed-test", proposal(task, "fake:another"),
            repair_generated_at=NOW + timedelta(minutes=1))
    for changed in ("upper", "rationale"):
        draft = json.loads(proposal(task))
        draft["replacements"][0][changed] = "changed"
        with pytest.raises(ValueError, match="Exact operating driver fields"):
            repair.validate_repair(task, "rt-sealed-test", json.dumps(draft),
                repair_generated_at=NOW + timedelta(minutes=1))
    draft = json.loads(proposal(task))
    draft["replacements"][0]["support_quote"] = "unsupported source wording"
    with pytest.raises(ValueError, match="SOURCE_QUOTE_NOT_VERIFIED"):
        repair.validate_repair(task, "rt-sealed-test", json.dumps(draft),
            repair_generated_at=NOW + timedelta(minutes=1))


def test_source_change_and_future_source_rejected(context):
    task = SealedTask(context)
    text = proposal(task)
    task.ctx["evidence"][0]["text"] = "tampered"
    with pytest.raises(ValueError, match="SOURCE_HASH_CHANGED"):
        repair.validate_repair(task, "rt-sealed-test", text,
            repair_generated_at=NOW + timedelta(minutes=1))
    task = SealedTask(context)
    task.ctx["evidence"][0]["available_at"] = (NOW + timedelta(hours=1)).isoformat()
    task.source_hash = _hash(_bytes(task.ctx))
    task.request = split.build_annual_request(task.ctx, [2026], source_binding={"test": "pin"},
        max_completion_tokens=1024)
    task.packet["request_sha256"] = _hash(_bytes(task.request.__dict__))
    with pytest.raises(ValueError, match="REPAIR_FUTURE_SOURCE"):
        repair.build_request(task, "rt-sealed-test")


def test_repair_bounds_and_no_repeated_failed_task_provider_call(context):
    task = SealedTask(context)
    with pytest.raises(ValueError, match="TOKEN_CAP"):
        repair.build_request(task, "rt-sealed-test", max_completion_tokens=1025)
    task.original["years"]["2026"]["operating_paths"]["base"]["drivers"]["unit_cost_change"]["evidence_ids"][0] = "fake:two"
    task.original_text = json.dumps(task.original)
    task.packet["response"]["text"] = task.original_text
    req = repair.build_request(task, "rt-sealed-test")
    assert len(json.loads(req.user)["problems"]) == 2
    task.state["stage_validated"] = ["annual"]
    with pytest.raises(ValueError, match="FAILED_V7_ANNUAL_ONLY"):
        repair.build_request(task, "rt-sealed-test")
