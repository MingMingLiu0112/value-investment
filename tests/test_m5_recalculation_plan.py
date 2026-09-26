from datetime import datetime
import json
import os
from pathlib import Path
import pytest

from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload
from value_investment_agent.m5_recalculation_plan import (
    STATUS_BLOCKED_GRAPH_GAP,
    build_bounded_recalculation_plan,
    bounded_recalculation_plan_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
FACT_ROOT = Path(os.environ.get("M5_ACTUAL_FACT_ROOT", ROOT))
EVIDENCE_ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", ROOT))
RECEIPT = EVIDENCE_ROOT / "runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"
GRAPH = EVIDENCE_ROOT / "runtime/m5-600519-disclosure-queue-20260924/m5-research-artifact-graph-600519-20260925.json"


def test_actual_receipt_recalculation_plan_surfaces_missing_fact_nodes():
    if not RECEIPT.is_file() or not GRAPH.is_file():
        pytest.skip("Actual receipt and graph are not available in this checkout")
    receipt = m5_event_run_receipt_from_payload(
        json.loads(RECEIPT.read_text(encoding="utf-8"))["receipt"],
        allow_legacy_read_only=True,
    )
    graph = dependency_graph_from_payload(
        json.loads(GRAPH.read_text(encoding="utf-8"))["graph"]
    )

    plan = build_bounded_recalculation_plan(
        receipt=receipt,
        graph=graph,
        generated_at=datetime.fromisoformat("2026-09-25T08:11:00+08:00"),
    )

    assert plan.blocked is True
    gaps = {
        task.dependency_kind: task.blockers
        for task in plan.tasks
        if task.status == STATUS_BLOCKED_GRAPH_GAP
    }
    assert gaps["financial_facts"] == ("missing_dependency_node:financial_facts",)
    assert gaps["valuation_result"] == ("missing_dependency_node:valuation_result",)


def test_new_actual_graph_resolves_real_fact_and_valuation_nodes():
    path = FACT_ROOT / "runtime/m5-actual-facts-plan-20260925.json"
    if not path.is_file():
        if os.environ.get("M5_ACTUAL_FACT_ROOT"):
            pytest.fail(f"Required ACTUAL facts plan is missing: {path}")
        pytest.skip("Actual verified-facts replay is unavailable")
    plan = bounded_recalculation_plan_from_payload(json.loads(path.read_text(encoding="utf-8")))
    gaps = {task.dependency_kind for task in plan.tasks if task.status == STATUS_BLOCKED_GRAPH_GAP}
    assert gaps == {"valuation_inputs"}
    assert all(task.action == "no_order" for task in plan.tasks)
