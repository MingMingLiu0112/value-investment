import copy
import json
import os
from pathlib import Path

import pytest

from value_investment_agent.m5_actual_read_model import build_actual_event_read_model
from value_investment_agent.m5_event_dependencies import dependency_graph_from_payload
from value_investment_agent.m5_event_run import m5_event_run_receipt_from_payload
from value_investment_agent.m5_recalculation_plan import bounded_recalculation_plan_from_payload


SOURCE_ROOT = Path(os.environ.get("M5_ACTUAL_EVIDENCE_ROOT", Path(__file__).resolve().parents[1]))
LOCAL_ROOT = Path(__file__).resolve().parents[1]
QUEUE = SOURCE_ROOT / "runtime/m5-600519-disclosure-queue-20260924/source/queue.json"


def _inputs():
    if not QUEUE.is_file():
        pytest.skip("Archived ACTUAL 600519 evidence is unavailable in this checkout")
    source = SOURCE_ROOT / "runtime/m5-600519-disclosure-queue-20260924/delegated-review-application-20260925/reviews.json"
    receipt_path = SOURCE_ROOT / "runtime/m5-600519-disclosure-rescan-20260925/actual-valid-receipts/m5-receipt-44a756ccad5433e236c3d74ff3ce3a75d65be835de52109407ad6ac4f0e0576d.json"
    graph_path = LOCAL_ROOT / "runtime/m5-actual-facts-graph-20260925.json"
    plan_path = LOCAL_ROOT / "runtime/m5-actual-facts-plan-20260925.json"
    facts_path = LOCAL_ROOT / "runtime/m5-verified-facts-actual-20260925.json"
    outcome_path = LOCAL_ROOT / "runtime/m5-bounded-recalculation-result-20260925.json"
    if any(not path.is_file() for path in (graph_path, plan_path, facts_path, outcome_path)):
        pytest.skip("Verified-facts replay inputs are unavailable")
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    return dict(
        queue=load(QUEUE), reviews=load(source),
        receipt=m5_event_run_receipt_from_payload(load(receipt_path)["receipt"]),
        graph=dependency_graph_from_payload(load(graph_path)["graph"]),
        plan=bounded_recalculation_plan_from_payload(load(plan_path)),
        facts_artifact=load(facts_path),
        outcome_receipt=load(outcome_path),
    )


def test_actual_read_model_preserves_nine_reviews_and_two_not_ready_events():
    result = build_actual_event_read_model(**_inputs())
    assert result["reviewed_count"] == 9
    assert result["pending_human_review"] == 0
    assert result["verified_fact_count"] == 5
    assert sum(row["recalculation_status"] == "STILL_NOT_READY" for row in result["rows"]) == 2
    assert all(row["new_valuation_result"] is None and row["action"] == "no_order" for row in result["rows"])


def test_actual_read_model_rejects_wrong_review_pdf_hash():
    inputs = _inputs()
    inputs["reviews"] = copy.deepcopy(inputs["reviews"])
    inputs["reviews"][0]["decisions"][0]["source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="PDF hash"):
        build_actual_event_read_model(**inputs)


def test_actual_read_model_rejects_tampered_facts_payload():
    inputs = _inputs()
    inputs["facts_artifact"] = copy.deepcopy(inputs["facts_artifact"])
    inputs["facts_artifact"]["payload"]["facts"][0]["value"] = "0"
    with pytest.raises(ValueError, match="Verified facts artifact"):
        build_actual_event_read_model(**inputs)


def test_actual_read_model_rejects_tampered_execution_outcome():
    inputs = _inputs()
    inputs["outcome_receipt"] = copy.deepcopy(inputs["outcome_receipt"])
    inputs["outcome_receipt"]["outcomes"][0]["status"] = "RECALCULATED"
    with pytest.raises(ValueError, match="hash mismatch"):
        build_actual_event_read_model(**inputs)


def test_actual_read_model_rejects_wrong_facts_file_version():
    inputs = _inputs()
    inputs["facts_source_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Verified facts artifact"):
        build_actual_event_read_model(**inputs)


def test_actual_read_model_rejects_outcome_bound_to_different_facts():
    inputs = _inputs()
    inputs["outcome_receipt"] = copy.deepcopy(inputs["outcome_receipt"])
    inputs["outcome_receipt"]["facts_payload_sha256"] = "0" * 64
    body = {key: value for key, value in inputs["outcome_receipt"].items()
            if key not in {"result_sha256", "input_file_sha256"}}
    import hashlib
    inputs["outcome_receipt"]["result_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="Verified facts artifact"):
        build_actual_event_read_model(**inputs)
