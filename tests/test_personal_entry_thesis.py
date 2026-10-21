"""TEST_ONLY preparation contract; no private production paths or permission grants."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
import hashlib

import pytest

from test_advisory_decision_recommendation_v3 import _entry, _consistency
from value_investment_agent.application.portfolio import personal_entry_thesis as personal
from value_investment_agent.application.portfolio import private_portfolio_service as journal_module
from value_investment_agent.domain.portfolio.dual_sleeve_records import canonical_bytes
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent import research_artifact_repository as repository_module
from value_investment_agent.research_artifacts import ResearchArtifactIdentity
from value_investment_agent.investment_decision import ENTRY_TYPE_SIMULATED, ENTRY_TYPE_RECONSTRUCTED

STAMP = datetime.fromisoformat("2026-10-14T16:00:00+08:00")
AS_OF = datetime.fromisoformat("2026-10-15T20:00:00+08:00")


class FrozenClock(datetime):
    @classmethod
    def now(cls, tz=None):
        result = cls.fromisoformat(STAMP.isoformat())
        return result if tz is None else result.astimezone(tz)


@pytest.fixture
def case(tmp_path, monkeypatch):
    monkeypatch.setattr(journal_module, "datetime", FrozenClock)
    monkeypatch.setattr(repository_module, "datetime", FrozenClock)
    service = journal_module.PrivatePortfolioService(
        journal_module.PrivateJournal(tmp_path / "TEST_ONLY-journal.jsonl"))
    service.initialize({"idempotency_key": "init", "expected_revision": 0,
        "account_scope": "TEST_ONLY_PERSONAL_ENTRY", "as_of": "2026-10-13", "cash_cny": "10000",
        "holdings": [], "sleeve_allocations": {}, "policy": {},
        "confirmed_at": "2026-10-13T16:00:00+08:00", "confirmation_note": "TEST_ONLY baseline"})
    _, digest = service.prepare_fill({"idempotency_key": "buy", "expected_revision": 1,
        "fill": {"transaction_id": "TEST_ONLY-original-buy", "side": "BUY", "sleeve": "CORE_VALUE",
            "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "18",
            "fees_cny": "1", "trade_date": "2026-10-14", "next_sell_session": "2026-10-15",
            "trading_unit": "100"}})
    service.confirm_fill({"idempotency_key": "confirm", "expected_revision": 2,
        "prepared_record_sha256": digest, "confirmed_at": STAMP.isoformat(),
        "confirmation_note": "TEST_ONLY confirmed BUY"})
    repository = repository_module.InMemoryResearchArtifactRepository()
    entry = replace(_entry(), symbol="300364", entry_date=date(2026, 10, 14), confirmed_at=STAMP)
    consistency = replace(_consistency("CONSISTENT"), symbol="300364", as_of=date(2026, 10, 14))

    def save(value, available=STAMP):
        kind, payload = artifact_payload(value)
        return repository.save_object(value, identity=ResearchArtifactIdentity(
            scope_type="security", scope_key=value.symbol, artifact_type=kind,
            schema_version=payload["schema_version"], as_of=date(2026, 10, 14), available_at=available),
            run_id="TEST_ONLY-personal-entry")

    entry_artifact, consistency_artifact = save(entry), save(consistency)
    records = service.records()
    binding = {"schema_version": personal.BINDING_SCHEMA, "account_scope": "TEST_ONLY_PERSONAL_ENTRY",
        "journal_revision": len(records), "journal_tip_sha256": records[-1]["record_sha256"],
        "fill_record_sha256": records[-1]["record_sha256"], "transaction_id": "TEST_ONLY-original-buy",
        "symbol": "300364", "exchange": "SZSE", "sleeve": "CORE_VALUE",
        "entry_ref": personal._ref(entry_artifact), "consistency_ref": personal._ref(consistency_artifact),
        "confirmation": {"subject": "TEST_ONLY-user", "confirmed_at": AS_OF.isoformat(),
            "note": "TEST_ONLY explicit original thesis binding", "explicit_original_entry_binding": True},
        "action": "no_order"}
    monkeypatch.setattr(journal_module, "datetime", datetime)
    return dict(records=records, account_scope="TEST_ONLY_PERSONAL_ENTRY", authenticated_subject="TEST_ONLY-user",
        expected_revision=len(records), binding_candidate=binding, entry_artifact=entry_artifact,
        consistency_artifact=consistency_artifact, repository=repository, as_of=AS_OF), service, save


def test_strict_positive_contract_reuses_domain_objects_without_granting_ownership(case):
    args, service, _ = case
    before = service.journal.path.read_bytes()
    inputs = deepcopy(args["binding_candidate"])
    result = personal.validate_personal_entry_thesis_binding_contract(**args)
    assert result["status"] == "CONTRACT_VALIDATED_NOT_PERSISTED"
    assert result["entry_thesis"].entry_id == result["investment_consistency_review"].entry_id
    assert not result["ownership_verified"] and not result["formal_eligibility"]
    assert not result["personal_sell_permission"] and result["position_guidance"] is None
    assert result["action"] == "no_order"
    assert service.journal.path.read_bytes() == before
    assert args["binding_candidate"] == inputs


@pytest.mark.parametrize("field,value", [
    ("account_scope", "other-account"), ("journal_revision", 2), ("journal_revision", True),
    ("journal_tip_sha256", "0" * 64), ("fill_record_sha256", "0" * 64),
    ("transaction_id", "other-buy"), ("symbol", "600519"), ("exchange", "SSE"),
    ("sleeve", "HOTSPOT_SATELLITE"), ("action", "BUY"),
])
def test_binding_cannot_cross_account_revision_fill_or_strategy(case, field, value):
    args, _, _ = case
    args["binding_candidate"][field] = value
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


@pytest.mark.parametrize("field,value", [
    ("subject", "other-user"), ("explicit_original_entry_binding", False),
    ("explicit_original_entry_binding", "true"), ("note", ""),
    ("confirmed_at", "2026-10-16T20:00:00+08:00"),
    ("confirmed_at", "2026-10-14T15:00:00+08:00"),
    ("confirmed_at", "2026-10-15T20:00:00"),
])
def test_confirmation_requires_explicit_subject_and_valid_time(case, field, value):
    args, _, _ = case
    args["binding_candidate"]["confirmation"][field] = value
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


@pytest.mark.parametrize("role", ["entry", "consistency"])
@pytest.mark.parametrize("field,value", [
    ("artifact_id", "public-example"), ("payload_sha256", "0" * 64),
    ("available_at", "2026-10-14T15:59:59+08:00"),
])
def test_exact_registered_artifact_references_required(case, role, field, value):
    args, _, _ = case
    args["binding_candidate"][role + "_ref"][field] = value
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


@pytest.mark.parametrize("fault", ["simulated", "reconstructed", "foreign_symbol", "wrong_price",
    "wrong_date", "future_confirmation", "future_available", "review_entry", "review_future"])
def test_domain_and_temporal_mismatches_rejected(case, fault):
    args, _, save = case
    entry = personal.decode_artifact("entry_thesis_snapshot", args["entry_artifact"].envelope.payload_object())
    review = personal.decode_artifact("investment_consistency_review", args["consistency_artifact"].envelope.payload_object())
    if fault == "simulated":
        entry = replace(entry, entry_type=ENTRY_TYPE_SIMULATED)
    elif fault == "reconstructed":
        entry = replace(entry, entry_type=ENTRY_TYPE_RECONSTRUCTED, reconstructed_note="TEST_ONLY retrospective")
    elif fault == "foreign_symbol":
        entry = replace(entry, symbol="600519")
    elif fault == "wrong_price":
        entry = replace(entry, entry_price=entry.entry_price + 1)
    elif fault == "wrong_date":
        entry = replace(entry, entry_date=date(2026, 10, 13))
    elif fault == "future_confirmation":
        entry = replace(entry, confirmed_at=AS_OF)
    elif fault == "review_entry":
        review = replace(review, entry_id="other-entry")
    elif fault == "review_future":
        review = replace(review, as_of=date(2026, 10, 16))
    args["entry_artifact"] = save(entry, AS_OF if fault == "future_available" else STAMP)
    args["consistency_artifact"] = save(review)
    args["binding_candidate"]["entry_ref"] = personal._ref(args["entry_artifact"])
    args["binding_candidate"]["consistency_ref"] = personal._ref(args["consistency_artifact"])
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


def test_tampered_journal_hash_rejected(case):
    args, _, _ = case
    args["records"][2]["body"]["fill"]["price_cny"] = "19"
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


def test_sell_record_with_valid_hash_cannot_be_original_buy(case):
    args, _, _ = case
    record = args["records"][-1]
    record["body"]["fill"]["side"] = "SELL"
    record["record_sha256"] = hashlib.sha256(canonical_bytes(
        {k: v for k, v in record.items() if k != "record_sha256"})).hexdigest()
    args["binding_candidate"]["fill_record_sha256"] = record["record_sha256"]
    args["binding_candidate"]["journal_tip_sha256"] = record["record_sha256"]
    with pytest.raises(ValueError, match="BUY"):
        personal.validate_personal_entry_thesis_binding_contract(**args)


def test_production_resolver_requires_explicit_confirmation(case):
    args, service, _ = case
    before = service.journal.path.read_bytes()
    result = personal.resolve_personal_entry_thesis(**{k: args[k] for k in
        ("records", "account_scope", "expected_revision", "as_of")})
    assert result["status"] == "MISSING_CONFIRMATION"
    assert result["code"] == "PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED"
    assert result["ownership_verified"] is False
    assert service.journal.path.read_bytes() == before


def test_recording_snapshot_and_public_entry_do_not_replace_explicit_confirmation(case):
    args, _, _ = case
    del args["binding_candidate"]["confirmation"]
    args["binding_candidate"]["judgment_snapshot"] = {"entry_thesis": "public-ACTUAL-example"}
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


@pytest.mark.parametrize("fault", ["unregistered", "different_registered_version", "corrupt_payload",
    "future_created", "wrong_type"])
def test_repository_identity_and_content_are_reverified(case, fault):
    args, _, _ = case
    stored = args["entry_artifact"]
    if fault == "unregistered":
        args["entry_artifact"] = replace(stored, artifact_id="not-registered")
    elif fault == "different_registered_version":
        args["entry_artifact"] = replace(stored, created_at=AS_OF)
    elif fault == "corrupt_payload":
        object.__setattr__(stored.envelope, "canonical_payload", '{"tampered":true}')
    elif fault == "future_created":
        object.__setattr__(stored, "created_at", AS_OF)
    else:
        args["entry_artifact"] = args["consistency_artifact"]
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


@pytest.mark.parametrize("field,value", [("confirmation", None), ("entry_ref", {}),
    ("consistency_ref", {}), ("confirmation", {"explicit_original_entry_binding": True})])
def test_malformed_contract_fails_closed(case, field, value):
    args, _, _ = case
    args["binding_candidate"][field] = value
    with pytest.raises(ValueError):
        personal.validate_personal_entry_thesis_binding_contract(**args)


def test_prepared_record_or_baseline_is_not_a_confirmed_entry(case):
    args, _, _ = case
    for record in args["records"][:2]:
        args["binding_candidate"]["fill_record_sha256"] = record["record_sha256"]
        with pytest.raises(ValueError, match="Confirmed fill"):
            personal.validate_personal_entry_thesis_binding_contract(**args)


def test_future_unregistered_journal_binding_kind_is_not_silently_admitted(case):
    args, _, _ = case
    args["records"][-1]["kind"] = "PERSONAL_ENTRY_THESIS_CONFIRMED"
    with pytest.raises(ValueError):
        personal.resolve_personal_entry_thesis(**{k: args[k] for k in
            ("records", "account_scope", "expected_revision", "as_of")})


def narrative_request(args, **updates):
    return dict(idempotency_key="TEST_ONLY-thesis", expected_revision=3,
        fill_record_sha256=args["records"][-1]["record_sha256"],
        binding_mode="HISTORICAL_RECONSTRUCTION", read_and_confirmed=True,
        confirmation_note="TEST_ONLY now confirmed; not original PIT",
        reconstruction=dict(thesis="TEST_ONLY recorded personal rationale",
            hold_logic="Evidence still supports the recorded rationale",
            invalidation_conditions=["New evidence contradicts the rationale"]), **updates)


def thesis_service(args, service):
    return personal.PersonalEntryThesisService(service.journal, repository=args["repository"])


def test_authenticated_narrative_append_restart_and_revoke(case, tmp_path):
    args, service, _ = case
    api = thesis_service(args, service)
    before = service.journal.path.read_bytes()
    payload = narrative_request(args)
    kwargs = dict(repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    response, digest = api.confirm(payload, **kwargs)
    assert response["status"] == personal.CONFIRMED_KIND and response["revision"] == 4
    assert service.journal.path.read_bytes().startswith(before)
    assert response["confirmation"]["original_pit_proven"] is False
    assert response["confirmation"]["advisory_eligible"] is False
    assert response["confirmation"]["provenance"] == "USER_NARRATIVE_RECONSTRUCTION"
    assert "artifact_bundle" not in response["confirmation"]
    assert service._replay(service.records()).state == service._replay(args["records"]).state
    assert api.confirm(payload, **kwargs) == (response, digest)
    assert len(service.records()) == 4
    restarted = personal.PersonalEntryThesisService(journal_module.PrivateJournal(service.journal.path),
                                                   repository=args["repository"])
    view = restarted.view(**kwargs)
    row = view["items"][0]
    assert row["remaining_quantity"] == "100"
    assert row["current_binding"]["record_sha256"] == digest
    assert len(row["history"]) == 1
    revoke = dict(idempotency_key="TEST_ONLY-revoke", expected_revision=4,
        confirmation_record_sha256=digest, read_and_confirmed=True, confirmation_note="TEST_ONLY withdrawn")
    revoked = restarted.revoke(revoke, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    assert revoked[0]["status"] == personal.REVOKED_KIND
    assert restarted.revoke(revoke, authenticated_subject="LOCAL_OPERATOR", now=AS_OF) == revoked
    final = restarted.view(**kwargs)
    assert final["items"][0]["current_binding"] is None
    assert len(final["items"][0]["history"]) == 2
    assert len(service.records()) == 5


def test_confirmation_correction_is_append_only_and_exact_active_hash(case, tmp_path):
    args, service, _ = case
    api = thesis_service(args, service)
    kwargs = dict(repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    payload = narrative_request(args)
    _, digest = api.confirm(payload, **kwargs)
    before = service.journal.path.read_bytes()
    corrected = {**payload, "idempotency_key": "TEST_ONLY-correct", "expected_revision": 4,
                 "supersedes_record_sha256": digest, "confirmation_note": "TEST_ONLY corrected"}
    _, replacement = api.confirm(corrected, **kwargs)
    assert replacement != digest and service.journal.path.read_bytes().startswith(before)
    assert api.view(**kwargs)["items"][0]["current_binding"]["record_sha256"] == replacement
    with pytest.raises(journal_module.JournalConflict):
        api.confirm({**corrected, "idempotency_key": "wrong-active", "expected_revision": 5}, **kwargs)


@pytest.mark.parametrize("updates", [
    {"subject": "client-forgery"}, {"authenticated_subject": "client-forgery"},
    {"account_scope": "different"}, {"confirmed_at": "2000-01-01T00:00:00+08:00"},
    {"read_and_confirmed": False}, {"read_and_confirmed": "true"},
    {"binding_mode": "CONTEMPORANEOUS"}, {"fill_record_sha256": "0" * 64},
    {"reconstruction": {"thesis": "a", "hold_logic": "b", "invalidation_conditions": []}},
])
def test_invalid_confirmation_leaves_journal_unchanged(case, tmp_path, updates):
    args, service, _ = case
    before = service.journal.path.read_bytes()
    with pytest.raises(ValueError):
        thesis_service(args, service).confirm({**narrative_request(args), **updates},
            repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    assert service.journal.path.read_bytes() == before


def test_identity_and_revision_conflicts_are_not_idempotent_success(case, tmp_path):
    args, service, _ = case
    api = thesis_service(args, service)
    kwargs = dict(repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    request = narrative_request(args)
    api.confirm(request, **kwargs)
    before = service.journal.path.read_bytes()
    with pytest.raises(journal_module.JournalConflict, match="同一幂等键"):
        api.confirm(request, **{**kwargs, "authenticated_subject": "OTHER_AUTHENTICATED_OPERATOR"})
    with pytest.raises(journal_module.JournalConflict):
        api.confirm({**request, "idempotency_key": "new-stale-key"}, **kwargs)
    with pytest.raises(ValueError, match="subject mismatch"):
        api.view(**{**kwargs, "authenticated_subject": "OTHER_AUTHENTICATED_OPERATOR"})
    assert service.journal.path.read_bytes() == before


def test_artifact_confirmation_survives_repository_restart(case, tmp_path):
    args, service, _ = case
    api = thesis_service(args, service)
    payload = narrative_request(args)
    del payload["reconstruction"]
    payload.update(binding_mode="CONTEMPORANEOUS", entry_artifact_id=args["entry_artifact"].artifact_id,
                   consistency_artifact_id=args["consistency_artifact"].artifact_id)
    kwargs = dict(repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    _, digest = api.confirm(payload, **kwargs)
    result = personal.resolve_personal_entry_thesis(records=service.records(),
        account_scope=args["account_scope"], expected_revision=4, as_of=AS_OF,
        authenticated_subject="LOCAL_OPERATOR")
    assert result["status"] == "RESOLVED"
    binding = result["items"][0]["current_binding"]
    assert binding["record_sha256"] == digest
    assert binding["provenance"] == "REGISTERED_ARTIFACT_BINDING"
    assert binding["original_pit_proven"] is False  # Artifact cutoff alone is not full source-input PIT.
    assert binding["advisory_eligible"] is False


def test_view_lists_buy_without_artifacts_and_no_writes(case, tmp_path):
    args, service, _ = case
    before = service.journal.path.read_bytes()
    api = personal.PersonalEntryThesisService(service.journal)
    result = api.view(repository_root=tmp_path, authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    assert result["items"][0]["candidate_plans"] == []
    assert result["items"][0]["current_binding"] is None
    assert result["items"][0]["fill_record_sha256"] == args["records"][-1]["record_sha256"]
    assert service.journal.path.read_bytes() == before


def _confirm_registered_entry(args, service, root):
    request = narrative_request(args)
    del request["reconstruction"]
    request.update(binding_mode="CONTEMPORANEOUS",
        entry_artifact_id=args["entry_artifact"].artifact_id,
        consistency_artifact_id=args["consistency_artifact"].artifact_id)
    return thesis_service(args, service).confirm(request, repository_root=root,
        authenticated_subject="LOCAL_OPERATOR", now=AS_OF)


def test_closed_lot_revocation_replays_after_restart_and_remains_idempotent(case, tmp_path, monkeypatch):
    args, service, _ = case
    _, confirmation = _confirm_registered_entry(args, service, tmp_path)
    class SaleClock(datetime):
        @classmethod
        def now(cls, tz=None):
            stamp = cls.fromisoformat(AS_OF.isoformat())
            return stamp if tz is None else stamp.astimezone(tz)
    monkeypatch.setattr(journal_module, "datetime", SaleClock)
    seller = journal_module.PrivatePortfolioService(service.journal, clock=SaleClock.now)
    _, prepared = seller.prepare_fill({"idempotency_key": "TEST_ONLY-close", "expected_revision": 4,
        "fill": {"transaction_id": "TEST_ONLY-close", "side": "SELL", "sleeve": "CORE_VALUE",
            "symbol": "300364", "exchange": "SZSE", "quantity": "100", "price_cny": "19",
            "fees_cny": "1", "trade_date": "2026-10-15"}})
    seller.confirm_fill({"idempotency_key": "TEST_ONLY-close-confirm", "expected_revision": 5,
        "prepared_record_sha256": prepared, "confirmed_at": AS_OF.isoformat(),
        "confirmation_note": "TEST_ONLY fully closed"})
    monkeypatch.setattr(journal_module, "datetime", datetime)
    before = service.journal.path.read_bytes()
    api = thesis_service(args, service)
    request = dict(idempotency_key="TEST_ONLY-closed-revoke", expected_revision=6,
        confirmation_record_sha256=confirmation, read_and_confirmed=True,
        confirmation_note="TEST_ONLY withdraw closed entry binding")
    kwargs = dict(authenticated_subject="LOCAL_OPERATOR", now=AS_OF)
    response = api.revoke(request, **kwargs)
    assert response[0]["status"] == personal.REVOKED_KIND
    assert service.journal.path.read_bytes().startswith(before)
    assert api.revoke(request, **kwargs) == response
    restarted = journal_module.PrivatePortfolioService(
        journal_module.PrivateJournal(service.journal.path), clock=lambda: AS_OF)
    state = restarted._replay(restarted.records()).state
    assert sum(lot.quantity for lot in state.lots) == 0
    view = personal.PersonalEntryThesisService(restarted.journal, repository=args["repository"]).view(
        repository_root=tmp_path, **kwargs)
    assert view["items"][0]["remaining_quantity"] == "0"
    assert view["items"][0]["current_binding"] is None
    after = service.journal.path.read_bytes()
    with pytest.raises(journal_module.JournalConflict):
        api.revoke({**request, "idempotency_key": "TEST_ONLY-wrong-revoke", "expected_revision": 7}, **kwargs)
    request = narrative_request(args)
    with pytest.raises(ValueError, match="no longer held"):
        api.confirm({**request, "idempotency_key": "TEST_ONLY-closed-confirm", "expected_revision": 7},
            repository_root=tmp_path, **kwargs)
    assert service.journal.path.read_bytes() == after


def _save_current_review(args, *, status="BROKEN", available=AS_OF, review_date=None, **changes):
    review = replace(_consistency(status), symbol="300364",
        as_of=review_date or AS_OF.date(), review_id="TEST_ONLY-current-" + status, **changes)
    _, payload = artifact_payload(review)
    return args["repository"].save_object(review, identity=ResearchArtifactIdentity(
        scope_type="security", scope_key=review.symbol,
        artifact_type=personal.ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
        schema_version=payload["schema_version"], as_of=review.as_of, available_at=available),
        run_id="TEST_ONLY-current-consistency")


def _resolve_current(args, root):
    return personal.resolve_current_entry_consistency(root, entry_artifact=args["entry_artifact"],
        as_of=AS_OF, repository=args["repository"])


def test_current_broken_review_overrides_old_consistent_without_mutating_original(case, tmp_path):
    args, service, _ = case
    _confirm_registered_entry(args, service, tmp_path)
    before = service.journal.path.read_bytes()
    original = args["entry_artifact"]
    broken = _save_current_review(args)
    result = _resolve_current(args, tmp_path)
    assert result["schema_version"] == "owned-current-consistency-resolution-v1"
    assert result["investment_consistency_review"].status == "BROKEN"
    assert result["consistency_artifact"] == broken
    assert result["consistency_ref"] == personal._ref(broken)
    assert result["entry_artifact"] == original
    context = personal.owned_entry_context(records=service.records(), symbol="300364", sleeve="CORE_VALUE",
        authenticated_subject="LOCAL_OPERATOR", as_of=AS_OF)
    assert context["investment_consistency_review"].status == "CONSISTENT"
    assert service.journal.path.read_bytes() == before


@pytest.mark.parametrize("status", ["CONSISTENT", "FULFILLED", "WEAKENED", "BROKEN"])
def test_current_review_selects_newest_entry_matched_version(case, tmp_path, status):
    args, _, _ = case
    current = _save_current_review(args, status=status)
    _save_current_review(args, status="BROKEN", available=AS_OF,
                         entry_id="TEST_ONLY-other-entry")
    result = _resolve_current(args, tmp_path)
    assert result["consistency_artifact"] == current
    assert result["investment_consistency_review"].status == status


def test_newly_available_correction_wins_over_older_publication_with_later_as_of(case, tmp_path):
    args, _, _ = case
    _save_current_review(args, status="CONSISTENT",
        available=datetime.fromisoformat("2026-10-15T19:00:00+08:00"))
    correction = _save_current_review(args, status="BROKEN", review_date=STAMP.date())
    assert _resolve_current(args, tmp_path)["consistency_artifact"] == correction


@pytest.mark.parametrize("future_field", ["available_at", "created_at", "as_of"])
def test_future_review_never_replaces_available_review(case, tmp_path, future_field):
    args, _, _ = case
    future = datetime.fromisoformat("2026-10-16T20:00:00+08:00")
    row = _save_current_review(args,
        available=future if future_field == "available_at" else AS_OF,
        review_date=future.date() if future_field == "as_of" else None)
    if future_field == "created_at":
        row = replace(row, created_at=future)
        args["repository"]._artifacts[row.artifact_id] = row
    result = _resolve_current(args, tmp_path)
    assert result["consistency_artifact"] == args["consistency_artifact"]


@pytest.mark.parametrize("fault", ["missing_sources", "missing_comparison_sources", "blocked", "schema", "identity_date", "payload_hash"])
def test_invalid_newer_review_cannot_silently_fall_back_to_old_consistent(case, tmp_path, fault):
    args, _, _ = case
    changes = {"evidence_refs": ()} if fault == "missing_sources" else {"blockers": ("source_conflict",)} if fault == "blocked" else {}
    if fault == "missing_comparison_sources":
        changes = {"comparisons": tuple(replace(c, evidence_refs=()) for c in _consistency("BROKEN").comparisons)}
    row = _save_current_review(args, **changes)
    if fault in {"schema", "identity_date"}:
        identity = replace(row.envelope.identity,
            **({"schema_version": "unsupported-review-version"} if fault == "schema" else {"as_of": STAMP.date()}))
        row = replace(row, envelope=replace(row.envelope, identity=identity))
    elif fault == "payload_hash":
        object.__setattr__(row.envelope, "payload_sha256", "0" * 64)
    args["repository"]._artifacts[row.artifact_id] = row
    with pytest.raises(ValueError):
        _resolve_current(args, tmp_path)


def test_missing_current_registered_review_does_not_use_frozen_binding(case, tmp_path):
    args, _, _ = case
    args["repository"] = repository_module.InMemoryResearchArtifactRepository()
    with pytest.raises(ValueError, match="entry-matched.*unavailable"):
        _resolve_current(args, tmp_path)


def test_conflicting_newest_review_versions_are_rejected(case, tmp_path):
    args, _, _ = case
    _save_current_review(args, status="BROKEN")
    _save_current_review(args, status="CONSISTENT")
    with pytest.raises(ValueError, match="Ambiguous newest"):
        _resolve_current(args, tmp_path)


@pytest.mark.parametrize("sleeve", ["CORE_VALUE", "HOTSPOT_SATELLITE"])
def test_held_advisory_consumes_current_broken_artifact_for_original_entry(case, tmp_path, monkeypatch, sleeve):
    from types import SimpleNamespace
    from value_investment_agent.application.portfolio.held_continuity import evaluate_owned_held_advisory
    from value_investment_agent.application.decision import build_advisory_decision_recommendation_v3 as advisory
    from value_investment_agent.application.product import publication_chain, decision_surface
    from value_investment_agent.application.hotspot import independent_price_conditions
    from value_investment_agent.application.hotspot import independent_admission
    from value_investment_agent.application.portfolio import held_continuity
    from value_investment_agent.application.decision import restore_decision_recommendation as restore
    args, service, _ = case
    _confirm_registered_entry(args, service, tmp_path)
    context = personal.owned_entry_context(records=service.records(), symbol="300364", sleeve="CORE_VALUE",
        authenticated_subject="LOCAL_OPERATOR", as_of=AS_OF)
    broken = _save_current_review(args)
    monkeypatch.setattr(personal, "_application_repository", lambda *a, **k: args["repository"])
    monkeypatch.setattr(independent_price_conditions, "project_independent_price_condition",
        lambda *a, **k: {"risk_review_eligible": True, "blockers": [], "independent_admission": {"namespace": "ACTUAL"}})
    monkeypatch.setattr(held_continuity, "load_held_price_plan", lambda root, symbol, binding, **k: binding)
    monkeypatch.setattr(independent_admission, "load_independent_admission", lambda *a, **k:
        dict(risk_review_eligible=True, blockers=[], review_status='VERIFIED', rule_version='TEST_ONLY',
             gate_source_bindings=dict(price_structure=[dict(path='TEST_ONLY', sha256='a'*64)],
                                       strategy_validation=[{}], event_risk=[{}])))
    monkeypatch.setattr(publication_chain, "load_current_chain", lambda root:
        {"model": {"audit": {"evidence": [{"artifact_type": "verified_decision_workbench"}]}}})
    monkeypatch.setattr(publication_chain, "bound_object", lambda *a:
        {"symbol": "300364", "generated_at": AS_OF.isoformat()})
    monkeypatch.setattr(personal, "registered_entry_workbenches", lambda *a, **k:
        [{"symbol": "300364", "generated_at": AS_OF.isoformat()}])
    monkeypatch.setattr(decision_surface, "verify_current_decision_workbench", lambda *a, **k:
        SimpleNamespace(recommendation=SimpleNamespace(symbol="300364", run_id="TEST_ONLY-current",
            input_model_id=None, input_additional_blockers=()), dependencies={}, dependency_objects={
                "event_materiality": SimpleNamespace(covers=lambda day: True, review_blockers=()),
                "research_case": object(), "valuation": object()}))
    def build(**kwargs):
        assert kwargs["entry_thesis"] == context["entry_thesis"]
        assert kwargs["investment_consistency_review"].status == "BROKEN"
        assert kwargs["dependency_artifacts"]["investment_consistency_review"] == broken
        return SimpleNamespace(recommendation_action="SELL_CANDIDATE", blockers=(), as_policy=lambda: {})
    monkeypatch.setattr(advisory, "build_advisory_decision_recommendation_v3", build)
    monkeypatch.setattr(restore, "_restore_optional_payload_inputs", lambda *a: {})
    before = service.journal.path.read_bytes()
    action, blockers, evidence = evaluate_owned_held_advisory(tmp_path, context=context,
        plan={"symbol": "300364", "schema_version": "value-action-plan-v1" if sleeve == "CORE_VALUE"
            else "price-action-plan-independent-v2", "strategy": sleeve,
            "case_path": "TEST_ONLY", "case_sha256": "a"*64, "model_or_rule_version": "TEST_ONLY"}, now=AS_OF)
    assert action == "SELL_CANDIDATE" and not blockers
    if sleeve == "HOTSPOT_SATELLITE":
        assert evidence["current_consistency_review"] == personal._ref(broken)
    assert service.journal.path.read_bytes() == before


def test_partial_sale_keeps_exact_cross_sleeve_theses_after_restart(case, tmp_path, monkeypatch):
    args, service, save = case
    _confirm_registered_entry(args, service, tmp_path)
    # The test clock affects legacy fill append timestamps as well as service calls.
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromisoformat(AS_OF.isoformat())
    monkeypatch.setattr(journal_module, 'datetime', Clock)
    seller = journal_module.PrivatePortfolioService(service.journal, clock=Clock.now)
    _, prepared = seller.prepare_fill(dict(idempotency_key='TEST_ONLY-other-sleeve', expected_revision=4,
        fill=dict(transaction_id='TEST_ONLY-hotspot-buy', side='BUY', sleeve='HOTSPOT_SATELLITE',
            symbol='300364', exchange='SZSE', quantity='200', price_cny='18', fees_cny='1',
            trade_date='2026-10-15', next_sell_session='2026-10-16', trading_unit='100')))
    _, bought = seller.confirm_fill(dict(idempotency_key='TEST_ONLY-hotspot-confirm', expected_revision=5,
        prepared_record_sha256=prepared, confirmed_at=AS_OF.isoformat(), confirmation_note='TEST_ONLY'))
    entry = personal.decode_artifact(personal.ARTIFACT_ENTRY_THESIS_SNAPSHOT,
        args['entry_artifact'].envelope.payload_object())
    hotspot_entry = save(replace(entry, entry_id='TEST_ONLY-hotspot-entry', entry_date=AS_OF.date(),
        confirmed_at=AS_OF, thesis='TEST_ONLY distinct hotspot structure rationale'), AS_OF)
    hotspot_review = save(replace(_consistency('CONSISTENT'), symbol='300364',
        entry_id='TEST_ONLY-hotspot-entry', as_of=AS_OF.date()))
    personal.PersonalEntryThesisService(service.journal, repository=args['repository']).confirm(dict(
        idempotency_key='TEST_ONLY-hotspot-thesis', expected_revision=6, fill_record_sha256=bought,
        binding_mode='CONTEMPORANEOUS', read_and_confirmed=True, confirmation_note='TEST_ONLY distinct sleeve',
        entry_artifact_id=hotspot_entry.artifact_id, consistency_artifact_id=hotspot_review.artifact_id),
        repository_root=tmp_path, authenticated_subject='LOCAL_OPERATOR', now=Clock.now())
    _, prepared = seller.prepare_fill(dict(idempotency_key='TEST_ONLY-partial', expected_revision=7,
        fill=dict(transaction_id='TEST_ONLY-partial', side='SELL', sleeve='CORE_VALUE', symbol='300364',
            exchange='SZSE', quantity='50', price_cny='19', fees_cny='1', trade_date='2026-10-15')))
    seller.confirm_fill(dict(idempotency_key='TEST_ONLY-partial-confirm', expected_revision=8,
        prepared_record_sha256=prepared, confirmed_at=AS_OF.isoformat(), confirmation_note='TEST_ONLY partial'))
    records = journal_module.PrivateJournal(service.journal.path).read()
    core = personal.owned_entry_context(records=records, symbol='300364', sleeve='CORE_VALUE',
        authenticated_subject='LOCAL_OPERATOR', as_of=AS_OF)
    hotspot = personal.owned_entry_context(records=records, symbol='300364', sleeve='HOTSPOT_SATELLITE',
        authenticated_subject='LOCAL_OPERATOR', as_of=AS_OF)
    assert core['held_quantity'] == '50' and hotspot['held_quantity'] == '200'
    assert core['entry_artifact'] == args['entry_artifact']
    assert hotspot['entry_artifact'] == hotspot_entry
    assert core['entry_thesis_record_sha256'] != hotspot['entry_thesis_record_sha256']
    assert core['advisory_dependencies_valid'] and hotspot['advisory_dependencies_valid']
