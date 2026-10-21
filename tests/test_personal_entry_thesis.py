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


def test_production_resolver_reports_real_missing_record_interface(case):
    args, service, _ = case
    before = service.journal.path.read_bytes()
    result = personal.resolve_personal_entry_thesis(**{k: args[k] for k in
        ("records", "account_scope", "expected_revision", "as_of")})
    assert result["status"] == "CODE_GAP"
    assert result["code"] == personal.MISSING_CONFIRMATION_INTERFACE
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
