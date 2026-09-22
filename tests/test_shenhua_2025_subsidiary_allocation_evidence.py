import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_subsidiary_allocation",
    ROOT / "scripts" / "build_shenhua_2025_subsidiary_allocation_evidence.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def test_subsidiary_allocation_package_is_source_bound_and_fail_closed():
    payload = MODULE.build()
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "subsidiary_allocation_boundary_audited_no_verified_allocation"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    assert _hash(source) == MODULE.SOURCE_HASH
    assert payload["evidence_refs"]
    assert all(ref["sha256"] == MODULE.SOURCE_HASH for ref in payload["evidence_refs"])
    assert {ref["page"] for ref in payload["evidence_refs"]} == {152, 338, 340, 428, 429, 439, 440}


def test_parent_legal_entity_is_not_treated_as_group_parent_operating_profit():
    payload = MODULE.build()

    assert payload["parent_entity_boundary"]["conclusion"] == (
        "parent_legal_entity_profit_is_not_group_parent_operating_profit"
    )
    assert payload["parent_entity_income_statement"][2025] == {
        "revenue_cny_millions": 74_055,
        "operating_profit_cny_millions": 64_233,
        "pretax_profit_cny_millions": 67_384,
        "income_tax_cny_millions": 5_024,
        "net_profit_cny_millions": 62_360,
        "investment_income_cny_millions": 44_607,
        "associate_investment_income_cny_millions": 3_224,
    }
    assert payload["parent_entity_boundary"]["observations"][
        "investment_income_share_of_parent_entity_operating_profit"
    ].startswith("0.694")


def test_named_subsidiaries_do_not_complete_the_minority_reconciliation():
    payload = MODULE.build()
    named = payload["named_non_wholly_owned_subsidiaries"]

    assert [item["name"] for item in named["subsidiaries"]] == [
        "准格尔能源",
        "宝日希勒能源",
        "定州发电",
        "朔黄铁路",
        "远海航运",
        "黄骅港务",
        "北电胜利能源",
    ]
    assert named["totals"] == {
        "named_minority_profit_cny_millions": 8_832,
        "named_dividends_to_minority_cny_millions": 16_787,
        "named_minority_equity_cny_millions": 45_723,
    }
    assert payload["reconciliation_gaps"]["minority_profit"] == {
        "named_subsidiaries_cny_millions": 8_832,
        "consolidated_cny_millions": 9_934,
        "residual_cny_millions": 1_102,
        "interpretation": "Named-subsidiary minority profit does not fully reconcile the consolidated minority profit.",
    }
    assert payload["reconciliation_gaps"]["minority_equity"] == {
        "named_subsidiaries_cny_millions": 45_723,
        "consolidated_cny_millions": 72_344,
        "residual_cny_millions": 26_621,
        "interpretation": "Named-subsidiary minority equity does not fully reconcile the consolidated minority-equity balance.",
    }


def test_allocations_never_become_model_inputs():
    payload = MODULE.build()
    profit = payload["model_derivations"]["normalized_parent_operating_profit"]
    net_cash = payload["model_derivations"]["attributable_net_cash"]

    assert profit["status"] == "cannot_derive_from_sub_legal_entity_or_named_subsidiary_disclosure"
    assert profit["candidate_values"] == {}
    assert profit["model_input"] is None
    assert "subsidiary-by-subsidiary" in profit["review_requirement"]

    assert net_cash["status"] == "outside_this_evidence_package"
    assert net_cash["candidate_values"] == {}
    assert net_cash["model_input"] is None


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2025-subsidiary-allocation-evidence-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = _hash(target)
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == MODULE.SOURCE_HASH
