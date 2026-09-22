import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_ifrs_subsidiary_tax_review",
    ROOT / "scripts" / "build_shenhua_2025_ifrs_subsidiary_tax_review.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_ifrs_review_is_source_bound_and_fail_closed():
    payload = MODULE.build()

    assert payload["status"] == "ifrs_12_sub_company_summary_reviewed_no_verified_pretax_tax_allocation"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    assert _hash(MODULE.SOURCE) == MODULE.SOURCE_HASH
    assert MODULE.SOURCE.stat().st_size == MODULE.SOURCE_BYTES
    assert payload["evidence_refs"]
    assert all(ref["sha256"] == MODULE.SOURCE_HASH for ref in payload["evidence_refs"])
    assert {ref["page"] for ref in payload["evidence_refs"]} == {67, 240, 294, 295, 358, 359, 360, 361, 371}


def test_ifrs_12_named_subsidiary_facts_and_reconciliation_are_pinned():
    payload = MODULE.build()
    named = payload["named_subsidiaries_ifrs_12_2025"]
    reconciliation = payload["named_subsidiary_reconciliation"]

    assert [item["name"] for item in named] == [
        "Zhunge'er Energy",
        "China Energy Baorixile Energy Industrial Co., Ltd.",
        "Dingzhou Power",
        "China Energy Shuohuang Railway Development Co., Ltd.",
        "China Energy Yuanhai Shipping Co., Ltd.",
        "China Energy Huanghua Harbour Administration Co., Ltd.",
        "Beidian Shengli Company",
    ]
    assert [item["nci_holding_pct"] for item in named] == [42, 43, 59, 47, 49, 30, 37]
    assert [item["profit_allocated_to_nci_cny_millions"] for item in named] == [2_870, 1_311, 436, 3_105, 100, 522, 750]
    assert [item["revenue_cny_millions"] for item in named] == [13_016, 8_183, 4_423, 23_061, 3_989, 5_388, 6_677]
    assert [item["profit_and_total_comprehensive_income_cny_millions"] for item in named] == [6_675, 2_938, 733, 6_594, 205, 1_711, 2_005]

    assert reconciliation == {
        "named_profit_allocated_to_nci_cny_millions": 9_094,
        "consolidated_minority_profit_cny_millions": 10_285,
        "profit_residual_cny_millions": 1_191,
        "named_accumulated_nci_cny_millions": 46_274,
        "consolidated_minority_equity_cny_millions": 72_891,
        "equity_residual_cny_millions": 26_617,
        "note": "The equity residual equals the disclosed individually immaterial subsidiaries amount, but the profit residual is not allocated by the filing.",
    }


def test_consolidated_tax_heterogeneity_blocks_proportional_allocation():
    payload = MODULE.build()

    assert payload["consolidated_ifrs_2025_facts"] == {
        "profit_before_income_tax_cny_millions": 81_062,
        "income_tax_expense_cny_millions": 16_559,
        "profit_for_year_cny_millions": 64_503,
        "minority_profit_cny_millions": 10_285,
        "minority_equity_cny_millions": 72_891,
        "effective_tax_rate_pct": "20.427573956",
    }
    assert payload["tax_reconciliation_observations"]["different_tax_rates_effect_cny_millions"] == -4_228
    assert payload["partial_major_subsidiary_operating_profit"]["entries"] == [
        {"name": "Shendong Coal", "revenue_cny_millions": 67_918, "operating_profit_cny_millions": 9_253},
        {"name": "Shuohuang Railway", "revenue_cny_millions": 23_061, "operating_profit_cny_millions": 9_073},
        {"name": "Zhunge'er Energy", "revenue_cny_millions": 13_016, "operating_profit_cny_millions": 7_822},
    ]


def test_no_subsidiary_pretax_or_tax_line_was_found():
    payload = MODULE.build()
    absence = payload["absence_check"]

    assert absence["pages"] == [358, 359, 360, 361]
    assert absence["absent_line_items"] == ["Profit before income tax", "Income tax expense", "Profit before tax"]
    assert "No subsidiary-level pre-tax or tax line item" in absence["conclusion"]


def test_no_value_enters_the_cyclical_model():
    payload = MODULE.build()
    profit = payload["model_derivations"]["normalized_parent_operating_profit"]
    net_cash = payload["model_derivations"]["attributable_net_cash"]

    assert profit["status"] == "cannot_derive_from_ifrs_12_or_partial_major_subsidiary_disclosure"
    assert profit["candidate_values"] == {}
    assert profit["model_input"] is None
    assert "audited statutory allocation" in profit["review_requirement"]
    assert net_cash["candidate_values"] == {}
    assert net_cash["model_input"] is None


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2025-ifrs-subsidiary-tax-review-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == MODULE.SOURCE_HASH
    assert manifest["source_bytes"] == MODULE.SOURCE_BYTES
