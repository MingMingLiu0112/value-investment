import copy
from datetime import datetime, timezone
import json
import os
from types import SimpleNamespace

import pytest

from value_investment_agent.m5_scenario_research_review import (
    _sha, build_need_more_evidence_review, validate_need_more_evidence_review,
)


def _context():
    pdf = "a" * 64
    receipt_sha = "b" * 64
    decision = {
        "event_decision_id": "decision-1", "symbol": "600519",
        "announcement_id": "filing-1", "human_decision": "MATERIAL_REQUIRES_RECALCULATION",
        "source_sha256": pdf, "source_ref": {"source_url": "https://example.test/filing.pdf"},
        "reviewed_at": "2026-09-24T08:00:00+00:00",
    }
    event = SimpleNamespace(
        event_id="event-1", source_event_id="materiality-review:decision-1",
        symbol="600519", current_state={"source_sha256": pdf},
    )
    receipt = SimpleNamespace(
        namespace="ACTUAL", action="no_order", active_events=(event,),
        receipt_id="receipt-1", state_sha256=receipt_sha,
        generated_at=datetime(2026, 9, 24, 9, tzinfo=timezone.utc),
    )
    pending = {
        "symbol": "600519", "input_sha256": "c" * 64,
        "facts": {"scenario_inputs": None}, "assumptions": None,
        "valuation_approval": None,
        "sources": [
            {"sha256": receipt_sha, "location": "m5-actual-receipt"},
            {"sha256": pdf, "location": "https://example.test/filing.pdf"},
        ],
    }
    return dict(
        source_bytes=b"human review: NEED_MORE_EVIDENCE",
        review_package_bytes=b"event-bound proposal, not approved",
        pending_input_bytes=json.dumps(pending).encode(),
        receipt=receipt, decisions=[decision], graph_sha256="d" * 64,
        facts_payload_sha256="e" * 64, facts_file_sha256="f" * 64,
        bounded_result_sha256="1" * 64,
    )


def test_negative_review_binds_all_inputs_and_never_approves_model():
    context = _context()
    review = build_need_more_evidence_review(
        **context, recorded_at="2026-09-25T09:00:00+00:00",
    )
    validate_need_more_evidence_review(review, **context)
    assert review["decision"] == "NEED_MORE_EVIDENCE"
    assert set(review["axis_decisions"].values()) == {"NOT_APPROVED"}
    assert review["event_bound_scenario_inputs_approved"] is False
    assert review["valuation_refresh_approved"] is False
    assert review["model_executed"] is False
    assert review["new_valuation_result"] is None
    assert review["action"] == "no_order"
    assert len(review["material_events"]) == 1
    assert len(review["evidence_triggers"]) == 8
    assert {item["addresses"] for item in review["evidence_triggers"]} == set(review["blockers"])
    assert {item["on_evidence"] for item in review["evidence_triggers"]} == {"REOPEN_RESEARCH"}


@pytest.mark.parametrize("change", [
    lambda item: item["material_events"].clear(),
    lambda item: item["axis_decisions"].update({"base_roe_path": "APPROVED"}),
    lambda item: item.update({"event_bound_scenario_inputs_approved": True}),
    lambda item: item.update({"valuation_refresh_approved": True}),
    lambda item: item.update({"new_valuation_result": {"base": "123"}}),
    lambda item: item["blockers"].pop(),
    lambda item: item["evidence_triggers"][0].update({"on_evidence": "RECALCULATE"}),
    lambda item: item.update({"pending_input_sha256": "0" * 64}),
])
def test_rehashed_negative_review_cannot_change_decision_or_lineage(change):
    context = _context()
    review = build_need_more_evidence_review(
        **context, recorded_at="2026-09-25T09:00:00+00:00",
    )
    forged = copy.deepcopy(review)
    change(forged)
    forged["review_sha256"] = _sha({key: value for key, value in forged.items()
                                     if key != "review_sha256"})
    with pytest.raises(ValueError, match="differs from original"):
        validate_need_more_evidence_review(forged, **context)


def test_negative_review_rejects_wrong_source_and_completed_input():
    context = _context()
    review = build_need_more_evidence_review(
        **context, recorded_at="2026-09-25T09:00:00+00:00",
    )
    with pytest.raises(ValueError, match="differs from original"):
        validate_need_more_evidence_review(review, **{**context, "source_bytes": b"other"})
    pending = json.loads(context["pending_input_bytes"])
    pending["facts"]["scenario_inputs"] = {"base": {}}
    with pytest.raises(ValueError, match="blocked event-bound input lineage"):
        build_need_more_evidence_review(
            **{**context, "pending_input_bytes": json.dumps(pending).encode()},
            recorded_at="2026-09-25T09:00:00+00:00",
        )
    with pytest.raises(ValueError, match="record time is invalid"):
        build_need_more_evidence_review(
            **context, recorded_at="2026-09-23T09:00:00+00:00",
        )


def test_reviewed_candidate_shows_blockers_without_recalculation(tmp_path):
    from openpyxl import load_workbook
    from value_investment_agent.m7_daily_workbench import write_daily_workbench
    from pathlib import Path
    import runpy

    root = Path(__file__).resolve().parents[1]
    evidence_root = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", root))
    model_path = evidence_root / "runtime" / "m5-actual-read-model-human-reviewed-need-more-evidence-20260925.json"
    if not model_path.exists():
        pytest.skip("local ACTUAL reviewed read model is unavailable")
    builder = runpy.run_path(str(evidence_root / "scripts" / "build_m7_daily_workbench_post_checkpoint_a.py"))
    packet = builder["build_packet"](datetime(2026, 9, 25, tzinfo=timezone.utc))
    packet["m5"]["disclosure_queue_600519"]["pending_count"] = 0
    packet["m5"]["disclosure_queue_600519"]["pending_items"] = []
    model = json.loads(model_path.read_text(encoding="utf-8"))
    packet["m5"]["actual_event_chain"] = model
    output = tmp_path / "review.xlsx"
    write_daily_workbench(packet, output=output, root=tmp_path)
    workbook = load_workbook(output, read_only=True, data_only=True)
    values = [str(value) for row in workbook["06_事件与预警"].values for value in row if value is not None]
    assert any("NEED_MORE_EVIDENCE" in value and "无交易指令" in value for value in values)
    assert sum("STILL_NOT_READY" in value for value in values) == 2
    assert any("TERMINAL_ASSUMPTIONS_NOT_REVIEWED" in value for value in values)
    assert any("forecast_horizon_roe_fade_terminal_evidence" in value for value in values)
    downgraded = copy.deepcopy(packet)
    del downgraded["m5"]["actual_event_chain"]["research_review_status"]
    with pytest.raises(ValueError, match="research review must remain blocked"):
        write_daily_workbench(downgraded, output=tmp_path / "downgraded.xlsx", root=tmp_path)
    forged = copy.deepcopy(packet)
    material = next(row for row in forged["m5"]["actual_event_chain"]["rows"] if row["event_id"])
    material["recalculation_status"] = "RECALCULATED"
    with pytest.raises(ValueError, match="research review must remain blocked"):
        write_daily_workbench(forged, output=tmp_path / "forged.xlsx", root=tmp_path)
