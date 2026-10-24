from copy import deepcopy

from value_investment_agent.application.portfolio.decision_logic import project_decision_logic


def test_bound_logic_preserves_reasons_and_conflicts_without_upgrading():
    plan = dict(symbol="600519", thesis="Cash generation", supporting_facts=["cash"],
        counter_evidence=["demand weakens"], thesis_invalidation=["cash deteriorates"],
        next_observation=["next filing"], bear="10", base="20", bull="30",
        scenario_validity={"confidence": "LOW"},
        source_bindings=[dict(path="facts.json", sha256="a" * 64)],
        research_analysis={"return_driver": "owner earnings"})
    before = deepcopy(plan)
    result = project_decision_logic(plan, outcome="UNASSESSABLE", blockers=["G3_PENDING"],
        entry_context={"original_thesis": "original", "consistency_status": "WEAKENED"})
    assert result["decision_action"] == "UNASSESSABLE"
    assert result["blockers"] == ["G3_PENDING"]
    assert result["counter_evidence"] == ["demand weakens"]
    assert result["original_thesis"] == "original"
    assert result["confidence"] == "LOW"
    assert result["broker_execution_permission"] is False
    assert plan == before
    result["source_bindings"][0]["path"] = "changed"
    assert plan == before


def test_unbound_or_bad_hash_never_labels_prose_verified():
    for sources in ([], [{"path": "facts.json", "sha256": "z" * 64}]):
        card = project_decision_logic({"thesis": "unverified", "source_bindings": sources},
            outcome="UNASSESSABLE", blockers=["SOURCE_MISSING"])
        assert card["source_status"] == "NOT_SOURCE_BOUND"
        assert card["thesis"] is None
        assert card["source_bindings"] == []


def test_logic_fingerprint_changes_with_evidence_and_reason():
    plan = {"symbol": "600519", "source_bindings": [{"path": "facts", "sha256": "a" * 64}]}
    first = project_decision_logic(plan, outcome="BUY", blockers=[])
    second = project_decision_logic(plan, outcome="UNASSESSABLE", blockers=["STALE"])
    assert first["content_sha256"] != second["content_sha256"]
    assert first["action"] == second["action"] == "no_order"


def test_all_owned_entry_theses_are_projected_from_actual_context_contract():
    from types import SimpleNamespace
    entries = [dict(entry_thesis=SimpleNamespace(entry_id=name, thesis='reason-' + name),
        investment_consistency_review=SimpleNamespace(status=status))
        for name, status in [('first', 'CONSISTENT'), ('second', 'WEAKENED')]]
    plan = {'symbol': '600519', 'source_bindings': [{'path': 'facts', 'sha256': 'a' * 64}]}
    card = project_decision_logic(plan, outcome='ADD', blockers=[], entry_context={'entry_contexts': entries})
    assert card['original_thesis'] == [
        dict(entry_id='first', thesis='reason-first', consistency_status='CONSISTENT'),
        dict(entry_id='second', thesis='reason-second', consistency_status='WEAKENED')]
