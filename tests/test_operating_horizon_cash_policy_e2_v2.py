"""Direct V10 E2 admission checks, using the offline two-stage task fixture."""
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

import pytest

from test_operating_horizon_task_v10_live import task, NOW  # noqa: F401
from test_operating_horizon_split_v8 import split_context  # noqa: F401
from test_operating_horizon_draft_v1 import context as base_context  # noqa: F401
from value_investment_agent.application.research.operating_horizon_cash_policy_e2_v2 import (
    read_v10_cash_policy_e2_input,
)


def test_v10_complete_task_only_and_tamper_fail_closed(task):
    service, source, calls = task
    pbt = next(row for row in source["evidence"] if row.get("field") == "pre_tax_profit")
    for row in source["evidence"]:
        if row.get("unit") == "CNY":
            row["kind"] = "VERIFIED_REPORTED_FACT"
            row["physical_page"] = 1
    for field, amount, scope in (("tax", "91", "consolidated"),
                                 ("parent_profit", "346", "consolidated_parent")):
        row = deepcopy(pbt)
        row.update(id="TEST_ONLY:" + field, field=field, value=amount, scope=scope)
        source["evidence"].append(row)
    created = service.create(symbol="600519", request_key="TEST_V10_E2_ADMISSION", years=[2027], now=NOW)
    task_id = created["task_id"]
    completed = service.run(task_id, now=NOW)
    assert len(calls) == 2
    assert completed["status"] in {"SUCCEEDED", "WAITING_EVIDENCE"}
    if completed["status"] == "WAITING_EVIDENCE":
        with pytest.raises(ValueError, match="SUCCEEDED_TWO_STAGE"):
            read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
                now=NOW + timedelta(hours=1), service=service)
        return
    result = read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
        now=NOW + timedelta(hours=1), service=service)
    assert result["annual_operating_status"] == "SAME_TASK_COMPILED"
    assert result["policy_years"]["2027"]["base"]["complete"] is True
    assert result["action"] == "no_order" and result["formal_eligibility"] is False
    assert result["condition_price"] is None
    assert len(result["input_manifest"]["stage_responses"]) == 2

    view = service.read(task_id)
    projected = SimpleNamespace(read=lambda _: view, _load=service._load,
        _context=service._context, _packet=service._packet)
    original = deepcopy(view)
    view["stage_responses"].pop("cash")
    with pytest.raises(ValueError, match="RESPONSE_PINS_REQUIRED"):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=projected)
    view.clear(); view.update(deepcopy(original))
    view["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"].update(
        classification="UNKNOWN", value=None, unit="not_quantified")
    with pytest.raises(ValueError, match="UNKNOWN_CASH_TERM"):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=projected)
    view.clear(); view.update(deepcopy(original))
    del view["research_result"]["years"]["2027"]["shareholder_cash_paths"]["base"]["terms"]["operating_wc_cash_cny"]
    with pytest.raises(ValueError, match="CASH_TERMS_INCOMPLETE"):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=projected)
    view.clear(); view.update(deepcopy(original))
    view["source_binding"] = {"path": "changed", "sha256": "0" * 64}
    with pytest.raises(ValueError, match="TASK_PINS_CHANGED"):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=projected)
    view.clear(); view.update(deepcopy(original))
    view["updated_at"] = (NOW + timedelta(hours=2)).isoformat()
    with pytest.raises(ValueError, match="TIME_INVALID"):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=projected)
    packet = service._directory(task_id) / "response-cash.json"
    packet.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        read_v10_cash_policy_e2_input(root=service.root, task_id=task_id,
            now=NOW + timedelta(hours=1), service=service)
