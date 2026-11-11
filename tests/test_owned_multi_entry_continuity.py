"""TEST_ONLY cross-date fills; per-entry read review is not aggregate authority."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from test_personal_entry_thesis import case, AS_OF, _confirm_registered_entry  # noqa: F401
from test_advisory_decision_recommendation_v3 import _consistency
from test_owned_held_actions import inputs
from value_investment_agent.application.portfolio import personal_entry_thesis as personal
from value_investment_agent.application.portfolio import private_portfolio_service as ledger
from value_investment_agent.application.portfolio import held_continuity as held
from value_investment_agent.application.decision.build_advisory_decision_recommendation_v3 import derive_recommendation_rule_inputs
from value_investment_agent.domain.decision.recommendation_rules import evaluate_recommendation_action
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_artifacts import ResearchArtifactIdentity


@pytest.fixture
def multi(case, tmp_path, monkeypatch):
    args, service, _ = case
    _confirm_registered_entry(args, service, tmp_path)
    clock = [AS_OF]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            stamp = cls.fromisoformat(clock[0].isoformat())
            return stamp if tz is None else stamp.astimezone(tz)

    from value_investment_agent import research_artifact_repository as repositories
    monkeypatch.setattr(ledger, "datetime", Clock)
    monkeypatch.setattr(repositories, "datetime", Clock)
    service = ledger.PrivatePortfolioService(service.journal, clock=Clock.now)
    _, draft = service.prepare_fill(dict(idempotency_key="TEST_ONLY-later-add", expected_revision=4,
        fill=dict(transaction_id="TEST_ONLY-later-add", side="BUY", sleeve="CORE_VALUE",
            symbol="300364", exchange="SZSE", quantity="100", price_cny="17", fees_cny="1",
            trade_date="2026-10-15", next_sell_session="2026-10-16", trading_unit="100")))
    _, bought = service.confirm_fill(dict(idempotency_key="TEST_ONLY-later-add-confirm", expected_revision=5,
        prepared_record_sha256=draft, confirmed_at=AS_OF.isoformat(), confirmation_note="TEST_ONLY manual ADD fill"))
    repository = args["repository"]

    def save(value):
        kind, payload = artifact_payload(value)
        return repository.save_object(value, identity=ResearchArtifactIdentity(scope_type="security",
            scope_key="300364", artifact_type=kind, schema_version=payload["schema_version"],
            as_of=getattr(value, "as_of", value.entry_date if hasattr(value, "entry_date") else clock[0].date()),
            available_at=clock[0]), run_id="TEST_ONLY-cross-date")

    original = personal.decode_artifact(personal.ARTIFACT_ENTRY_THESIS_SNAPSHOT,
        args["entry_artifact"].envelope.payload_object())
    added = save(replace(original, entry_id="TEST_ONLY-added-entry", entry_date=AS_OF.date(),
        confirmed_at=AS_OF, entry_price=Decimal("17"), thesis="TEST_ONLY independent additional-entry rationale"))
    review = save(replace(_consistency("CONSISTENT"), symbol="300364", as_of=AS_OF.date(),
        entry_id="TEST_ONLY-added-entry"))
    personal.PersonalEntryThesisService(service.journal, repository=repository).confirm(
        dict(idempotency_key="TEST_ONLY-bind-add", expected_revision=6, fill_record_sha256=bought,
            binding_mode="CONTEMPORANEOUS", read_and_confirmed=True,
            confirmation_note="TEST_ONLY additional original", entry_artifact_id=added.artifact_id,
            consistency_artifact_id=review.artifact_id),
        repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=Clock.now())

    def context():
        return personal.owned_entry_context(records=service.records(), symbol="300364", sleeve="CORE_VALUE",
            authenticated_subject="LOCAL_OPERATOR", as_of=clock[0])

    seen = []

    def test_only_source_adapter(root, *, context, plan, now, **kwargs):
        # Test the orchestration with real artifact/PIT and action rules. This
        # adapter does not stand in for signed production research admission.
        seen.append(context["entry_artifact"].artifact_id)
        current = personal.resolve_current_entry_consistency(root, entry_artifact=context["entry_artifact"],
            as_of=now, repository=repository)
        rules = derive_recommendation_rule_inputs(entry_thesis=current["entry_thesis"],
            consistency_review=current["investment_consistency_review"], base_positive=True,
            model_validity_status="VALID", event_review_current=True)
        selected = evaluate_recommendation_action(rules)
        return selected.action, list(selected.blockers), dict(namespace="TEST_ONLY_SOURCE_ADAPTER",
            current_consistency_status=current["investment_consistency_review"].status,
            current_consistency_review=current["consistency_ref"], reason_codes=list(selected.reason_codes))

    monkeypatch.setattr(held, "_evaluate_owned_single_entry", test_only_source_adapter)
    return dict(args=args, service=service, repository=repository, context=context, clock=clock,
        save=save, root=tmp_path, seen=seen, original=original, added=added)


def evaluate(multi, context=None):
    context = context or multi["context"]()
    args = inputs(context, "HOLD")
    args["sleeve_position"].update(quantity="200", sellable_quantity="100")
    args["advisory_provider"] = lambda: held.evaluate_owned_held_advisory(multi["root"],
        context=context, plan=args["plan"], now=multi["clock"][0])
    return held.owned_held_action(**args)


def test_cross_date_add_replays_every_original_and_per_entry_hold_without_aggregate_authority(multi):
    before = multi["service"].journal.path.read_bytes()
    context = multi["context"]()
    assert context["ownership_verified"] and not context["advisory_dependencies_valid"]
    assert context["held_quantity"] == "200" and len(context["entry_contexts"]) == 2
    assert {part["entry_thesis"].entry_date.isoformat() for part in context["entry_contexts"]} == {"2026-10-14", "2026-10-15"}
    result = evaluate(multi)
    assert result["entry_review_status"] == "CONSISTENT_ENTRY_ACTIONS"
    assert [row["research_action"] for row in result["entry_reviews"]] == ["HOLD", "HOLD"]
    assert set(multi["seen"]) == {multi["args"]["entry_artifact"].artifact_id, multi["added"].artifact_id}
    assert multi["original"].thesis in result["original_thesis"]
    assert "TEST_ONLY independent additional-entry rationale" in result["original_thesis"]
    assert "2026-10-14" in result["decision_reason"] and "2026-10-15" in result["decision_reason"]
    assert result["decision_action"] == "UNASSESSABLE" and result["review_quantity"] is None
    assert result["multi_entry_sell_confirmation_required"] is True
    assert result["formal_eligibility"] is result["personal_sell_permission"] is False
    assert all(row["review_quantity"] is None and row["formal_eligibility"] is False for row in result["entry_reviews"])
    assert result["action"] == "no_order" and result["advisory"]["aggregate_authority"] == "NONE"
    restarted = ledger.PrivatePortfolioService(ledger.PrivateJournal(multi["service"].journal.path))
    replay = personal.owned_entry_context(records=restarted.records(), symbol="300364", sleeve="CORE_VALUE",
        authenticated_subject="LOCAL_OPERATOR", as_of=AS_OF)
    assert personal.owned_entry_display(replay) == personal.owned_entry_display(context)
    assert restarted.journal.path.read_bytes() == before


@pytest.mark.parametrize("state,expected", [("BROKEN", "SELL_CANDIDATE"), ("WEAKENED", "TRIM_CANDIDATE"),
                                            ("FULFILLED", "ADD_CANDIDATE")])
def test_old_original_conflict_cannot_be_hidden_by_latest_add_entry(multi, state, expected):
    multi["clock"][0] += timedelta(seconds=1)
    multi["save"](replace(_consistency(state), symbol="300364", as_of=AS_OF.date(),
        entry_id=multi["original"].entry_id, review_id="TEST_ONLY-current-"+state))
    result = evaluate(multi)
    assert result["entry_review_status"] == "CONFLICTING_ENTRY_ACTIONS"
    assert [row["research_action"] for row in result["entry_reviews"]] == [expected, "HOLD"]
    assert result["decision_action"] == "UNASSESSABLE" and result["review_quantity"] is None
    assert not result["personal_sell_permission"] and not result["formal_eligibility"]


def test_missing_current_review_retains_original_and_marks_incomplete(multi, monkeypatch):
    repository = multi["repository"]
    versions = repository.list_versions
    monkeypatch.setattr(repository, "list_versions", lambda *a, **k: [value for value in versions(*a, **k)
        if value.envelope.payload_object()["entry_id"] != multi["original"].entry_id])
    result = evaluate(multi)
    assert result["entry_review_status"] == "INCOMPLETE"
    assert len(result["entry_reviews"]) == 2 and result["entry_reviews"][0]["blockers"]
    assert result["entry_reviews"][1]["research_action"] == "HOLD"
    assert result["decision_action"] == "UNASSESSABLE"


def test_multi_entry_review_rejects_a_different_strategy_plan(multi):
    with pytest.raises(ValueError, match="scope mismatch"):
        held.evaluate_owned_held_advisory(multi["root"], context=multi["context"](),
            plan=dict(symbol="300364", schema_version="price-action-plan-independent-v2",
                strategy="HOTSPOT_SATELLITE"), now=multi["clock"][0])


@pytest.mark.parametrize("fault", ["drop_entry", "duplicate", "quantity", "sleeve", "revision", "drop_binding"])
def test_partial_or_cross_scope_group_cannot_be_reviewed_as_complete(multi, fault):
    context = deepcopy(multi["context"]())
    parts = context["entry_contexts"]
    if fault == "drop_entry":
        parts.pop()
    elif fault == "duplicate":
        parts[1] = deepcopy(parts[0])
    elif fault == "quantity":
        parts[0]["held_quantity"] = "99"
    elif fault == "sleeve":
        parts[0]["sleeve"] = "HOTSPOT_SATELLITE"
    elif fault == "revision":
        parts[0]["journal_revision"] -= 1
    else:
        parts[0]["bindings"] = []
    result = evaluate(multi, context)
    assert result["decision_action"] == "UNASSESSABLE" and result["review_quantity"] is None
    assert any(code.startswith("HELD_PER_ENTRY_REVIEW_INVALID:") for code in result["blockers"])
