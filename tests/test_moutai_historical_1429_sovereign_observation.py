import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_1429_sovereign_observation",
    ROOT / "scripts" / "build_moutai_historical_1429_sovereign_observation.py",
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
    assert payload["symbol"] == "600519"
    assert payload["engineering_status"] == (
        "historical_1429_sovereign_coupon_observation_package_complete"
    )
    assert payload["r1_status"] == "not_passed"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["financial_scope_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["replay_eligible"] is False
    assert payload["strategy_backtest_complete"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert payload["registered_capital_cost_inputs"] == []


def test_instrument_terms_are_pinned(payload):
    instrument = payload["instrument"]
    assert instrument["issue_name"] == "2014年记账式附息（二十九期）国债"
    assert instrument["exchange_codes"] == {"szse": "101429", "sse": "019429"}
    assert instrument["tenor_years"] == 10
    assert instrument["coupon_percent"] == "3.77"
    assert instrument["issue_amount_cny_billion"] == "282.4"
    assert instrument["interest_start_date"] == "2014-12-18"
    assert instrument["listing_date"] == "2014-12-24"
    assert instrument["maturity_date"] == "2024-12-18"


def test_decision_window_publications_are_separated(payload):
    rows = {row["id"]: row for row in payload["publications"]}
    assert rows["mof_2014_no_91_primary"]["publication_date"] == "2014-12-17"
    assert rows["mof_2014_no_91_primary"]["published_before_decision_date"] is True
    assert rows["szse_2014_12_22_listing_notice"]["publication_date"] == "2014-12-22"
    assert rows["szse_2014_12_22_listing_notice"]["published_before_decision_date"] is True

    assert rows["mof_2015_no_5_later_corroboration"]["publication_date"] == "2015-01-28"
    assert rows["mof_2015_no_5_later_corroboration"]["published_before_decision_date"] is False
    assert rows["mof_2015_no_5_later_corroboration"]["availability_role"] == (
        "later_independent_corroboration_only"
    )
    assert rows["sse_2014_factbook_bond_record"]["publication_date"] == "2015-annual-publication"
    assert rows["sse_2014_factbook_bond_record"]["published_before_decision_date"] is False
    assert rows["sse_2014_factbook_bond_record"]["availability_role"] == (
        "later_independent_corroboration_only"
    )


def test_decision_window_is_anchored_to_existing_replay(payload):
    window = payload["decision_window"]
    assert window["first_archived_fill_date"] == "2015-01-06"
    assert window["first_archived_fill_price_cny"] == 200.0
    ref = window["evidence_ref"]
    assert ref["id"] == "moutai_historical_executed_entry_receipt"
    assert Path(ref["path"]).as_posix() == (
        "runtime/strategy-validation/moutai-capital-entry-20260920T092929069969Z/result.json"
    )
    assert _hash(ROOT / ref["path"]) == ref["sha256"]


def test_coupon_is_not_a_capital_cost_input(payload):
    assert payload["summary"]["registered_capital_cost_inputs"] == 0
    assert any("coupon" in text for text in payload["definition_breaks"])
    assert any("risk-free rate" in text for text in payload["forbidden_calculations"])
    assert any("cost of equity" in text for text in payload["forbidden_calculations"])
    assert any("coupon predates" in text for text in payload["forbidden_calculations"])
    assert any("risk-free" in text for text in payload["not_proven"])
    assert any("full Moutai R1" in text for text in payload["not_proven"])


def test_evidence_references_are_hash_bound(payload):
    expected = set(MODULE.RAW_SOURCES) | {
        "moutai_historical_executed_entry_receipt",
        "moutai_historical_chinabond_government_2014_candidate",
    }
    refs = {item["id"]: item for item in payload["evidence_refs"]}
    assert set(refs) == expected
    for item in refs.values():
        target = ROOT / item["path"]
        assert target.exists()
        assert _hash(target) == item["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (
            ROOT
            / "runtime/company-research/moutai-historical-1429-sovereign-observation-latest.json"
        ).read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert set(manifest["source_sha256s"]) == set(MODULE.RAW_SOURCES)
    assert manifest["prior_evidence_sha256s"] == {
        "moutai_historical_executed_entry_receipt": MODULE.DECISION_WINDOW_HASH,
        "moutai_historical_chinabond_government_2014_candidate": MODULE.CHINABOND_CANDIDATE_HASH,
    }
