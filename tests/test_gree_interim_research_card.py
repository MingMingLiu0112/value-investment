import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "gree_interim_research_card", ROOT / "scripts" / "build_gree_interim_research_card.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_gree_r0_card_is_hash_bound_and_not_a_trade_output():
    card = MODULE.build()
    assert card["issuer_filing"]["source_id"] == "cninfo:1225515004"
    assert card["issuer_filing"]["raw_file_hash"] == MODULE.PDF_SHA256
    assert card["issuer_disclosed_facts_cny"]["cash_and_cash_equivalents"] == "35699553592.36"
    assert card["issuer_disclosed_facts_cny"]["issuer_disclosed_interest_bearing_liabilities"] == "84635545410.92"
    assert card["research_status"] == "priority_for_shallow_research"
    assert card["formal_fair_value"] is None
    assert card["valuation_approved"] is False
    assert card["trade_approved"] is False
