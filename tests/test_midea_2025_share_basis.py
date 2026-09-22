import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_2025_share_basis", ROOT / "scripts" / "build_midea_2025_share_basis.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_midea_2025_share_basis_separates_accounting_eps_scope_from_valuation_denominator():
    payload = MODULE.build_payload()
    source = ROOT / "runtime/midea-2025-official.pdf"
    pointer = ROOT / "runtime/company-research/midea-2025-share-basis-latest.json"
    pin = json.loads(pointer.read_text(encoding="utf-8"))
    evidence = ROOT / pin["path"] / "evidence.json"
    assert hashlib.sha256(evidence.read_bytes()).hexdigest() == pin["sha256"]

    assert payload["symbol"] == "000333"
    assert payload["status"] == "accounting_share_facts_disclosed_not_valuation_denominator"
    assert payload["facts"]["year_end_2025"] == {
        "issued_total_shares": 7597145346,
        "issued_a_shares": 6946296846,
        "issued_h_shares": 650848500,
        "a_plus_h_reconciles_to_total": True,
        "p143_total_and_p219_movement_agree": True,
        "rounding_note": (
            "Page 219 reports the movement table in thousands of shares and rounds "
            "the H-share class to 650,849 thousand. The exact page-143 class total is "
            "650,848,500 shares; both are retained, and no H-share amount is inferred."
        ),
    }
    eps = payload["facts"]["fy2025_accounting_eps"]
    assert eps["weighted_average_ordinary_shares_thousand"] == 7559265
    assert eps["diluted_weighted_average_ordinary_shares_thousand"] == 7608132
    assert eps["parent_ordinary_net_profit_cny_thousand"] == 43829974
    assert eps["basic_eps_cny"] == "5.80"
    assert eps["diluted_eps_cny"] == "5.76"
    assert payload["facts"]["treasury_stock_2025"]["year_end_share_count"] is None
    assert payload["derived_scope"]["fy2025_weighted_denominator_can_verify_reported_eps"] is True
    assert payload["derived_scope"]["fy2025_weighted_denominator_is_current_valuation_share_basis"] is False
    assert payload["registered_valuation_inputs"]["ordinary_shares"] is None
    assert payload["share_basis_approved"] is False
    assert payload["valuation_approved"] is False
    assert payload["trade_approved"] is False
    assert {ref["page"] for ref in payload["evidence_refs"]} == {143, 219, 220, 223, 231}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
    assert all(Path(ref["path"]) == source.relative_to(ROOT) for ref in payload["evidence_refs"])


def test_midea_2025_share_basis_rejects_the_year_end_total_as_a_weighted_denominator():
    payload = MODULE.build_payload()
    blocked = payload["blocked_uses"]
    assert any("issued total" in item for item in blocked)
    assert any("FY2025 weighted denominator" in item for item in blocked)
    assert any("treasury-stock carrying amount" in item for item in blocked)
