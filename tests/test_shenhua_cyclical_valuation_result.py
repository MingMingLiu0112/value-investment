import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shenhua_cyclical_result_is_not_ready_without_mid_cycle_inputs():
    evidence = ROOT / "runtime/valuation-results/601088-cyclical-b3/evidence.json"
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    result = payload["result"]
    scope = ROOT / "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
    scope_payload = json.loads(scope.read_text(encoding="utf-8"))

    assert payload["version"] == "unified-company-valuation-result-v1"
    assert payload["model"] == "cyclical_normalized"
    assert payload["trade_approved"] is False
    assert result["symbol"] == "601088"
    assert result["model_type"] == "cyclical_normalized"
    assert result["status"] == "not_ready"
    assert (result["bear_value"], result["base_value"], result["bull_value"]) == (None, None, None)
    assert "financial_facts_not_verified" in result["blockers"]
    assert "cyclical_input_missing:resource_life_years" in result["blockers"]
    assert result["evidence_refs"]
    assert any(ref["path"] == "runtime/company-research/shenhua-cyclical-scope-20260921/evidence.json"
               and ref["sha256"] == hashlib.sha256(scope.read_bytes()).hexdigest()
               for ref in result["evidence_refs"])
    bridge = payload["price_bridge"]
    assert bridge["symbol"] == "601088"
    assert bridge["bridge_status"] == "PENDING_EXTERNAL_DATA"
    assert bridge["model_validity_status"] == "UNKNOWN"
    assert (bridge["current_price"], bridge["margin_to_bear"], bridge["margin_to_base"]) == (None, None, None)
    assert scope_payload["valuation_status"] == "VALUATION_NOT_READY"
