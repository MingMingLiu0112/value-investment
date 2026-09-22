import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_historical_2015_01_yield_observations",
    ROOT / "scripts" / "build_moutai_historical_2015_01_yield_observations.py",
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
        "historical_2015_01_yield_observation_package_complete"
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


def test_observations_are_pinned(payload):
    rows = {row["id"]: row for row in payload["observations"]}
    assert rows["boc_2014_12_16_10y_transaction"]["yield_percent"] == "3.75"
    assert rows["boc_2014_12_16_10y_transaction"]["availability_role"] == (
        "pre_decision_public_market_observation"
    )
    assert rows["chinabond_2015_01_05_10y_curve"]["yield_percent"] == "3.6251"
    assert rows["chinabond_2015_01_05_10y_curve"]["observation_date"] == "2015-01-05"
    assert rows["csj_2015_01_06_reported_10y_around"]["yield_percent"] == "3.63"
    assert rows["csj_2015_01_06_reported_10y_around"]["publication_date"] == "2015-01-06"
    assert rows["pbc_2015_01_last_trading_day_10y"]["yield_percent"] == "3.4966"
    assert rows["pbc_2015_01_last_trading_day_10y"]["availability_role"] == (
        "later_monthly_corroboration_only"
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


def test_observations_are_not_capital_cost_inputs(payload):
    assert payload["summary"]["registered_capital_cost_inputs"] == 0
    assert any("risk-free-rate input" in text for text in payload["forbidden_calculations"])
    assert any("cost of equity" in text for text in payload["forbidden_calculations"])
    assert any("beta" in text for text in payload["forbidden_calculations"])
    assert any("10-year government yield" in text for text in payload["not_proven"])
    assert any("time of the 2015-01-06" in text for text in payload["not_proven"])


def test_evidence_references_are_hash_bound(payload):
    expected = set(MODULE.RAW_SOURCES) | {
        "moutai_historical_executed_entry_receipt",
        "moutai_historical_1429_sovereign_observation_package",
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
            / "runtime/company-research/"
            "moutai-historical-2015-01-yield-observations-latest.json"
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
        "moutai_historical_1429_sovereign_observation_package": MODULE.PRIOR_COUPON_PACKAGE_HASH,
        "moutai_historical_chinabond_government_2014_candidate": MODULE.CHINABOND_CANDIDATE_HASH,
    }
