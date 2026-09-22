import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_bspi_point_in_time_publications",
    ROOT / "scripts" / "build_shenhua_bspi_point_in_time_publications.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def payload():
    return MODULE.build()


def test_package_is_fail_closed(payload):
    assert payload["symbol"] == "601088"
    assert payload["engineering_status"] == "bspi_point_in_time_publications_package_complete"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_cyclical_facts_operating_inputs"] == []


def test_source_layers_are_not_confused(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    assert [rows[year]["source_role"] for year in (2014, 2015, 2016)] == [
        "cctd_hosted_republication",
        "cctd_hosted_republication",
        "cctd_hosted_republication",
    ]
    assert [rows[year]["source_role"] for year in (2017, 2020, 2021, 2022)] == [
        "cqcoal_operator_direct_page",
        "secondary_attributed_republication",
        "cqcoal_operator_direct_page",
        "cqcoal_operator_direct_page",
    ]
    assert payload["summary"]["operator_primary_publication_pages"] == 3
    assert payload["summary"]["cctd_hosted_republication_pages"] == 3
    assert payload["summary"]["attributed_secondary_republication_pages"] == 4
    assert payload["summary"]["independent_2020_secondary_republication_pages"] == 2
    assert payload["scope"]["operator_primary_article_missing_years"] == [2018, 2019, 2020]
    assert [rows[year]["operator_primary_page_found"] for year in (2017, 2021, 2022)] == [True, True, True]
    assert rows[2020]["operator_primary_page_found"] is False
    assert rows[2020]["additional_secondary_source_ids"] == ["ehang_attributed_bspi_2020_page_585"]
    assert rows[2020]["secondary_attributed_republication_count"] == 2


def test_publication_values_periods_and_page_timestamps(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    expected = {
        2014: (525, "2014-12-17", "2014-12-23", "2014-12-24T15:48:00+08:00"),
        2015: (372, "2015-12-23", "2015-12-29", "2016-01-04T13:55:32+08:00"),
        2016: (593, "2016-12-21", "2016-12-27", "2016-12-28T15:01:05+08:00"),
        2017: (577, "2017-12-20", "2017-12-26", "2017-12-27T15:08:00+08:00"),
        2020: (585, "2020-12-23", "2020-12-29", "2020-12-31T10:43:44+08:00"),
        2021: (737, "2021-12-22", "2021-12-28", "2021-12-29T15:00:00+08:00"),
        2022: (734, "2022-12-21", "2022-12-27", "2022-12-28T15:07:00+08:00"),
    }
    for year, (value, start, end, page_time) in expected.items():
        row = rows[year]
        assert row["cited_value"] == value
        assert row["reporting_period_start"] == start
        assert row["reporting_period_end"] == end
        assert row["page_publication_timestamp"] == page_time
        assert row["model_input"] is None


def test_calendar_final_publication_scope(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    assert rows[2014]["calendar_year_final_publication"] is False
    assert [year for year in (2015, 2016, 2017, 2020, 2021, 2022)
            if not rows[year]["calendar_year_final_publication"]] == []
    assert payload["summary"]["calendar_year_final_publication_years"] == [
        2015, 2016, 2017, 2020, 2021, 2022
    ]


def test_2014_and_2017_alignment_issues_remain_explicit(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    assert rows[2014]["endpoint_last_observation"] == {"date": "2014-12-31", "value": 523}
    assert rows[2014]["annual_report_period_end_value"] == 525
    assert rows[2014]["date_alignment_status"] == "mismatch_flagged"
    assert "not a calendar-year-final publication" in rows[2014]["mismatch_notes"][0]

    assert rows[2017]["cited_value"] == 577
    assert rows[2017]["annual_report_period_end_value"] == 578
    assert rows[2017]["endpoint_last_observation"] == {"date": "2017-12-27", "value": 577}
    assert rows[2017]["date_alignment_status"] == "annual_report_value_mismatch"
    assert "2017-11-08" in rows[2017]["mismatch_notes"][0]
    assert any("578" in text for text in payload["forbidden_calculations"])


def test_missing_direct_pages_are_not_interpolated(payload):
    assert payload["summary"]["operator_primary_article_missing_years"] == [2018, 2019, 2020]
    assert payload["summary"]["operator_primary_article_missing_years_remain_unresolved"] is True
    assert payload["summary"]["missing_years_interpolated"] is False
    assert payload["scope"]["not_collected_years"] == [2023, 2024, 2025]
    assert any("never interpolated" in text for text in payload["point_in_time_policy"])
    assert any("interpolation" in text for text in payload["forbidden_calculations"])
    rows = {item["year"]: item for item in payload["publications"]}
    assert "China5e" not in rows[2020]["source_role"]
    assert "E-Hang" not in rows[2020]["source_role"]
    assert "2020-12-23 to 2020-12-29" in rows[2020]["provenance_notes"][0]
    assert "China5e and E-Hang" in rows[2020]["provenance_notes"][0]
    assert "operator original" in rows[2020]["provenance_notes"][0]


def test_corroborating_publication_roles_and_cei_limits(payload):
    rows = {item["id"]: item for item in payload["corroborating_publications"]}
    assert payload["summary"]["secondary_corroborating_pages"] == 10
    assert payload["summary"]["non_attributed_corroborating_pages"] == 2
    assert payload["scope"]["secondary_corroboration_only_years"] == [2018, 2019]
    assert all(item["model_input"] is None for item in rows.values())

    assert rows["bspi_2018_coalchina_attributed_569"]["provenance_class"] == "industry_association_attributed_republication"
    assert rows["bspi_2018_coalchina_attributed_569"]["explicit_operator_attribution"] is True
    assert rows["bspi_2018_hebeidaily_operator_group_news_569"]["provenance_class"] == "print_news_operator_group_report"
    assert rows["bspi_2018_hebeidaily_operator_group_news_569"]["source_date"] == "2018-12-31"
    assert rows["bspi_2019_china5e_attributed_551"]["provenance_class"] == "secondary_attributed_republication"
    assert rows["bspi_2019_cwestc_attributed_551"]["explicit_operator_attribution"] is True
    assert rows["bspi_2020_cwestc_attributed_585"]["source_date"] == "2020-12-31"
    assert rows["bspi_2020_in_en_attributed_585"]["source_date"] == "2020-12-30"
    assert sum(item["explicit_operator_attribution"] for item in rows.values()) == 8

    cei = rows["bspi_2020_cei_secondary_listing_585"]
    assert cei["cited_value"] == 585
    assert cei["explicit_operator_attribution"] is False
    assert cei["reporting_period_start"] is None
    assert cei["reporting_period_end"] is None
    assert cei["page_publication_timestamp"] is None
    assert cei["article_path_fragment"] == MODULE.CEI_ARTICLE_PATH_FRAGMENT
    assert cei["access_scope"] == "title_date_article_path_only"
    assert cei["full_article_access"] == "LOGIN_GATED"
    assert "login-gated" in cei["notes"]
    assert "no full-text attributed republication" in cei["notes"]
    assert "秦皇岛煤炭网" not in cei["notes"]


def test_publisher_and_original_availability_are_explicit(payload):
    source = MODULE.source_record("cei_bspi_2020_page_585")
    assert source["listing_scope"] == "title_date_article_path_only"
    assert source["full_article_access"] == "LOGIN_GATED"

    publisher = payload["publisher_provenance"]
    assert publisher["bspi_operator"]["operator_name"] == "秦皇岛海运煤炭交易市场有限公司"
    assert publisher["bspi_operator"]["historical_platform_domains"][0]["probe_status"] == "DNS_NOT_RESOLVED"
    assert publisher["ncei_operator"]["history_access"] == "membership_gated"

    availability = payload["original_availability"]
    assert availability["status"] == "ORIGINAL_NOT_EVIDENCED_FOR_MISSING_YEARS"
    assert availability["bspi_missing_years"] == [2018, 2019, 2020]
    assert availability["ncei_missing_years"] == [2023, 2024, 2025]
    assert {item["id"] for item in availability["findings"]} == {
        "bspi_2018_operator_original_not_evidenced",
        "bspi_2019_operator_original_not_evidenced",
        "bspi_2020_operator_original_not_evidenced",
        "ncei_2023_2025_original_publication_records_not_evidenced",
    }


def test_evidence_references_are_hash_bound(payload):
    expected = set(MODULE.RAW_SOURCES) | {
        "cctd_bspi_historical_endpoint",
        "shenhua_bspi_annual_report_reconciliation",
        "shenhua_external_index_provenance",
        "shenhua_price_cost_transport_bridge",
        "shenhua_public_index_history",
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]
    assert MODULE.RAW_SOURCES["ehang_attributed_bspi_2020_page_585"]["url"] == "http://www.e-hang.net/wap/detail/post-43328.html"


def test_additional_secondary_corroboration_pages_are_content_bound(payload):
    expectations = {
        "coalchina_attributed_bspi_2018_page_569": (
            "gbk",
            ("2018年12月19日至2018年12月25日", "环渤海动力煤价格指数报收于569元/吨", "秦皇岛煤炭网"),
        ),
        "hebeidaily_operator_group_news_2018_bspi_569": (
            "utf-8",
            ("2018年12月19日至2018年12月25日", "环渤海动力煤价格指数报收于569元/吨", "河北港口集团秦皇岛海运煤炭交易市场发布"),
        ),
        "china5e_attributed_bspi_2019_page_551": (
            "utf-8",
            ("2019年12月18日至2019年12月24日", "环渤海动力煤价格指数报收于551元/吨", "秦皇岛煤炭网"),
        ),
        "cwestc_attributed_bspi_2019_page_551": (
            "utf-8",
            ("2019年12月18日至2019年12月24日", "环渤海动力煤价格指数报收于551元/吨", "来源：秦皇岛煤炭网"),
        ),
        "cwestc_attributed_bspi_2020_page_585": (
            "utf-8",
            ("2020年12月23日至2020年12月29日", "环渤海动力煤价格指数报收于585元/吨", "来源：秦皇岛煤炭网"),
        ),
        "in_en_attributed_bspi_2020_page_585": (
            "utf-8",
            ("2020年12月23日至2020年12月29日", "环渤海动力煤价格指数报收于585元/吨", "来源：秦皇岛煤炭网"),
        ),
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    rows = {item["source_id"]: item for item in payload["corroborating_publications"]}
    for source_id, (encoding, fragments) in expectations.items():
        source = refs[source_id]
        text = (ROOT / source["path"]).read_text(encoding=encoding)
        normalized = MODULE.stripped_text(text)
        assert all(fragment in normalized for fragment in fragments)
        assert _hash(ROOT / source["path"]) == source["sha256"]
        assert rows[source_id]["model_input"] is None


def test_2020_attributed_publication_pages_are_explicitly_bound(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    row = rows[2020]
    expected_ids = {
        "china5e_attributed_bspi_2020_page_585",
        "ehang_attributed_bspi_2020_page_585",
    }
    assert {row["source_id"], *row["additional_secondary_source_ids"]} == expected_ids
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    for source_id in expected_ids:
        source = refs[source_id]
        text = (ROOT / source["path"]).read_text(encoding="utf-8")
        assert "2020年12月23日至2020年12月29日" in text
        assert "585元/吨" in text
        assert "秦皇岛煤炭网" in text
    assert any("still cannot become an operator original" in text
               for text in payload["definition_breaks"])


def test_operator_article_metadata_and_search_gap_are_pinned(payload):
    rows = {item["year"]: item for item in payload["publications"]}
    expected_operator = {
        2017: (80997, "2017-12-27 15:08", "2022-10-31 13:52:19", "秦皇岛煤炭网"),
        2021: (110846, "2021-12-29 15:00", "2022-10-31 13:52:19", "秦皇岛煤炭网"),
        2022: (114105, "2022-12-28 15:07", "2023-01-05 16:40:37", "秦皇岛煤炭网"),
    }
    for year, expected in expected_operator.items():
        row = rows[year]
        assert (row["operator_article_id"], row["operator_publish_time"],
                row["operator_api_update_time"], row["operator_source_label"]) == expected
        assert row["source_id"].startswith("cqcoal_operator_api_")
        assert row["secondary_source_id"].startswith("china5e_attributed_")

    assert rows[2020]["operator_article_id"] is None
    assert rows[2020]["operator_publish_time"] is None
    assert any("missing 2020 final-period operator article" in text
               for text in payload["point_in_time_policy"])
    assert any(item["id"] == "operator_primary_article_missing_for_2020_final_period"
               for item in payload["specific_findings"])


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-bspi-point-in-time-publications-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == set(MODULE.RAW_SOURCES) | {
        "cctd_bspi_historical_endpoint"
    }
    assert manifest["prior_evidence_sha256s"]["shenhua_bspi_annual_report_reconciliation"] == json.loads(
        (ROOT / "runtime/company-research/shenhua-bspi-annual-report-reconciliation-latest.json").read_text(encoding="utf-8")
    )["sha256"]
