import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_public_index_history",
    ROOT / "scripts" / "build_shenhua_public_index_history.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_public_index_history_package_is_fail_closed(payload):
    assert payload["symbol"] == "601088"
    assert payload["engineering_status"] == "public_index_history_package_complete"
    assert payload["status"] == "public_cctd_historical_chart_series_archived_not_reconciled"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_all_series_rows_are_research_observations_not_model_inputs(payload):
    for series in payload["series"].values():
        assert series["model_input"] is None
        assert series["observations"]
        assert all(row["model_input"] is None for row in series["observations"])


def test_series_coverage_and_boundary_values_are_pinned(payload):
    series = payload["series"]
    assert series["bspi"]["observation_count"] == 802
    assert series["bspi"]["first_observation_date"] == "2010-06-29"
    assert series["bspi"]["last_observation_date"] == "2026-09-16"
    assert series["bspi"]["minimum_observation_value"] == "371"
    assert series["bspi"]["maximum_observation_value"] == "854"

    assert series["ctpi"]["observation_count"] == 130
    assert series["ctpi"]["first_observation_date"] == "2024-01-05"
    assert series["ctpi"]["last_observation_date"] == "2026-09-18"
    assert series["scpi"]["observation_count"] == 501
    assert series["scpi"]["first_observation_date"] == "2016-01-08"
    assert series["ospi"]["observation_count"] == 525
    assert series["ospi"]["first_observation_date"] == "2014-06-10"
    assert series["ybspi"]["observation_count"] == 379
    assert series["ybspi"]["first_observation_date"] == "2016-04-29"
    assert series["ybspi"]["last_observation_date"] == "2025-11-28"


def test_endpoint_payloads_match_the_archived_row_counts(payload):
    for source_id, series in payload["series"].items():
        path = MODULE.OUT / MODULE.RAW_SOURCES[source_id]["filename"]
        raw_rows = json.loads(path.read_text(encoding="utf-8"))
        assert len(raw_rows) == series["observation_count"]
        assert [row["name"] for row in raw_rows] == [
            row["observation_date"] for row in series["observations"]
        ]
        assert [row["age"] for row in raw_rows] == [
            row["value"] for row in series["observations"]
        ]


def test_page_and_endpoint_label_caveats_are_recorded(payload):
    findings = {item["id"]: item for item in payload["specific_findings"]}
    assert "five_public_chart_endpoints_are_source_addressable" in findings
    assert "ncei_cctd_ceci_historical_tables_remain_membership_gated" in findings
    assert "endpoint_and_page_labels_are_not_self_describing" in findings
    assert payload["series"]["ctpi"]["page_acronym_discrepancy"] == (
        "endpoint_uses_ctpi_but_page_table_uses_tcpi"
    )
    assert payload["series"]["ospi"]["displayed_unit"] == "未标注"
    assert any("separate instruments" in item for item in payload["definition_breaks"])
    assert any("never interpolated" in item for item in payload["point_in_time_policy"])
    assert any("use any endpoint value directly" in item.lower() for item in payload["forbidden_calculations"])


def test_evidence_references_are_hash_bound(payload):
    expected = {
        *(f"cctd_{source_id}_historical_endpoint" for source_id in MODULE.RAW_SOURCES),
        "cctd_index_center_page",
        "shenhua_external_index_provenance",
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-public-index-history-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == set(MODULE.RAW_SOURCES) | {"cctd_index_center_page"}
    assert manifest["prior_evidence_sha256s"]["shenhua_external_index_provenance"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json").read_text(encoding="utf-8")
    )["sha256"]

    payload = json.loads(target.read_text(encoding="utf-8"))
    for ref in payload["evidence_refs"]:
        assert _hash(ROOT / ref["path"]) == ref["sha256"]
