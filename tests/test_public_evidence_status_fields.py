"""Read-only API projection of bound adopted fields and recorded issues."""
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from test_public_evidence import transport, run
from value_investment_agent.application.research import public_evidence as mod
from value_investment_agent.presentation.web_api.app import create_app


def captured_files(root):
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("status GET must not acquire, extract, or write")


def configure_facts(monkeypatch, *, malformed=None):
    def enrich(root, source, points, **kwargs):
        adopted = [{"field_name": "debt_ratio"}] if source.symbol == "600519" else []
        reconciliation = {"issues": [] if adopted else ["MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS"]}
        if malformed:
            field, value = malformed
            if field == "reconciliation":
                reconciliation = value
            elif field == "issues":
                reconciliation["issues"] = value
            else:
                adopted = [{"field_name": value}]
        return dict(source_extraction=dict(identity=dict(source=vars(source))),
            adopted_points=adopted, official_balance_reconciliation=reconciliation,
            action="no_order", formal_eligibility=False, symbol=source.symbol, period=source.period,
            evaluation_at=datetime.now(timezone.utc).isoformat())
    monkeypatch.setattr(mod, "enrich_retained_company", enrich)


def test_http_projects_bound_fields_and_issues_without_inference_or_writes(tmp_path, transport, monkeypatch):
    configure_facts(monkeypatch)
    binding = run(tmp_path, allow_network=True)
    mod.publish_public_evidence(tmp_path, binding)
    monkeypatch.setattr(mod, "acquire_official_report", forbidden)
    monkeypatch.setattr(mod, "enrich_retained_company", forbidden)
    before = captured_files(tmp_path)
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/api/v1/public-evidence")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "VERIFIED"  # originals, not complete facts
    first, second = body["items"]
    assert first["adopted_fields"] == ["debt_ratio"]
    assert first["adopted_fact_count"] == 1
    assert first["fact_issues"] == []
    assert second["adopted_fields"] == []
    assert second["adopted_fact_count"] == 0
    assert second["fact_issues"] == ["MISSING_OR_AMBIGUOUS_PRINTED_BALANCE_TOTALS"]
    assert all(item["fetched_at"] == "2026-01-01T00:00:00+00:00" for item in body["items"])
    assert body["scope"] == "REQUESTED_REPORTS_ONLY"
    assert body["formal_eligibility"] is False
    assert body["strict_historical_pit"] is False
    assert captured_files(tmp_path) == before


def test_no_snapshot_returns_empty_fields_and_issues(tmp_path, transport):
    binding = run(tmp_path, allow_network=True, requests=[
        dict(symbol="600519", issuer_name="TEST_ONLY A", period="2026-06-30", exchange="SSE")])
    mod.publish_public_evidence(tmp_path, binding)
    row = mod.public_evidence_status(tmp_path)["items"][0]
    assert row["fact_issues"] == []
    assert row["adopted_fields"] == []
    assert row["fact_status"] == "UNSUPPORTED_INTERIM_FACT_PARSER"


def test_old_snapshot_without_reconciliation_keeps_compatibility(tmp_path, transport):
    binding = run(tmp_path, allow_network=True)
    mod.publish_public_evidence(tmp_path, binding)
    result = mod.public_evidence_status(tmp_path)
    assert result["status"] == "VERIFIED"
    assert all(row["fact_issues"] == [] and row["adopted_fields"] == [] for row in result["items"])


@pytest.mark.parametrize("field,value", [
    ("reconciliation", None), ("reconciliation", []),
    ("issues", None), ("issues", "NOT_A_LIST"), ("issues", [0]), ("issues", [{}]),
    ("field_name", None), ("field_name", 1), ("field_name", []),
])
def test_invalid_bound_projection_types_are_not_exposed(tmp_path, transport, monkeypatch, field, value):
    configure_facts(monkeypatch, malformed=(field, value))
    binding = run(tmp_path, allow_network=True)
    mod.publish_public_evidence(tmp_path, binding)
    before = captured_files(tmp_path)
    with TestClient(create_app(root=tmp_path)) as client:
        response = client.get("/api/v1/public-evidence")
    assert response.status_code == 200
    for row in response.json()["items"]:
        assert row["status"] == "CONFLICT"
        assert row["fact_status"] == "NOT_ADMITTED"
        assert row["adopted_fact_count"] == 0
        assert row["adopted_fields"] == []
        assert row["fact_issues"] == []
    assert captured_files(tmp_path) == before
