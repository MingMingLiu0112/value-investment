"""Input adaptation tests; synthetic sources remain TEST_ONLY, opt-in real replay separate."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from test_value_evidence_enrichment_v1 import source, balance_inputs, income_inputs, NOW
from test_income_source_correlation_integration import correlated_income
from value_investment_agent.application.research import retained_income_financial_input as adapter
from value_investment_agent.infrastructure.screening.financial_export_v2 import load_retained_financial_export
from value_investment_agent.application.research.value_evidence_enrichment_v1 import consume_retained_enrichment


def bound(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.fixture
def inputs(tmp_path, correlated_income):
    official, _, _, secondary, _ = correlated_income
    base = tmp_path/"runtime/base.json"
    # A provider observation is preserved unchanged, not promoted by this adapter.
    observation = dict(symbol=official.symbol, field_name="net_income", period_label="2025-12-31",
        data_point_id="TEST_ONLY-E1", value="24.00", unit="CNY", validation_status="unverified",
        created_at="2026-09-01T00:00:00+00:00", available_at="2026-09-01T00:00:00+00:00",
        metadata=dict(automatic_cross_source_verification=False))
    payload = dict(points=[observation], generated_at="2026-10-20T00:00:00+00:00")
    base.write_text(json.dumps(payload), encoding="utf-8")
    return dict(root=tmp_path, base_export_binding=bound(tmp_path, base),
        sources=[dict(official=official.__dict__, secondary=secondary)],
        output_dir=tmp_path/"runtime/new-input", evaluation_at=NOW)


def test_real_consumers_accept_adapter_without_new_assurance_flags(inputs):
    original = (inputs["root"]/inputs["base_export_binding"]["path"]).read_bytes()
    result = adapter.build_retained_income_financial_export(**inputs)
    json.dumps(result, allow_nan=False)
    assert result["annual_evidence_adoption"]["added_accepted_official_rows"] == 4
    payload_path = inputs["root"]/result["financial_export_binding"]["path"]
    payload = json.loads(payload_path.read_bytes())
    assert payload["points"] == json.loads(original)["points"]
    points, _ = load_retained_financial_export(payload_path, evaluation_at=NOW)
    enriched, _ = consume_retained_enrichment(inputs["root"], points, payload["value_enrichment_sources"], evaluation_at=NOW)
    assert {p["field_name"] for p in enriched if p.get("metadata", {}).get("derivation_formula")} == {"revenue_yoy", "net_income_yoy"}
    change = result["quality_changes"]["600887"]
    assert str(change["before"]["coverage_ratio"]) == "0.0000"
    assert str(change["after"]["coverage_ratio"]) == "0.2222"
    assert change["after"]["total_score"] is None
    assert set(change["accepted_quality_fields"]) == {"revenue_yoy", "net_income_yoy"}
    assert all(p["field_name"] in {"revenue", "net_income"} for p in payload["annual_points"])
    assert all(p["metadata"]["economic_approval"] is False for p in payload["annual_points"])
    assert not result["economic_approval"] and not result["formal_eligibility"] and not result["current_registry_updated"]
    assert result["historical_pit_admission"] == "NOT_ADMITTED"
    assert (inputs["root"]/inputs["base_export_binding"]["path"]).read_bytes() == original


@pytest.mark.parametrize("damage", ["base_hash", "missing_secondary", "secondary_hash", "wrong_period", "late",
    "duplicate_source", "base_conflict", "declaration_conflict", "saved_facts", "outside", "naive"])
def test_invalid_inputs_fail_closed_without_export(inputs, damage):
    root = inputs["root"]
    base = root/inputs["base_export_binding"]["path"]
    if damage == "base_hash": inputs["base_export_binding"]["sha256"] = "0"*64
    elif damage == "missing_secondary": (root/inputs["sources"][0]["secondary"]["path"]).unlink()
    elif damage == "secondary_hash": inputs["sources"][0]["secondary"]["sha256"] = "0"*64
    elif damage == "wrong_period": inputs["sources"][0]["official"] = dict(inputs["sources"][0]["official"], period="2025-06-30")
    elif damage == "late": inputs["evaluation_at"] = NOW-timedelta(days=40)
    elif damage == "duplicate_source": inputs["sources"] *= 2
    elif damage in {"base_conflict", "declaration_conflict"}:
        payload = json.loads(base.read_bytes())
        if damage == "base_conflict": payload["points"][0]["value"] = "999.00"
        else:
            payload["value_enrichment_sources"] = [dict(inputs["sources"][0]["official"], sha256="0"*64)]
        base.write_text(json.dumps(payload), encoding="utf-8")
        inputs["base_export_binding"] = bound(root, base)
    elif damage == "saved_facts": inputs["sources"] = [dict(verified=True, points=[])]
    elif damage == "outside": inputs["base_export_binding"]["path"] = "../outside.json"
    elif damage == "naive": inputs["evaluation_at"] = NOW.replace(tzinfo=None)
    with pytest.raises((ValueError, FileNotFoundError)):
        adapter.build_retained_income_financial_export(**inputs)
    assert not inputs["output_dir"].exists()


def test_existing_output_cannot_be_overwritten(inputs):
    adapter.build_retained_income_financial_export(**inputs)
    with pytest.raises(FileExistsError): adapter.build_retained_income_financial_export(**inputs)


def test_future_base_observation_preserved_but_cannot_select_quality_period(inputs):
    root = inputs["root"]
    base = root/inputs["base_export_binding"]["path"]
    payload = json.loads(base.read_bytes())
    future = dict(symbol="600887", field_name="revenue_yoy", period_label="2026-12-31",
        data_point_id="TEST_ONLY_FUTURE", value="999", unit="percent", validation_status="unverified",
        available_at=(NOW+timedelta(days=365)).isoformat(), metadata={})
    payload["points"].append(future)
    base.write_text(json.dumps(payload), encoding="utf-8")
    inputs["base_export_binding"] = bound(root, base)
    result = adapter.build_retained_income_financial_export(**inputs)
    assert result["quality_changes"]["600887"]["after"]["coverage_ratio"] == "0.2222"
    assert result["quality_changes"]["600887"]["after"]["calculation_details"]["period"] == "2025-12-31"
    output = json.loads((root/result["financial_export_binding"]["path"]).read_bytes())
    assert future in output["points"]
    assert all(p["data_point_id"] != future["data_point_id"] for p in result["research_input_points"])


def test_base_drift_after_correlation_rejected(inputs, monkeypatch):
    original = adapter.correlate_income_inputs
    def drift(*args, **kwargs):
        points = original(*args, **kwargs)
        base = inputs["root"]/inputs["base_export_binding"]["path"]
        base.write_bytes(base.read_bytes()+b" ")
        return points
    monkeypatch.setattr(adapter, "correlate_income_inputs", drift)
    with pytest.raises(ValueError, match="hash mismatch"):
        adapter.build_retained_income_financial_export(**inputs)
    assert not inputs["output_dir"].exists()


def test_selected_source_drift_during_consumption_rejected(inputs, monkeypatch):
    original = adapter.consume_retained_enrichment
    def drift(*args, **kwargs):
        result = original(*args, **kwargs)
        path = inputs["root"]/inputs["sources"][0]["secondary"]["path"]
        path.write_bytes(path.read_bytes()+b" ")
        return result
    monkeypatch.setattr(adapter, "consume_retained_enrichment", drift)
    with pytest.raises(ValueError, match="hash mismatch"):
        adapter.build_retained_income_financial_export(**inputs)


def test_real_retained_income_sources_into_existing_export_and_quality(tmp_path):
    raw = os.environ.get("RETAINED_INCOME_REAL_ROOT")
    if not raw:
        pytest.skip("Explicit real retained comparison root required; no collection")
    public = Path(raw)
    report = json.loads((public/"runtime/income-source-comparison/20261024T083440789422Z/comparison-result.json").read_bytes())
    sources = []
    for item in report["companies"].values():
        official, secondary = item["official_source"], item["secondary"]
        for ref in (official, secondary, secondary["receipt"]):
            origin = public/ref["path"]
            assert hashlib.sha256(origin.read_bytes()).hexdigest() == ref["sha256"]
            target = tmp_path/ref["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
        sources.append(dict(official=official, secondary=secondary))
    base = tmp_path/"runtime/empty-research-base.json"
    base.write_text(json.dumps(dict(points=[], generated_at=datetime.now(timezone.utc).isoformat())), encoding="utf-8")
    result = adapter.build_retained_income_financial_export(root=tmp_path, base_export_binding=bound(tmp_path, base),
        sources=sources, output_dir=tmp_path/"runtime/adapted", evaluation_at=datetime.now(timezone.utc))
    assert result["annual_evidence_adoption"]["added_accepted_official_rows"] == 8
    assert len(result["research_input_points"]) == 12
    for symbol in ("600519", "600887"):
        change = result["quality_changes"][symbol]
        assert str(change["after"]["coverage_ratio"]) == "0.2222"
        assert change["after"]["total_score"] is None
        assert set(change["accepted_quality_fields"]) == {"revenue_yoy", "net_income_yoy"}
