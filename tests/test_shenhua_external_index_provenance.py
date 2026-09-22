import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_external_index_provenance",
    ROOT / "scripts" / "build_shenhua_external_index_provenance.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_external_index_provenance_is_fail_closed(payload):
    assert payload["engineering_status"] == "external_index_provenance_package_complete"
    assert payload["status"] == "primary_provenance_archived_historical_operator_archives_membership_restricted"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_all_external_values_are_research_observations_not_model_inputs(payload):
    for section in (
        payload["ncei_launch_announcement"],
        payload["ncei_history_access"],
        payload["bspi_launch_notice"],
        payload["cctd_qhd_methodology"],
    ):
        assert section["model_input"] is None
    assert all(item["model_input"] is None for item in payload["ncei_live_page"]["observations"])


def test_ncei_operator_launch_provenance_is_pinned(payload):
    facts = payload["ncei_launch_announcement"]
    assert facts["operator"] == "全国煤炭交易中心有限公司"
    assert facts["document_date"] == "2021-12-31"
    assert facts["first_public_release_date"] == "2021-12-31"
    assert "独立" in facts["independence_declaration"]
    assert facts["contacts"]["email"] == "ncei@ncexc.com.cn"
    assert "010-52698888" in facts["contacts"]["telephone"]


def test_ncei_live_page_pins_two_dated_observations(payload):
    observations = {item["instrument"]: item for item in payload["ncei_live_page"]["observations"]}
    waterborne = observations["ncei_5500k_waterborne_index"]
    contract = observations["ncei_5500k_medium_long_term_contract_price"]

    assert waterborne["value"] == 758
    assert waterborne["publication_date"] == "2026-09-18"
    assert waterborne["month_on_month_change"] == "+3"
    assert contract["value"] == 704
    assert contract["unit"] == "cny_per_tonne"
    assert contract["publication_date"] == "2026-08-31"
    assert contract["month_on_month_change"] == "+3"


def test_history_archive_membership_restriction_is_recorded_without_data(payload):
    facts = payload["ncei_history_access"]
    assert facts["historical_rows_retrieved"] is False
    assert facts["membership_message"] == "成为缴费会员，查看历史指数数据"
    assert facts["export_requires_membership"] is True
    assert set(facts["visible_index_tabs"]) == {"NCEI", "BSPI", "CCTD", "CECI"}
    assert "/DzjyServer/api/queryQuotationIndexPage.json" in facts["api_endpoints_observed"]
    assert facts["direct_head_method_status"] == 405
    assert facts["client_reported_permission_states"]["1"] == "fully_paid_all_history_visible"


def test_bspi_primary_notice_pins_trial_schedule(payload):
    facts = payload["bspi_launch_notice"]
    assert facts["document_issuer"] == "国家发展改革委办公厅"
    assert facts["document_number"] == "办价格[2010]2399号"
    assert facts["publication_date"] == "2010-09-29"
    assert len(facts["port_universe"]) == 6
    assert "秦皇岛港" in facts["port_universe"]
    assert facts["reporting_period"] == "7天"
    assert facts["collection_window"] == "上周三到本周二"
    assert facts["release_schedule"] == "每周三下午15时"
    assert facts["initial_grades"] == [4500, 5000, 5500, 5800]
    assert facts["initial_data_collection_companies"] == 149


def test_cctd_methodology_pins_grades_prices_schedule_and_caveats(payload):
    facts = payload["cctd_qhd_methodology"]
    assert facts["cover_publication_period"] == "2022-10"
    assert facts["fifth_edition_revision_date"] == "2022-10-28"
    assert facts["delivery_location"].startswith("秦皇岛港及周边港口")
    assert facts["price_basis"] == "离岸平仓价格（含税）"
    assert facts["representative_grades_kcal_per_kg"] == [5500, 5000, 4500]
    assert facts["publication_schedule"]["composite_price"] == "weekly, Friday 17:00"
    assert facts["publication_schedule"]["spot_price_daily"] == "each workday 15:00"
    assert facts["publication_schedule"]["annual_long_term_price"] == "monthly, at month end for the next month"
    assert facts["daily_spot_publication_name"] == "CCTD环渤海动力煤现货参考价"
    assert facts["composite_weights_fifth_edition"]["annual_long_term_price"] == "80%"
    assert facts["subjective_judgment_allowed"] is True


def test_definition_breaks_and_boundaries_are_explicit(payload):
    findings = {item["id"]: item for item in payload["specific_findings"]}
    assert "operator_historical_archive_is_membership_gated" in findings
    assert "bspi_primary_notice_pins_weekly_trial_schedule" in findings
    assert "cctd_allows_disclosed_subjective_judgment" in findings
    assert any("different instruments" in item["fact"] for item in payload["definition_breaks"])
    assert any("758" in text or "704" in text for text in payload["forbidden_calculations"])
    assert any("secondary provenance" in text for text in payload["point_in_time_policy"])


def test_evidence_references_are_hash_bound(payload):
    expected = set(MODULE.RAW_SOURCES) | {"shenhua_price_cost_transport_bridge"}
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-external-index-provenance-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == set(MODULE.RAW_SOURCES)
    assert manifest["prior_evidence_sha256s"]["shenhua_price_cost_transport_bridge"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-2014-2025-price-cost-transport-bridge-latest.json").read_text(encoding="utf-8")
    )["sha256"]

    payload = json.loads(target.read_text(encoding="utf-8"))
    sources = {item["id"]: item for item in payload["evidence_refs"] if item["id"] in MODULE.RAW_SOURCES}
    for source_id, source_hash in manifest["source_sha256s"].items():
        assert sources[source_id]["sha256"] == source_hash
        assert _hash(ROOT / sources[source_id]["path"]) == source_hash
