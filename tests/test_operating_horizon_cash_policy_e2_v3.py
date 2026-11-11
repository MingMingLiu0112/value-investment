"""Offline direct admission checks for the versioned V11 E2 reader."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW  # noqa: F401
from test_operating_horizon_task_v11_live import _service
from test_operating_horizon_split_v8 import split_context  # noqa: F401
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v3 import (
    read_v11_cash_policy_e2_input,
)


def test_v11_admission_and_fail_closed(task, monkeypatch):
    _, source, _ = task
    pbt = next(row for row in source["evidence"] if row.get("field") == "pre_tax_profit")
    for row in source["evidence"]:
        if row.get("unit") == "CNY":
            row.update(kind="VERIFIED_REPORTED_FACT", physical_page=1)
    for field, amount, scope in (("tax", "91", "consolidated"),
                                 ("parent_profit", "346", "consolidated_parent")):
        row = deepcopy(pbt)
        row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
        source["evidence"].append(row)
    mechanism = "原料采购单价若随长期合同调整而下降，单位成本可能改善；仍需逐季核对同口径营业成本和采购披露。"
    service, calls = _service(task, mechanism)
    queued = service.create(symbol="600519", request_key="TEST_V11_E2", years=[2027], now=NOW)
    task_id = queued["task_id"]
    completed = service.run(task_id, now=NOW)
    assert len(calls) == 2
    if completed["status"] != "SUCCEEDED":
        with pytest.raises(ValueError, match="SUCCEEDED_TWO_STAGE"):
            read_v11_cash_policy_e2_input(root=service.root, task_id=task_id,
                                           now=NOW + timedelta(hours=1), service=service)
        return
    cutoff = NOW + timedelta(hours=1)
    result = read_v11_cash_policy_e2_input(root=service.root, task_id=task_id,
                                           now=cutoff, service=service)
    assert result["status"] == "TEST_ONLY_E2_CONTRACT_REPLAY"
    assert result["input_manifest"]["schema_version"].endswith("v3")
    assert result["input_manifest"]["task_contract"].startswith("operating-horizon-task-v11")
    assert result["annual_operating_status"] == "SAME_TASK_COMPILED"
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None

    view = service.read(task_id)
    projected = SimpleNamespace(read=lambda _: view, _load=service._load,
                                _context=service._context, _packet=service._packet)
    original = deepcopy(view)
    for change, error in (
        (lambda v: v.update(workflow="wrong-version"), "SUCCEEDED_TWO_STAGE"),
        (lambda v: v["stage_responses"].pop("cash"), "RESPONSE_PINS_REQUIRED"),
        (lambda v: v.update(source_binding={"path": "changed", "sha256": "0" * 64}), "TASK_PINS_CHANGED"),
        (lambda v: v.update(updated_at=(NOW + timedelta(hours=2)).isoformat()), "TIME_INVALID"),
        (lambda v: v["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"].update(value=None, classification="UNKNOWN"), "UNKNOWN_CASH_TERM"),
        (lambda v: v["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"].update(value="not-a-number"), "CASH_TERM_INVALID"),
    ):
        view.clear(); view.update(deepcopy(original))
        change(view)
        with pytest.raises(ValueError, match=error):
            read_v11_cash_policy_e2_input(root=service.root, task_id=task_id,
                                           now=cutoff, service=projected)
    view.clear(); view.update(deepcopy(original))
    from value_investment_agent.application.research import operating_horizon_cash_policy_e2_v2 as prior
    def failed_compile(**_):
        raise ValueError("ANNUAL_COMPILE_FAILED")
    monkeypatch.setattr(prior, "compile_verified_annual_candidates", failed_compile)
    with pytest.raises(ValueError, match="ANNUAL_COMPILE_FAILED"):
        read_v11_cash_policy_e2_input(root=service.root, task_id=task_id,
                                       now=cutoff, service=projected)
