from datetime import datetime
import json
from pathlib import Path

from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload
from value_investment_agent.m5_recalculation_plan import (
    STATUS_BLOCKED_GRAPH_GAP,
    build_bounded_recalculation_plan,
)


ROOT = Path(__file__).resolve().parents[1]
RECEIPT = ROOT / "runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"
GRAPH = ROOT / "runtime/m5-600519-disclosure-queue-20260924/m5-research-artifact-graph-600519-20260925.json"


def test_actual_receipt_recalculation_plan_surfaces_missing_fact_nodes():
    receipt = m5_event_run_receipt_from_payload(
        json.loads(RECEIPT.read_text(encoding="utf-8"))["receipt"]
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
