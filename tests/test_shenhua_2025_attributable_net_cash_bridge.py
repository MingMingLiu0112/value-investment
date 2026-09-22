import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_attributable_net_cash_bridge",
    ROOT / "scripts" / "build_shenhua_2025_attributable_net_cash_bridge.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_net_cash_bridge_is_source_bound_and_fail_closed():
    payload = MODULE.build()
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "attributable_net_cash_bridge_compiled_not_reviewed_or_approved"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    assert hashlib.sha256(source.read_bytes()).hexdigest().upper() == MODULE.SOURCE_HASH
    refs = payload["candidate_derivations"]["evidence_refs"]
    assert refs
    assert all(ref["sha256"] == MODULE.SOURCE_HASH for ref in refs)
    assert {ref["page"] for ref in refs} == {329, 331, 334, 335, 392, 462, 152}


def test_net_cash_candidates_are_transparent_and_not_model_inputs():
    payload = MODULE.build()
    derivations = payload["candidate_derivations"]

    assert derivations["consolidated_surface_net_cash"] == "57760.000"
    assert derivations["parent_surface_net_cash"] == "81701.000"
    assert derivations["parent_unrestricted_bank_cash_net_of_parent_debt"] == "30275.000"
    assert derivations["parent_cash_less_restricted_cash_net_of_parent_debt"] == "69815.000"
    assert derivations["conservative_attributable_interval"]["lower_bound"] == "30275.000"
    assert derivations["conservative_attributable_interval"]["upper_bound"] == "81701.000"
    assert derivations["model_input"] is None
    assert derivations["review_status"] == "not_reviewed_or_approved"


def test_post_balance_cash_events_are_observed_but_not_promoted():
    payload = MODULE.build()
    events = payload["post_balance_cash_events"]
    linked = events["linked_evidence"]

    assert events["status"] == "observed_but_current_net_cash_not_derivable"
    assert events["acquisition_cash_consideration_cny"] == "93518843500.00"
    assert events["placement_net_proceeds_cny"] == "19967492729.19"
    assert events["net_transaction_cash_effect_cny"].startswith("-73551350")
    source = ROOT / linked["path"]
    assert source.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest().upper() == linked["sha256"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2025-attributable-net-cash-bridge-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == MODULE.SOURCE_HASH
    linked = ROOT / "runtime/company-research/shenhua-2026-share-bridge-20260921/evidence.json"
    assert manifest["linked_share_bridge_sha256"] == hashlib.sha256(linked.read_bytes()).hexdigest().upper()
