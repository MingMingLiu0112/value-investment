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
