import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from decimal import Decimal


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_finance_co_size_observation",
    ROOT / "scripts" / "build_midea_finance_co_size_observation.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_finance_company_observation_is_pinned_and_not_a_model_input():
    payload = MODULE.build_payload()
    pointer = ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"
    manifest = ROOT / pin["path"] / "manifest.json"

    assert evidence.resolve().is_relative_to(ROOT.resolve())
    assert _hash(evidence) == pin["sha256"]
    assert _hash(evidence) == json.loads(manifest.read_text(encoding="utf-8"))["evidence_sha256"]

    assert payload["status"] == "OBSERVATION_NOT_MODEL_INPUT"
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["registered_valuation_model"] is None
    assert payload["registered_valuation_inputs"] == {}
    assert payload["formal_fair_value"] is None
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False
    assert payload["live_eligible"] is False
    assert "bear_value" not in payload
    assert "base_value" not in payload
    assert "bull_value" not in payload
    assert "order" not in payload
    assert "position" not in payload


def test_finance_company_values_match_primary_pdf_text():
    payload = MODULE.build_payload()
    observations = {item["id"]: item for item in payload["observations"]}

    unaudited = observations["march_risk_assessment_unaudited"]["values"]
    audited = observations["august_related_transaction_announcement_audited"]["values"]

    assert unaudited["assets_cny"] == "44439992400"
    assert unaudited["liabilities_cny"] == "36595436500"
    assert unaudited["net_assets_cny"] == "7844555900"
    assert unaudited["revenue_cny"] == "599134600"
    assert unaudited["net_profit_cny"] == "410544900"

    assert audited["assets_cny"] == "44464130600"
    assert audited["liabilities_cny"] == "36605537300"
    assert audited["net_assets_cny"] == "7858593400"
    assert audited["revenue_cny"] == "599134600"
    assert audited["net_profit_cny"] == "410528300"

    assert observations["march_risk_assessment_unaudited"]["audit_status"] == "unaudited"
    assert observations["august_related_transaction_announcement_audited"]["audit_status"] == (
        "audited_as_disclosed_in_related_listed_company_announcement"
    )


def test_scale_candidates_do_not_unblock_fcff():
    payload = MODULE.build_payload()
    candidates = payload["derived_scale_candidates"]

    assert candidates["status"] == "CANDIDATE_NOT_MODEL_INPUT"
    assert Decimal(candidates["audited_net_profit_to_midea_consolidated_attributable_ordinary_net_profit"]).quantize(
        Decimal("0.0001")
    ) == Decimal("0.0093")
    assert Decimal(candidates["audited_net_assets_to_midea_consolidated_attributable_ordinary_equity"]).quantize(
        Decimal("0.0001")
    ) == Decimal("0.0352")
    assert "industrial_ebit" not in candidates
    assert "net_debt" not in candidates
    assert "wacc" not in candidates
    assert "ordinary_shares" not in candidates
    assert any(item.startswith("finance_company_book_equity") for item in payload["blockers"])


def test_source_refs_are_hash_addressable_and_page_scoped():
    payload = MODULE.build_payload()
    refs = {item["id"]: item for item in payload["evidence_refs"]}

    expected_ids = {
        "kelu_march_2026_finance_co_risk_assessment",
        "hekang_march_2026_finance_co_risk_assessment",
        "kelu_august_2026_finance_service_agreement_announcement",
    }
    assert set(refs) == expected_ids
    assert refs["kelu_august_2026_finance_service_agreement_announcement"]["pages"] == [2, 3]
    for ref in refs.values():
        source = ROOT / ref["path"]
        assert source.is_relative_to(ROOT / "runtime")
        assert _hash(source) == ref["sha256"]
        assert ref["url"].startswith("http")


def test_generated_pointer_and_manifest_match_script():
    pointer = json.loads(
        (ROOT / "runtime/company-research/midea-finance-co-2025-size-observation-latest.json").read_text(
            encoding="utf-8"
        )
    )
    target = ROOT / pointer["path"] / "evidence.json"
    manifest = json.loads((ROOT / pointer["path"] / "manifest.json").read_text(encoding="utf-8"))

    assert _hash(target) == pointer["sha256"] == manifest["evidence_sha256"]
    assert manifest["script_sha256"] == _hash(Path(MODULE.__file__))
    assert len(manifest["source_sha256s"]) == 3
