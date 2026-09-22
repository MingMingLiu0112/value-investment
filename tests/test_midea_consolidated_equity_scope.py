import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "midea_consolidated_equity_scope",
    ROOT / "scripts" / "build_midea_consolidated_equity_scope.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_midea_consolidated_equity_scope_is_factual_and_not_registered():
    payload = MODULE.build_payload()
    source = MODULE.SOURCE

    assert payload["symbol"] == "000333"
    assert payload["financial_scope_approved"] is False
    assert payload["valuation_status"] == "VALUATION_NOT_READY"
    assert payload["registered_valuation_inputs"] == {}
    assert payload["consolidated_equity"]["attributable_ordinary_equity_cny"] == "223221305000"
    assert payload["consolidated_equity"]["minority_equity_cny"] == "13202918000"
    assert payload["consolidated_income"]["attributable_ordinary_net_profit_cny"] == "43945411000"
    assert payload["consolidated_equity"]["treasury_share_count"] is None
    assert payload["financial_business_visible_items"]["finance_company_direct_ownership_pct"] == "95"
    assert payload["alternative_route_candidate"]["status"] == "CANDIDATE_NOT_REGISTERED"
    assert {ref["page"] for ref in payload["evidence_refs"] if "page" in ref} == {137, 143, 185, 246}
    assert {page for ref in payload["evidence_refs"] for page in ref.get("pages", [])} == {133, 135, 136}
    assert all(ref["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
               for ref in payload["evidence_refs"])
