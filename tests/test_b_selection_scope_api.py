"""TEST_ONLY scope projection; retained actual-source acceptance is in runtime."""
import pytest
from fastapi.testclient import TestClient
from test_value_candidate_selection import source_package, _run_pointer
from value_investment_agent.application.discovery import value_candidate_selection as selection
from value_investment_agent.presentation.web_api.app import create_app

@pytest.mark.parametrize("complete", [False, True])
def test_verified_scan_scope_survives_selector_and_api(source_package, monkeypatch, complete):
    root, binding, _, _ = source_package
    pointer, _ = _run_pointer(root, binding, mode="READ_ONLY")
    before = pointer.read_bytes()
    original = selection.current_scan_details
    scope = dict(status="COMPLETE" if complete else "PARTIAL", scope="TEST_ONLY",
        all_a_complete=complete, covered_venues=["SSE", "SZSE"],
        failed_venues=[] if complete else ["BSE"])
    def verified(*args):
        scan = original(*args)
        assert scan["status"] == "SOURCE_REVALIDATED"
        scan["summary"]["screening_scope"] = scope
        return scan
    monkeypatch.setattr(selection, "current_scan_details", verified)
    response = TestClient(create_app(root)).get("/api/v1/strategy-selection")
    assert response.status_code == 200
    value = response.json()["value"]
    assert value["screening_scope"] == scope
    assert value["formal_eligibility"] is False
    assert pointer.read_bytes() == before

def test_damaged_manifest_never_claims_verified_market_scope(source_package):
    root, binding, _, _ = source_package
    _run_pointer(root, binding, mode="READ_ONLY")
    (root / binding["path"]).write_text("{}", encoding="utf-8")
    response = TestClient(create_app(root)).get("/api/v1/strategy-selection")
    value = response.json()["value"]
    assert response.status_code == 200
    assert value["items"] == []
    assert value["pagination"]["total"] is None
    assert "screening_scope" not in value
