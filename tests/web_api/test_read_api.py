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


def _fixture(root, *, receipt_records=None, receipt_text=None, report_overrides=None,
             explanation_extra=None, company_extra=None, extra_extensions=None,
             snapshot_overrides=None):
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
    extra = dict(extra_extensions or {})
    extensions.update(extra)
    report = dict(extensions["value_discovery_report"], schema_version="m2-opportunity-report-v1",
                  receipt_binding=report_receipt, semantic_content=extensions["value_discovery_report"],
                  deduplicated_lead_count=2)
    if receipt_text is None:
        report["data_health"] = {"universe_count": len(records)}
    report.update(report_overrides or {})
    bindings = {}
    for key, value in extensions.items():
        if key in extra:
            # A published extension stores its semantic content beside the
            # record, exactly like the real publication does.
            bindings[key] = _write(root, f"runtime/{key}.json",
                                   dict(value, semantic_content=value))
        else:
            bindings[key] = _write(root, f"runtime/{key}.json",
                                   report if key == "value_discovery_report" else value)
    explanation = _write(root, "runtime/600519-value-decision-explanation.json", {
        "schema_version": "public-value-decision-explanation-v1", "symbol": "600519",
        "action": "no_order", "candidate_explanation": "Pending evidence", "blockers": ["G3"],
        **(explanation_extra or {})})
    snapshot = {"action": "no_order", "as_of": "2026-10-12",
                "companies": [{"symbol": "600519", "company_name": "Moutai", "action": "no_order",
                               **(company_extra or {})}],
                "opportunities": [{"symbol": "600741", "company_name": "Huayu", "action": "no_order",
                                   "valuation_status": {"code": "NOT_READY"}, "why_now": "Research intake"}]}
    snapshot.update(snapshot_overrides or {})
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


@pytest.mark.parametrize('stale', [False, True])
def test_hotspot_detail_uses_independent_projection_after_current_case_verification(tmp_path, monkeypatch, stale):
    from copy import deepcopy
    from value_investment_agent.presentation.web_api import app as api_module
    from value_investment_agent.presentation.web_api import private_routes
    from value_investment_agent.application.hotspot import independent_price_conditions as projection
    from value_investment_agent.application.portfolio.private_portfolio_service import PrivateStoreUnavailable

    def no_private_root(**kwargs):
        raise PrivateStoreUnavailable("TEST_ONLY isolated private root absence")

    monkeypatch.setattr(private_routes, "resolve_private_root", no_private_root)

    client = _fixture(tmp_path)
    plan = dict(schema_version='price-action-plan-current-v1', symbol='600519',
        action='no_order', decision_id='hotspot-600519-test', market_trade_date='2026-10-12',
        signal_state='TRIGGER_OBSERVED', explanation='TEST_ONLY route wiring',
        model_or_rule_version='TEST_ONLY-v1', case_path='runtime/case.json', case_sha256='a'*64,
        opportunity_quality={'structure_tier': 'STRUCTURE_QUALIFIED_OBSERVATION'},
        blockers=['VALUE_GATE_NOT_PROVEN'], entry_trigger_price='10', invalidation_price='9')
    packet = dict(publication_id='TEST_ONLY', research_version='TEST_ONLY',
        price_conditions={'items': [dict(symbol='600519', company_name='TEST_ONLY', price_action_plan=plan)]})
    before = deepcopy(packet)
    monkeypatch.setattr(api_module, '_load_snapshot', lambda root: (packet, {}))

    def verify(**kwargs):
        if stale:
            raise ValueError('B1 current close rejected')
        return {}

    monkeypatch.setattr(api_module, 'load_current_price_case', verify)
    monkeypatch.setattr(projection, 'load_independent_admission', lambda *args, **kwargs: dict(
        blockers=[], risk_review_eligible=True, rule_version='TEST_ONLY-v1',
        gate_source_bindings={'price_structure': [dict(path='runtime/case.json', sha256='a'*64)]}))
    response = client.get('/api/v1/decisions/hotspot-600519-test?independent_hotspot=true').json()
    result = response['decision']['price_action_plan']
    assert result['schema_version'] == 'price-action-plan-independent-v2'
    assert result['risk_review_eligible'] is (not stale)
    assert 'VALUE_GATE_NOT_PROVEN' not in result['blockers']
    assert 'VALUE_GATE_NOT_PROVEN' in result['legacy_observation_blockers']
    assert result['formal_eligibility'] is result['trade_eligible'] is False
    assert result['action'] == 'no_order'
    if stale:
        assert result['signal_state'] == 'STALE'
        assert result['entry_trigger_price'] is result['invalidation_price'] is None
    assert packet == before
    legacy = client.get('/api/v1/decisions/hotspot-600519-test').json()['decision']['price_action_plan']
    assert legacy['schema_version'] == 'price-action-plan-current-v1'
    assert 'VALUE_GATE_NOT_PROVEN' in legacy['blockers']
    portfolio = client.get("/api/v1/portfolio").json()
    assert portfolio["action"] == "no_order"
    assert portfolio["status"] == "NOT_CONNECTED"
    assert portfolio["positions"] == []
    assert client.get("/api/v1/decision-history").json()["items"] == []


def test_daily_research_section_is_honest_about_unregistered_inputs(tmp_path):
    client = _fixture(tmp_path)
    daily = client.get("/api/v1/daily-decisions").json()
    research = daily["research"]
    assert research["schema_version"] == "daily-research-status-v1"
    assert research["action"] == "no_order"
    # The fixture registers no quote binding, so the section must not invent rows.
    assert research["status"] == "NO_REGISTERED_QUOTES"
    assert research["rows"] == []
    assert daily["summary"]["formal_count"] == 0


def test_daily_research_section_is_present_when_the_publication_is_broken(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/state.json").write_text("{}", encoding="utf-8")
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["status"] == "UNAVAILABLE"
    assert daily["research"]["status"] == "UNAVAILABLE"
    assert daily["research"]["rows"] == []


def _not_connected_report(**overrides):
    report = {"schema_version": "dual-sleeve-risk-review-v1", "action": "no_order",
              "status": "NOT_CONNECTED", "namespace": "ACTUAL",
              "blockers": ["portfolio.private_input_missing"], "sleeves": None,
              "aggregate": None, "hotspot_quantity_review": None,
              "position_guidance": None, "expected_return": None,
              "trade_eligible": False, "acceptance_authority": "NONE",
              "generated_at": "2026-10-12T19:24:27.760495+08:00"}
    report.update(overrides)
    return report


def test_daily_actionable_scope_does_not_invent_market_or_personal_conclusions(tmp_path):
    client = _fixture(tmp_path)
    body = client.get("/api/v1/daily-decisions").json()
    evaluation = body["actionable_evaluation"]
    assert evaluation["scope"] == "PUBLISHED_COMPANIES_ONLY"
    assert evaluation["conclusion"] == "INCOMPLETE_EVALUATION"
    assert evaluation["operation_eligible_count"] == 0
    assert evaluation["unassessable_count"] == len(evaluation["items"])
    assert evaluation["action"] == "no_order"
    assert all(row["decision_action"] == "UNASSESSABLE" and row["review_quantity"] is None
               for row in evaluation["items"])


def test_daily_dual_sleeve_section_restates_the_bound_report(tmp_path):
    """The section restates the published review and never fills guidance in."""
    client = _fixture(tmp_path, extra_extensions={
        "dual_sleeve_report": _not_connected_report()})
    surface = client.get("/api/v1/daily-decisions").json()["dual_sleeve"]
    assert surface["schema_version"] == "daily-dual-sleeve-surface-v1"
    assert surface["action"] == "no_order"
    assert surface["status"] == "NOT_CONNECTED"
    assert surface["namespace"] == "ACTUAL"
    assert surface["portfolio_connected"] is False
    assert surface["position_guidance"] is None
    assert surface["position_guidance_available"] is False
    assert surface["trade_eligible"] is False
    assert surface["acceptance_authority"] == "NONE"
    assert surface["blockers"] == ["portfolio.private_input_missing"]
    assert surface["next_user_input"] == "PRIVATE_PORTFOLIO_INPUT_REQUIRED"
    assert surface["source"] == "runtime/dual_sleeve_report.json"


def test_daily_dual_sleeve_section_without_binding_reports_real_not_connected(tmp_path):
    """An older publication gets the shared not-connected review, not a story."""
    client = _fixture(tmp_path)
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["status"] == "RESEARCH_OBSERVATION"
    surface = daily["dual_sleeve"]
    assert surface["action"] == "no_order"
    assert surface["status"] == "NOT_CONNECTED"
    assert surface["blockers"] == ["portfolio.private_input_missing"]
    assert surface["source"] is None
    assert surface["position_guidance"] is None
    assert surface["trade_eligible"] is False


def test_daily_dual_sleeve_section_fails_closed_alone_on_a_bad_report(tmp_path):
    """A malformed secondary report must not take the research page down."""
    client = _fixture(tmp_path, extra_extensions={
        "dual_sleeve_report": _not_connected_report(action="order")})
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["status"] == "RESEARCH_OBSERVATION"
    assert daily["sections"]["value"]
    surface = daily["dual_sleeve"]
    assert surface["status"] == "UNAVAILABLE"
    assert surface["blockers"] == ["DUAL_SLEEVE_SURFACE_INVALID"]
    assert surface["position_guidance"] is None


def test_dual_sleeve_section_is_present_when_the_publication_is_broken(tmp_path):
    client = _fixture(tmp_path)
    (tmp_path / "runtime/state.json").write_text("{}", encoding="utf-8")
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["status"] == "UNAVAILABLE"
    assert daily["dual_sleeve"]["status"] == "UNAVAILABLE"
    assert daily["dual_sleeve"]["blockers"] == ["DUAL_SLEEVE_STATUS_UNAVAILABLE"]
    assert daily["dual_sleeve"]["position_guidance"] is None


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
    surface = response["dual_sleeve"]
    assert surface["action"] == "no_order"
    assert surface["status"] == "NOT_CONNECTED"
    assert surface["position_guidance"] is None
    assert surface["trade_eligible"] is False
    assert surface["acceptance_authority"] == "NONE"
    packet = TestClient(create_app(ROOT)).get("/api/v1/daily-public-packet").json()
    assert packet["packet_status"] == "CURRENT"
    assert packet["publication_id"].startswith("pub-")
    assert packet["source_bindings_verified"] is True
    assert response["publication"]["publication_id"] == packet["publication_id"]
    assert response["publication"]["research_version"] == packet["research_version"]


def test_daily_public_packet_is_the_one_shared_identity(tmp_path):
    client = _fixture(tmp_path)
    packet = client.get("/api/v1/daily-public-packet").json()
    assert packet["schema_version"] == "daily-public-packet-v1"
    assert packet["action"] == "no_order"
    assert packet["packet_status"] == "CURRENT"
    assert packet["chain_error"] is None
    assert packet["publication_id"].startswith("pub-")
    assert packet["dates"]["research_as_of"] == "2026-10-12"
    assert set(packet["company_statuses"]) == {"600519", "600741"}
    assert packet["formal_admission_count"] == 0
    assert packet["pending_review_count"] == 1
    assert packet["research_counts"] == {"universe_count": 3, "lead_count": 2, "queue_count": 1,
                                         "needs_re_research_count": 0,
                                         "incomplete_research_count": 1,
                                         "awaiting_verified_close_count": 2}
    assert "NO_FORMAL_ADMISSION" in packet["blockers"]
    assert packet["source_bindings"] and packet["source_bindings_verified"] is True
    assert packet["data_freshness"]["quote"]["status"] == "UNAVAILABLE"
    assert packet["data_freshness"]["research"]["status"] == "UNKNOWN"
    # The public packet never speaks for the private ledger.
    assert "PRIVATE" not in json.dumps(packet, ensure_ascii=False)

    daily = client.get("/api/v1/daily-decisions").json()
    detail = client.get("/api/v1/decisions/600519").json()
    history = client.get("/api/v1/decision-history").json()
    assert daily["blockers"] == ["NO_FORMAL_ADMISSION"]
    assert {daily["publication"]["publication_id"], detail["publication"]["publication_id"],
            history["publication"]["publication_id"]} == {packet["publication_id"]}
    # Rebuilding from the same verified inputs is deterministic.
    assert client.get("/api/v1/daily-public-packet").json()["publication_id"] == packet["publication_id"]


def test_daily_public_packet_fails_closed_and_never_invents_identity(tmp_path):
    client = _fixture(tmp_path)
    assert client.get("/api/v1/daily-public-packet").json()["packet_status"] == "CURRENT"
    (tmp_path / "runtime/publication.json").write_text(
        '{"schema_version":"canonical-reviewed-research-publication-v1","canonical_written":true}',
        encoding="utf-8")
    packet = client.get("/api/v1/daily-public-packet").json()
    assert packet["packet_status"] == "UNAVAILABLE"
    assert packet["publication_id"] is None
    assert packet["company_statuses"] == {}
    assert "PUBLICATION_CHAIN_UNAVAILABLE" in packet["blockers"]
    assert packet["chain_error"]
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["status"] == "UNAVAILABLE"
    assert daily["publication"]["publication_id"] is None
    assert client.get("/api/v1/decisions/600519").json()["publication"]["publication_id"] is None


def test_daily_public_packet_binds_the_registered_quote_bridge(tmp_path):
    client = _fixture(tmp_path)
    base = client.get("/api/v1/daily-public-packet").json()
    pointer = tmp_path / "config/current-quote-bridge.json"
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(json.dumps({
        "schema_version": "current-quote-bridge-v1", "action": "no_order",
        "registered_at": "2026-10-13T00:00:00+00:00",
        "quotes": {"600519": {"quote_bundle": "runtime/missing-bundle.json",
                              "quote_bundle_sha256": "0" * 64,
                              "research_package": "runtime/missing-package.json",
                              "research_package_sha256": "0" * 64,
                              "registered_at": "2026-10-13T00:00:00+00:00"}}}), encoding="utf-8")
    packet = client.get("/api/v1/daily-public-packet").json()
    # Registering a quote changes the packet identity even before any price is admitted.
    assert packet["publication_id"] != base["publication_id"]
    assert packet["quote_bridge"]["quotes_registered"] == 1
    bridge = packet["price_bridge_statuses"]["600519"]
    assert bridge["status"] == "NOT_ADMITTED"
    assert bridge["price_admitted"] is False
    roles = {item["role"]: item for item in packet["source_bindings"]}
    assert roles["quote_bridge_pointer"]["sha256_verified"] is True
    assert roles["quote_bundle:600519"]["present"] is False
    assert "SOURCE_BINDING_HASH_MISMATCH:quote_bundle:600519" in packet["blockers"]
    daily = client.get("/api/v1/daily-decisions").json()
    assert daily["publication"]["publication_id"] == packet["publication_id"]

