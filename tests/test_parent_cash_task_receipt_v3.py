"""Direct checks for the task receipt admission and replay boundary."""
from datetime import datetime, timezone

import pytest

from value_investment_agent.application.research import parent_cash_task_receipt_v3 as connector


def test_completion_requires_exact_live_success():
    completed = datetime(2026, 11, 21, tzinfo=timezone.utc)
    spec = dict(mode="LIVE_PARENT_CASH_V3", created_at=completed.isoformat())
    state = dict(status="SUCCEEDED", updated_at=completed.isoformat(), action="no_order",
                 formal_eligibility=False, responses=dict.fromkeys(connector.STAGE_ORDER))
    head = dict(path="runtime/head.json", sha256="a" * 64)
    assert connector._completion(spec, state, head, head, completed) == completed
    for patch in (dict(status="FAILED"), dict(action="order"), dict(formal_eligibility=True),
                  dict(responses={}), dict(error_code="FAILED_STAGE")):
        with pytest.raises(ValueError, match="PARENT_TASK_EXACT_LIVE_SUCCESS_REQUIRED"):
            connector._completion(spec, state | patch, head, head, completed)
    with pytest.raises(ValueError, match="PARENT_TASK_EXACT_LIVE_SUCCESS_REQUIRED"):
        connector._completion(spec | dict(mode="TEST_ONLY_PARENT_CASH_V3"), state, head, head, completed)
    with pytest.raises(ValueError, match="PARENT_TASK_EXACT_LIVE_SUCCESS_REQUIRED"):
        connector._completion(spec, state, head, dict(head, sha256="b" * 64), completed)
    with pytest.raises(ValueError, match="PARENT_TASK_COMPLETION_CLOCK_INVALID"):
        connector._completion(spec, state, head, head, datetime(2026, 11, 20, tzinfo=timezone.utc))


def test_receipt_requires_cold_replay_and_immutable_result(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    now = datetime(2026, 11, 21, tzinfo=timezone.utc)
    inputs = dict(task_id="TEST_ONLY", task_head={}, case_package_binding={})
    result = dict(symbol="000568", action="no_order", formal_eligibility=False)
    monkeypatch.setattr(connector, "execute_parent_cash_task_research", lambda **kwargs: result)
    output = root / "runtime/isolated"
    binding = connector.build_parent_cash_task_receipt(root=root, output_dir=output, now=now, **inputs)
    assert connector.replay_parent_cash_task_receipt(root=root, receipt_binding=binding, now=now) == result
    with pytest.raises(FileExistsError, match="PARENT_TASK_NEW_OUTPUT_REQUIRED"):
        connector.build_parent_cash_task_receipt(root=root, output_dir=output, now=now, **inputs)
    result["symbol"] = "600887"
    with pytest.raises(ValueError, match="PARENT_TASK_RECEIPT_COLD_REPLAY_CHANGED"):
        connector.replay_parent_cash_task_receipt(root=root, receipt_binding=binding, now=now)
    (output / "result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="HASH"):
        connector.replay_parent_cash_task_receipt(root=root, receipt_binding=binding, now=now)



def test_successful_task_publishes_a_single_receipt_after_run(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from pathlib import Path
    import json
    from value_investment_agent.application.research import parent_cash_task_completion_v1 as completion

    task_id = "rt-" + "1" * 32
    spec_binding = {"path": "runtime/spec.json", "sha256": "a" * 64}
    case_binding = {"path": "runtime/case.json", "sha256": "b" * 64}
    head = {"path": "runtime/head.json", "sha256": "c" * 64}
    status = "SUCCEEDED"
    calls = []
    worker_calls = []

    class Service:
        root = tmp_path

        def _bound(self, binding):
            if binding == spec_binding:
                return dict(symbol="000568", action="no_order", model_applicable=True)
            assert binding == case_binding
            return dict(symbol="000568", profile_id="quality_compounder",
                        schema_version="m1-valuation-package-v2", research_case=dict(symbol="000568"))

        def run(self, identifier):
            worker_calls.append(identifier)

        def _directory(self, identifier):
            return tmp_path / identifier

        def _lock(self, directory, name="state"):
            return nullcontext()

        def _load(self, identifier):
            return {"spec_binding": spec_binding, "mode": "LIVE_PARENT_CASH_V3"}, {"status": status}, head

    def execute(*, root, task_id, task_head, case_package_binding, now):
        assert root == Path(tmp_path).resolve()
        assert task_head == head and case_package_binding == case_binding
        calls.append(task_head)
        return dict(action="no_order", formal_eligibility=False,
                    provenance=dict(task_id=task_id, task_record_binding=task_head))

    monkeypatch.setattr(connector, "execute_parent_cash_task_research", execute)
    with pytest.raises(ValueError, match="PARENT_TASK_CASE_BINDING_REQUIRED"):
        completion.run_and_seal_parent_cash_task(Service(), task_id)
    assert not calls
    assert not worker_calls
    failed = completion.read_valuation_publication(tmp_path, task_id, head)
    assert failed["valuation_receipt_status"] == "BLOCKED"
    assert failed["valuation_blockage"]["reason_code"] == "PARENT_TASK_CASE_BINDING_REQUIRED"
    registry = tmp_path / "config" / "parent-cash-task-case-bindings-v1.json"
    registry.parent.mkdir()
    registry.write_text(json.dumps({
        "schema_version": "parent-cash-task-case-bindings-v1",
        "specs": {spec_binding["sha256"]: {
            "spec_binding": spec_binding, "case_package_binding": case_binding,
        }},
    }), encoding="utf-8")
    status = "QUEUED"
    completion.seal_completed_parent_cash_task(Service(), task_id)
    assert not calls
    assert not worker_calls
    status = "CANCELLED"
    completion.run_and_seal_parent_cash_task(Service(), task_id)
    assert not calls
    status = "SUCCEEDED"
    completion.run_and_seal_parent_cash_task(Service(), task_id)
    path = completion.valuation_receipt_path(tmp_path, task_id)
    assert json.loads(path.read_bytes())["inputs"]["task_head"] == head
    completion.run_and_seal_parent_cash_task(Service(), task_id)
    assert calls == [head, head, head]  # Build, cold replay, then retained-receipt retry verification.
    assert worker_calls == [task_id]  # The cancelled fixture alone entered the worker.
    assert completion.read_valuation_publication(tmp_path, task_id, head) == {
        "valuation_receipt_status": "SEALED_REPLAY_REQUIRED",
        "valuation_blockage": None,
    }
