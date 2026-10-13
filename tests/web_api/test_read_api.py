import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_BOOTSTRAP, open_session
from value_investment_agent.presentation.web_api.app import ROOT, create_app


def _write(root, path, value):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
    target.write_bytes(raw)
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _write_raw(root, path, text):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = text.encode("utf-8")
    target.write_bytes(raw)
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest()}


def _fixture(root, *, receipt_records=None, receipt_text=None, report_overrides=None):
    if receipt_text is not None:
        report_receipt = _write_raw(root, "runtime/report-receipt.json", receipt_text)
    else:
        records = [{"symbol": "600519"}, {"symbol": "600741"}, {"symbol": "000333"}] \
            if receipt_records is None else receipt_records
        report_receipt = _write(root, "runtime/report-receipt.json", {
            "schema_version": "m2-opportunity-discovery-v2", "universe": {"records": records}})
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
                  receipt_binding=report_receipt, semantic_content=extensions["value_discovery_report"],
                  deduplicated_lead_count=2)
    if receipt_text is None:
        report["data_health"] = {"universe_count": len(records)}
    report.update(report_overrides or {})
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
    client = TestClient(create_app(root, port=8791, bootstrap_secret=TEST_BOOTSTRAP),
                        base_url="http://127.0.0.1:8791", client=("127.0.0.1", 51000))
    client.headers.update({"host": "127.0.0.1:8791", "origin": "http://127.0.0.1:8791"})
    client.headers["x-local-session"] = open_session(client)
    return client


def test_fixture_projection_and_detail(tmp_path):
    client = _fixture(tmp_path)
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["summary"] == {"universe_count": 3, "formal_count": 0, "watch_count": 2}
    assert daily["market"] == {"status": "UNKNOWN", "reason": "DATE_UNVERIFIED"}
    assert {row["id"] for row in daily["sections"]["value"]} == {"600519", "600741", "002612"}
    assert all(row["candidate_action"] == "no_order" for row in daily["sections"]["value"])
    bound = next(item for item in daily["sections"]["value"] if item["id"] == "600519")
    assert bound["blockers"] == ["G3"]
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


def test_unreadable_explanation_is_marked_not_hidden(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/600519-value-decision-explanation.json").write_text("{", encoding="utf-8")
    daily = client.get("/api/v1/daily-decisions").json()
    row = next(item for item in daily["sections"]["value"] if item["id"] == "600519")
    assert row["blockers"] == ["VALUE_EXPLANATION_BINDING_UNAVAILABLE"]


def test_missing_bound_file_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/state.json").unlink()
    assert client.get("/api/v1/daily-decisions").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/decisions/600519").json()["status"] == "UNAVAILABLE"


def test_runtime_path_escape_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    pointer_path = tmp_path / "config/current-trial-workbook.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["daily_product_state_binding"] = {"path": "runtime/../../private.json", "sha256": "0" * 64}
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    assert client.get("/api/v1/daily-decisions").json()["status"] == "UNAVAILABLE"
    assert client.get("/api/v1/decisions/../../private.json").status_code != 200


def test_missing_bound_extension_fails_closed_without_counts(tmp_path):
    """Losing a bound product extension must not read as a real zero-candidate day."""
    client = _fixture(tmp_path)
    (tmp_path / "runtime/value_discovery_report.json").unlink()
    body = client.get("/api/v1/daily-decisions").json()
    assert body["status"] == "UNAVAILABLE"
    assert body["gate_code"] == "PUBLICATION_UNAVAILABLE"
    assert body["summary"] == {"universe_count": None, "formal_count": 0, "watch_count": None}
    assert body["sections"] == {"holdings": [], "value": [], "hotspot": []}


def test_missing_discovery_receipt_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/report-receipt.json").unlink()
    body = client.get("/api/v1/daily-decisions").json()
    assert body["status"] == "UNAVAILABLE"
    assert body["gate_code"] == "VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE"
    assert body["publication_source"] == "runtime/report-receipt.json"
    assert body["sections"]["value"] == []


def test_corrupt_discovery_receipt_fails_closed(tmp_path):
    client = _fixture(tmp_path, receipt_text="{not json")
    body = client.get("/api/v1/daily-decisions").json()
    assert body["status"] == "UNAVAILABLE"
    assert body["gate_code"] == "VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE"


def test_receipt_hash_mismatch_fails_closed(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/report-receipt.json").write_text(
        '{"schema_version":"m2-opportunity-discovery-v2","universe":{"records":[]}}', encoding="utf-8")
    body = client.get("/api/v1/daily-decisions").json()
    assert body["status"] == "UNAVAILABLE"
    assert body["gate_code"] == "VALUE_DISCOVERY_RECEIPT_BINDING_UNAVAILABLE"


def test_universe_shape_and_counts_must_agree(tmp_path):
    shape = _fixture(tmp_path / "shape", receipt_text='{"schema_version":"m2-opportunity-discovery-v2",'
                                                     '"universe":{"records":"nope"}}')
    body = shape.get("/api/v1/daily-decisions").json()
    assert body["gate_code"] == "VALUE_DISCOVERY_UNIVERSE_UNAVAILABLE"

    schema = _fixture(tmp_path / "schema", receipt_text='{"schema_version":"other","universe":{"records":[]}}')
    body = schema.get("/api/v1/daily-decisions").json()
    assert body["gate_code"] == "VALUE_DISCOVERY_UNIVERSE_UNAVAILABLE"

    mismatch = _fixture(tmp_path / "count", report_overrides={"data_health": {"universe_count": 99}})
    body = mismatch.get("/api/v1/daily-decisions").json()
    assert body["gate_code"] == "VALUE_DISCOVERY_UNIVERSE_INCONSISTENT"

    leads = _fixture(tmp_path / "leads", report_overrides={"deduplicated_lead_count": 5})
    body = leads.get("/api/v1/daily-decisions").json()
    assert body["gate_code"] == "VALUE_DISCOVERY_LEAD_COUNT_INCONSISTENT"

    missing = _fixture(tmp_path / "missing", receipt_records=[{"symbol": "000001"}, {"symbol": "000002"},
                                                             {"symbol": "000003"}])
    body = missing.get("/api/v1/daily-decisions").json()
    assert body["gate_code"] == "VALUE_DISCOVERY_LEAD_NOT_IN_UNIVERSE"


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
