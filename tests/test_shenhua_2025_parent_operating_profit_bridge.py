import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "shenhua_parent_operating_profit_bridge",
    ROOT / "scripts" / "build_shenhua_2025_parent_operating_profit_bridge.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_profit_bridge_is_source_bound_and_fail_closed():
    payload = MODULE.build()
    source = ROOT / "runtime/shenhua-2025-official.pdf"

    assert payload["status"] == "parent_operating_profit_pro_forma_compiled_not_reviewed_or_approved"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["simulation_eligible"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False

    assert hashlib.sha256(source.read_bytes()).hexdigest().upper() == MODULE.SOURCE_HASH
    refs = [
        ref
        for year in payload["derivation"]["candidate_values"].values()
        for ref in year["evidence_refs"]
    ]
    assert refs
    assert all(ref["sha256"] == MODULE.SOURCE_HASH for ref in refs)
    assert all(ref["page"] in {337, 338, 429} for ref in refs)


def test_profit_bridge_arithmetic_records_explicit_pro_forma():
    payload = MODULE.build()
    values = payload["derivation"]["candidate_values"]

    assert values["2025"]["parent_attributable_pretax_operating_profit_candidate"].startswith("63580.757")
    assert values["2024"]["parent_attributable_pretax_operating_profit_candidate"].startswith("73631.585")
    assert values["2025"]["minority_net_profit"] == "9934.000"
    assert values["2025"]["parent_net_profit"] == "52849.000"
    assert values["2025"]["effective_tax_rate"].startswith("0.208674")
    assert values["2025"]["parent_net_share"].startswith("0.841772")

    assert payload["derivation"]["model_input"] is None
    assert payload["derivation"]["review_status"] == "not_reviewed_or_approved"
    assert "subsidiary-by-subsidiary" in payload["derivation"]["review_requirements"][0]
    assert "current-year audited-cycle observations" in payload["normalization_observation"]


def test_pointer_and_manifest_match_generated_evidence():
    pointer = json.loads(
        (ROOT / "runtime/company-research/shenhua-2025-parent-operating-profit-bridge-latest.json").read_text(encoding="utf-8")
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads(
        (ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8")
    )

    assert target.is_relative_to(ROOT.resolve())
    evidence_hash = hashlib.sha256(target.read_bytes()).hexdigest().upper()
    assert evidence_hash == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["source_sha256"] == MODULE.SOURCE_HASH
