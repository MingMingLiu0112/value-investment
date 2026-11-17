"""The M2 queue is research scheduling, never formal admission."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

import pytest

from test_m2_opportunity_discovery import (
    _receipt, _reference, _official_payload, _tencent_payload, _sina_payload,
    _dividend_payload, _financial_points,
)
from value_investment_agent.application.product.value_discovery_surface import publish_value_discovery_report
from value_investment_agent.application.research.value_research_queue import build_value_research_queue


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _inputs(root: Path):
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    payloads = dict(official=_official_payload(), tencent=_tencent_payload(),
                    sina=_sina_payload(), dividend=_dividend_payload(),
                    financial=dict(points=_financial_points()))
    references = {}
    for key, payload in payloads.items():
        reference = _reference(key)
        path = root / reference.path
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        references[key] = replace(reference, sha256=_hash(path))
    receipt = _receipt(run_refs=references)
    receipt_path = runtime / "receipt.json"
    receipt_path.write_text(json.dumps(receipt.as_policy(), ensure_ascii=False), encoding="utf-8")
    report_path = runtime / "value-discovery-report.json"
    publish_value_discovery_report(root=root, receipt_path=receipt_path,
        receipt_sha256=_hash(receipt_path), output_path=report_path)
    return dict(root=root, report_path=report_path, report_sha256=_hash(report_path),
                receipt_path=receipt_path, receipt_sha256=_hash(receipt_path))


def test_queue_is_deduplicated_budgeted_and_replayable(tmp_path):
    inputs = _inputs(tmp_path)
    first = build_value_research_queue(**inputs, budget=1)
    assert first == build_value_research_queue(**inputs, budget=1)
    assert first["action"] == "no_order"
    assert first["admission"] == "RESEARCH_QUEUE_ONLY"
    assert first["selected_count"] == 1
    assert len({item["symbol"] for item in first["entries"]}) == len(first["entries"])
    assert {item["research_state"] for item in first["entries"]} <= {"DISCOVERED", "DATA_CHECK"}
    assert all("VALUATION_MODEL_NOT_VALIDATED" in item["gaps"] for item in first["entries"])
    assert sum(item["queue_status"] == "SELECTED_FOR_DATA_CHECK" for item in first["entries"]) == 1
    empty = build_value_research_queue(**inputs, budget=0)
    assert empty["selected_count"] == 0
    assert all(item["queue_status"] == "BUDGET_DEFERRED" for item in empty["entries"])


def test_queue_rejects_modified_report_and_evidence(tmp_path):
    inputs = _inputs(tmp_path)
    inputs["report_path"].write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_value_research_queue(**inputs, budget=1)
    inputs = _inputs(tmp_path / "second")
    (inputs["root"] / "runtime" / "tencent.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError, match="evidence hash mismatch"):
        build_value_research_queue(**inputs, budget=1)


def test_queue_rejects_rehashed_forged_lead_and_duplicate(tmp_path):
    inputs = _inputs(tmp_path)
    report = json.loads(inputs["report_path"].read_text(encoding="utf-8"))
    report["leads"][0]["candidate_class"] = "VERIFIED"
    inputs["report_path"].write_text(json.dumps(report), encoding="utf-8")
    inputs["report_sha256"] = _hash(inputs["report_path"])
    with pytest.raises(ValueError, match="lead differs"):
        build_value_research_queue(**inputs, budget=1)
    report["leads"][0]["candidate_class"] = "LEAD"
    report["leads"].append(dict(report["leads"][0]))
    inputs["report_path"].write_text(json.dumps(report), encoding="utf-8")
    inputs["report_sha256"] = _hash(inputs["report_path"])
    with pytest.raises(ValueError, match="duplicate"):
        build_value_research_queue(**inputs, budget=1)


def test_previous_queue_requires_earlier_day_and_bound_hash(tmp_path):
    inputs = _inputs(tmp_path)
    first = build_value_research_queue(**inputs, budget=1)
    previous_path = tmp_path / "runtime" / "previous.json"
    previous_path.write_text(json.dumps(first), encoding="utf-8")
    with pytest.raises(ValueError, match="earlier day"):
        build_value_research_queue(**inputs, budget=1,
            previous_path=previous_path, previous_sha256=_hash(previous_path))
    first["entries"][0]["research_state"] = "BUY_REVIEW"
    previous_path.write_text(json.dumps(first), encoding="utf-8")
    with pytest.raises(ValueError, match="content changed"):
        build_value_research_queue(**inputs, budget=1,
            previous_path=previous_path, previous_sha256=_hash(previous_path))


def test_queue_rejects_outside_runtime_and_invalid_budget(tmp_path):
    inputs = _inputs(tmp_path)
    with pytest.raises(ValueError, match="budget"):
        build_value_research_queue(**inputs, budget=-1)
    with pytest.raises(ValueError, match="inside runtime"):
        build_value_research_queue(**{**inputs, "report_path": tmp_path / "other.json"}, budget=1)
