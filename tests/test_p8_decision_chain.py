from value_investment_agent.application.product.daily_public_packet import decision_chain_view
from value_investment_agent.application.product.daily_public_packet import _company_entry
import hashlib


def test_public_chain_separates_evidence_data_human_and_private():
    entry = {
        "symbol": "600887", "name": "Example", "research_version": "v1",
        "pending_actions": [
            {"code": "CLOSE", "actor": "EXTERNAL_DATA", "label": "Acquire close"},
            {"code": "MODEL", "actor": "EVIDENCE", "label": "Establish normalization"},
            {"code": "G3", "actor": "HUMAN", "label": "Authorized review"},
        ],
        "registered_research": {"missing_inputs": ["Clean surplus reconciliation"], "evidence": []},
        "price_bridge": {"quote_date": "2026-10-15", "current_price": "28.10", "price_admitted": False},
    }
    result = decision_chain_view(entry, {"entry_trigger_price": "10.00"})
    assert [gap["classification"] for gap in result["gaps"]] == ["DATA", "EVIDENCE", "HUMAN", "EVIDENCE"]
    assert result["private_qualification"]["status"] == "AUTHENTICATED_VIEW_REQUIRED"
    assert result["price_conditions"]["entry_trigger_price"] == "10.00"
    assert result["formal_eligibility"] is False
    assert result["market_integrity"]["price_admitted"] is False
    assert result["action"] == "no_order"


def test_unknown_task_owner_never_becomes_human_authorization():
    result = decision_chain_view({"symbol": "000333", "name": "Example",
        "pending_actions": [{"code": "UNKNOWN", "actor": "UNREGISTERED", "label": "Investigate"}]}, {})
    assert result["gaps"][0]["classification"] == "EVIDENCE"
    assert result["formal_eligibility"] is False


def test_research_conclusion_requires_all_source_hashes_and_never_grants_eligibility():
    entry = {"symbol": "600887", "name": "Example", "registered_research": {
        "status": "CURRENT_RELIABLE_FAIR_VALUE_NOT_ESTABLISHED",
        "summary": "Stress conditions are not fair value",
        "evidence": [{"sha256_verified": True}],
    }}
    result = decision_chain_view(entry, {})
    assert result["research_conclusion"]["summary"] == "Stress conditions are not fair value"
    assert result["formal_eligibility"] is False
    entry["registered_research"]["evidence"].append({"sha256_verified": False})
    result = decision_chain_view(entry, {})
    assert result["research_conclusion"]["summary"] is None
    assert result["research_conclusion"]["evidence_verified"] is False


def test_bound_existing_dossier_is_visible_without_claiming_missing_engineering_or_valuation(tmp_path):
    source = tmp_path / "dossier.json"
    source.write_text('{"scope":"research_only"}', encoding="utf-8")
    registered = {"missing_inputs": ["Normalized earnings"], "evidence": [
        {"path": "dossier.json", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}
    args = dict(root=tmp_path, symbol="000651", name="Example", company=None,
                opportunity=None, queue_entry=None, decision=None, bridge=None,
                explanation=None, explanation_broken=False, registry_entry=registered)
    entry = _company_entry(**args)
    assert "VALUATION_NOT_ADMITTED" in entry["blockers"]
    assert any(task["code"] == "REGISTERED_RESEARCH_NOT_FORMALLY_ADMITTED"
               and task["actor"] == "EVIDENCE" for task in entry["pending_actions"])
    source.write_text("changed", encoding="utf-8")
    entry = _company_entry(**args)
    assert "REGISTERED_EVIDENCE_CHANGED" in entry["blockers"]
    assert any(task["code"] == "BIND_CURRENT_RESEARCH_ASSESSMENT"
               and task["actor"] == "ENGINEERING" for task in entry["pending_actions"])
