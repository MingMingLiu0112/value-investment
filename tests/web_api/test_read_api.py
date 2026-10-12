import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from value_investment_agent.presentation.web_api.app import ROOT, create_app


def _write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    target.write_bytes(raw)
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _fixture(root):
    report_receipt = _write(root, "runtime/report-receipt.json", {
        "schema_version": "m2-opportunity-discovery-v2", "universe": {"records": [{}, {}, {}]}})
    extensions = {
        "value_discovery_report": {"status": "RESEARCH_LEADS_ONLY", "lead_symbols": ["600741", "600519"]},
        "m2_quality_diagnostic": {"schema_version": "m2-quality-diagnostic-v1", "quality_coverage_count": 99,
                                  "status_counts": {"PASS": 7}},
        "market_regime_observation": {"schema_version": "market-regime-observation-v1", "status": "UNKNOWN",
                                      "reason": "DATE_UNVERIFIED"},
        "hotspot_watch_queue": {"schema_version": "hotspot-watch-queue-v1", "items": []},
        "value_research_queue": {"schema_version": "value-research-queue-v1", "action": "no_order",
                                 "admission": "RESEARCH_QUEUE_ONLY", "as_of": "2026-10-12",
                                 "entries": [{"symbol": "002612", "company_name": "Lead",
                                              "queue_status": "SELECTED_FOR_DATA_CHECK",
                                              "channels": ["value"], "screening_reasons": ["Price screen"],
                                              "gaps": ["QUOTE_DATE_UNVERIFIED"]}]},
    }
    report = dict(extensions["value_discovery_report"], schema_version="m2-opportunity-report-v1",
                  receipt_binding=report_receipt, semantic_content=extensions["value_discovery_report"])
    bindings = {key: _write(root, f"runtime/{key}.json", report if key == "value_discovery_report" else value)
                for key, value in extensions.items()}
    explanation = _write(root, "runtime/600519-value-decision-explanation.json", {
        "schema_version": "public-value-decision-explanation-v1", "symbol": "600519",
        "action": "no_order", "candidate_explanation": "Pending evidence", "blockers": ["G3"]})
    snapshot = {"action": "no_order", "as_of": "2026-10-12",
                "companies": [{"symbol": "600519", "company_name": "Moutai", "action": "no_order"}],
                "opportunities": [{"symbol": "600741", "company_name": "Huayu", "action": "no_order",
                                   "valuation_status": {"code": "NOT_READY"}, "why_now": "Research intake"}]}
    model = {"schema_version": "historical-company-read-model-preview-v1", "action": "no_order",
             "snapshot": snapshot, "product_extensions": bindings,
             "additional_evidence_bindings": [explanation],
             "historical_preview": True, "canonical_written": False}
    model_binding = _write(root, "runtime/model.json", model)
    handoff = _write(root, "runtime/handoff.json", {
        "schema_version": "research-publication-input-v1", "action": "no_order",
        "snapshot": snapshot, "read_model_binding": model_binding})
    sources = _write(root, "runtime/sources.json", {
        "schema_version": "existing-workbench-preview-bindings-v1", "publication_input_binding": handoff})
    receipt = _write(root, "runtime/publication.json", {
        "schema_version": "canonical-reviewed-research-publication-v1", "canonical_written": True,
        "source_bindings_path": sources["path"], "source_bindings_sha256": sources["sha256"]})
    state = _write(root, "runtime/state.json", {"action": "no_order", "content": {"extensions": extensions}})
    _write(root, "config/current-trial-workbook.json", {
        "schema_version": "m7-current-trial-workbook-v5", "action": "no_order",
        "current_publication": {"status": "PUBLISHED_WPS_READONLY_VERIFIED",
                                "receipt": receipt["path"], "receipt_sha256": receipt["sha256"]},
        "daily_product_state_binding": state})
    return TestClient(create_app(root))


def test_fixture_projection_and_detail(tmp_path):
    client = _fixture(tmp_path)
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["summary"] == {"universe_count": 3, "formal_count": 0, "watch_count": 2}
    assert daily["market"] == {"status": "UNKNOWN", "reason": "DATE_UNVERIFIED"}
    assert {row["id"] for row in daily["sections"]["value"]} == {"600519", "600741", "002612"}
    assert all(row["candidate_action"] == "no_order" for row in daily["sections"]["value"])
    detail = client.get("/api/v1/decisions/600519").json()
    assert detail["decision"]["blockers"] == ["G3"]
    assert detail["decision"]["reason"] == "Pending evidence"
    assert client.get("/api/v1/decisions/600741").json()["status"] == "PENDING_RESEARCH"
    assert client.get("/api/v1/decisions/002612").json()["decision"]["blockers"] == ["QUOTE_DATE_UNVERIFIED"]
    portfolio = client.get("/api/v1/portfolio").json()
    assert portfolio["action"] == "no_order"
    assert portfolio["status"] == "NOT_CONNECTED"
    assert portfolio["positions"] == []
    assert client.get("/api/v1/decision-history").json()["items"] == []


def test_tampered_binding_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/state.json").write_text("{}", encoding="utf-8")
    assert client.get("/api/v1/daily-decisions").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/decisions/600519").json()["decision"] is None


def test_runtime_path_escape_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    pointer_path = tmp_path / "config/current-trial-workbook.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["daily_product_state_binding"] = {"path": "runtime/../../private.json", "sha256": "0" * 64}
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    assert client.get("/api/v1/daily-decisions").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/decisions/../../private.json").status_code != 200


def test_actual_local_publication():
    """Check the real published pointer on this machine.

    The pointer file is tracked but the runtime artifacts it binds are not, so a
    fresh checkout has to skip rather than assert against the developer machine's
    private runtime directory.
    """
    pointer_path = ROOT / "config/current-trial-workbook.json"
    if not pointer_path.is_file():
        pytest.skip("local publication absent")
    binding = json.loads(pointer_path.read_text(encoding="utf-8")).get(
        "daily_product_state_binding") or {}
    relative = str(binding.get("path") or "")
    if not relative or not (ROOT / relative).is_file():
        pytest.skip("local runtime artifacts absent")
    response = TestClient(create_app(ROOT)).get("/api/v1/daily-decisions").json()
    assert response["status"] == "RESEARCH_OBSERVATION"
    assert response["summary"] == {"universe_count": 5573, "formal_count": 0, "watch_count": 114}
    assert response["market"]["status"] == "UNKNOWN"
    assert any(row["id"] == "600741" and row["status"] == "PENDING_RESEARCH"
               for row in response["sections"]["value"])
