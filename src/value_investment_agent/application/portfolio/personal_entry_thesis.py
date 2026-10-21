"""Authenticated personal entry confirmation in the existing private journal.

The route authenticates the caller and passes its trusted subject separately.
Hashes bind immutable facts; confirmation never grants economic approval.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .private_portfolio_service import (
    PrivateJournal, PrivatePortfolioService, JournalConflict, JournalValidationError,
    _fill_from_body, request_digest, _idempotency_key,
)
from ...domain.decision.advisory_dependency_admission import validate_advisory_dependencies
from ...domain.decision.decision_recommendation import DECISION_RECOMMENDATION_V3_SCHEMA
from ...investment_decision import (
    EntryThesisSnapshot, InvestmentConsistencyReview, ENTRY_TYPE_RECONSTRUCTED, ENTRY_TYPE_SIMULATED,
)
from ..decision.artifact_bundle import ReadOnlyArtifactBundleRepository, export_artifact_bundle
from ...research_artifact_codecs import decode_artifact
from ...research_artifacts import (
    ARTIFACT_ENTRY_THESIS_SNAPSHOT, ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
    StoredResearchArtifact, parse_stored_artifact_payload,
)

BINDING_SCHEMA = "personal-entry-thesis-binding-contract-v1"
MISSING_CONFIRMATION_INTERFACE = "PERSONAL_ENTRY_THESIS_CONFIRMATION_RECORD_UNSUPPORTED"
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class ArtifactReader(Protocol):
    """Read subset of the existing ResearchArtifactRepository protocol."""

    def load_by_id(self, artifact_id: str) -> StoredResearchArtifact: ...


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _clock(value: str | datetime) -> datetime:
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    _require(isinstance(stamp, datetime) and stamp.utcoffset() is not None,
             "Timezone-aware timestamp required")
    return stamp


def _journal(records: Sequence[dict], *, account_scope: str, expected_revision: int,
             as_of: datetime) -> None:
    _clock(as_of)
    _require(isinstance(account_scope, str) and bool(account_scope.strip()), "Account scope required")
    _require(type(expected_revision) is int and expected_revision == len(records) and bool(records),
             "Journal revision mismatch or empty journal")
    previous = None
    previous_at = None
    for sequence, record in enumerate(records, 1):
        PrivateJournal._validate_record(record, line_number=sequence, previous=previous)
        _require(type(record.get("sequence")) is int and record["sequence"] == sequence,
                 "Journal sequence mismatch")
        recorded_at = _clock(record["recorded_at"])
        _require(recorded_at <= as_of and (previous_at is None or previous_at <= recorded_at),
                 "Future or out-of-order journal record")
        previous_at = recorded_at
        previous = record["record_sha256"]
    baselines = [record for record in records if record["kind"] == "BASELINE_CONFIRMED"]
    _require(len(baselines) == 1 and records[0] == baselines[0], "Unique initial baseline required")
    _require(baselines[0]["body"]["account_scope"] == account_scope, "Account scope mismatch")


def _artifact(artifact: StoredResearchArtifact, *, repository: ArtifactReader,
              artifact_type: str, symbol: str, cutoff: datetime):
    _require(isinstance(artifact, StoredResearchArtifact), "Registered stored artifact required")
    registered = repository.load_by_id(artifact.artifact_id)
    _require(registered == artifact, "Artifact differs from registered version")
    identity = registered.envelope.identity
    _require(identity.scope_type == "security" and identity.scope_key == symbol
             and identity.artifact_type == artifact_type, "Artifact scope/type mismatch")
    _require(_clock(identity.available_at) <= cutoff and _clock(registered.created_at) <= cutoff,
             "Artifact unavailable at binding cutoff")
    payload = parse_stored_artifact_payload(registered)
    _require(payload.get("schema_version") == identity.schema_version, "Artifact schema mismatch")
    return decode_artifact(artifact_type, payload)


def _ref(artifact: StoredResearchArtifact) -> dict:
    return {"artifact_id": artifact.artifact_id, "payload_sha256": artifact.envelope.payload_sha256,
            "available_at": artifact.envelope.identity.available_at.isoformat()}


def validate_personal_entry_thesis_binding_contract(
    *, records: Sequence[dict], account_scope: str, authenticated_subject: str,
    expected_revision: int, binding_candidate: Mapping,
    entry_artifact: StoredResearchArtifact, consistency_artifact: StoredResearchArtifact,
    repository: ArtifactReader, as_of: datetime,
) -> dict:
    """Validate preparation facts; persistence and ownership require the service.

    This read-only contract does not produce advisory/trading admission.
    """
    try:
        return _validate_binding_contract(records=records, account_scope=account_scope,
            authenticated_subject=authenticated_subject, expected_revision=expected_revision,
            binding_candidate=binding_candidate, entry_artifact=entry_artifact,
            consistency_artifact=consistency_artifact, repository=repository, as_of=as_of)
    except (KeyError, TypeError, AttributeError, ArithmeticError) as error:
        raise ValueError("Invalid personal entry binding input or unavailable registered artifact") from error


def _validate_binding_contract(*, records, account_scope, authenticated_subject, expected_revision,
        binding_candidate, entry_artifact, consistency_artifact, repository, as_of,
        binding_mode="CONTEMPORANEOUS"):
    _journal(records, account_scope=account_scope, expected_revision=expected_revision, as_of=as_of)
    _require(isinstance(authenticated_subject, str) and bool(authenticated_subject.strip()),
             "Authenticated subject required")
    b = binding_candidate
    _require(set(b) == {"schema_version", "account_scope", "journal_revision", "journal_tip_sha256",
        "fill_record_sha256", "transaction_id", "symbol", "exchange", "sleeve", "entry_ref",
        "consistency_ref", "confirmation", "action"}, "Exact binding contract fields required")
    _require(b["schema_version"] == BINDING_SCHEMA and b["action"] == "no_order",
             "Unsupported binding contract")
    _require(b["account_scope"] == account_scope and type(b["journal_revision"]) is int
             and b["journal_revision"] == expected_revision
             and b["journal_tip_sha256"] == records[-1]["record_sha256"], "Binding journal identity mismatch")
    c = b["confirmation"]
    _require(set(c) == {"subject", "confirmed_at", "note", "explicit_original_entry_binding"},
             "Explicit confirmation fields required")
    _require(c["subject"] == authenticated_subject and c["explicit_original_entry_binding"] is True
             and isinstance(c["note"], str) and bool(c["note"].strip()), "Explicit user confirmation required")
    confirmed = _clock(c["confirmed_at"])
    _require(_clock(records[-1]["recorded_at"]) <= confirmed <= as_of, "Invalid binding confirmation time")
    matches = [r for r in records if r["record_sha256"] == b["fill_record_sha256"]]
    _require(len(matches) == 1 and matches[0]["kind"] == "FILL_CONFIRMED", "Confirmed fill hash required")
    record = matches[0]
    body = record["body"]
    fill = body["fill"]
    _fill_from_body(body)
    _require(fill["side"] == "BUY", "Original entry requires an actual BUY fill")
    _require(b["exchange"] in {"SSE", "SZSE", "BSE"}
             and b["sleeve"] in {"CORE_VALUE", "HOTSPOT_SATELLITE"}, "Unsupported exchange/sleeve")
    for field in ("transaction_id", "symbol", "exchange", "sleeve"):
        _require(fill[field] == b[field], "Fill identity mismatch: " + field)
    _require(sum(r["kind"] == "FILL_CONFIRMED" and
                 r["body"]["fill"]["transaction_id"] == b["transaction_id"] for r in records) == 1,
             "Ambiguous confirmed transaction")
    prepared = [r for r in records[:record["sequence"] - 1]
                if r["record_sha256"] == body["prepared_record_sha256"]]
    _require(len(prepared) == 1 and prepared[0]["kind"] == "FILL_PREPARED"
             and prepared[0]["body"]["fill"] == fill
             and prepared[0]["sequence"] + 1 == record["sequence"], "Prepared fill binding mismatch")
    _require(body["evidence_ref"].get("kind") == "user_confirmation"
             and bool(body["confirmation"]["note"].strip()), "Fill user confirmation missing")
    fill_confirmed = _clock(body["confirmation"]["confirmed_at"])
    _require(fill_confirmed <= _clock(record["recorded_at"]) <= confirmed,
             "Fill confirmation chronology mismatch")
    _require(binding_mode in {"CONTEMPORANEOUS", "HISTORICAL_RECONSTRUCTION"}, "Unknown binding mode")
    historical = binding_mode == "HISTORICAL_RECONSTRUCTION"
    entry = _artifact(entry_artifact, repository=repository,
        artifact_type=ARTIFACT_ENTRY_THESIS_SNAPSHOT, symbol=b["symbol"],
        cutoff=confirmed if historical else fill_confirmed)
    review = _artifact(consistency_artifact, repository=repository,
        artifact_type=ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW, symbol=b["symbol"], cutoff=confirmed)
    _require(isinstance(entry, EntryThesisSnapshot) and isinstance(review, InvestmentConsistencyReview),
             "Existing entry/consistency domain objects required")
    _require(b["entry_ref"] == _ref(entry_artifact) and b["consistency_ref"] == _ref(consistency_artifact),
             "Exact artifact ID/hash/available_at binding required")
    _require(entry.entry_date.isoformat() == fill["trade_date"]
             and entry.entry_price == Decimal(fill["price_cny"]), "Entry date/price differs from original fill")
    _require(entry.entry_type != ENTRY_TYPE_SIMULATED, "Simulated entry cannot bind a confirmed fill")
    if historical:
        _require(_clock(entry.confirmed_at) <= confirmed
                 and (entry.created_at is None or _clock(entry.created_at) <= confirmed),
                 "Future reconstructed entry")
        _require(review.entry_id == entry.entry_id and entry.entry_date <= review.as_of
                 <= confirmed.astimezone(_SHANGHAI).date(), "Reconstructed review identity/date mismatch")
        entry = replace(entry, entry_type=ENTRY_TYPE_RECONSTRUCTED, reconstructed_note=c["note"])
    else:
        _require(_clock(entry.confirmed_at) <= fill_confirmed
                 and (entry.created_at is None or _clock(entry.created_at) <= fill_confirmed),
                 "Entry was not confirmed at original fill")
        validate_advisory_dependencies(symbol=b["symbol"], decision_as_of=confirmed.astimezone(_SHANGHAI).date(),
            recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
            entry_thesis=entry, investment_consistency_review=review)
    return {"status": "CONTRACT_VALIDATED_NOT_PERSISTED", "action": "no_order",
        "ownership_verified": False, "formal_eligibility": False, "personal_sell_permission": False,
        "position_guidance": None, "entry_thesis": entry, "investment_consistency_review": review,
        "journal_revision": expected_revision, "fill_record_sha256": record["record_sha256"],
        "blockers": [MISSING_CONFIRMATION_INTERFACE]}


def resolve_personal_entry_thesis(
    *, records: Sequence[dict], account_scope: str, expected_revision: int, as_of: datetime,
    authenticated_subject: str | None = None, repository: ArtifactReader | None = None,
) -> dict:
    """Replay explicit confirmations; public artifacts never establish ownership."""
    _journal(records, account_scope=account_scope, expected_revision=expected_revision, as_of=as_of)
    items, active, history = _replay_confirmations(records, account_scope=account_scope,
        authenticated_subject=authenticated_subject, as_of=as_of, repository=repository)
    bound = [row for row in items if Decimal(row["remaining_quantity"]) > 0
             and row["current_binding"] is not None]
    return {"status": "RESOLVED" if bound else "MISSING_CONFIRMATION",
        "code": None if bound else "PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED",
        "journal_revision": expected_revision, "account_scope": account_scope,
        "items": items, "confirmations": history,
        "action": "no_order", "ownership_verified": False, "formal_eligibility": False,
        "personal_sell_permission": False, "position_guidance": None}


CONFIRMED_KIND = "PERSONAL_ENTRY_THESIS_CONFIRMED"
REVOKED_KIND = "PERSONAL_ENTRY_THESIS_REVOKED"
EVENT_SCHEMA = "personal-entry-thesis-confirmation-v1"


def _subject(value):
    _require(isinstance(value, str) and bool(value.strip()), "Authenticated subject required")
    return value


def _sources(records):
    """Track fill lineage with the existing reconciliation's FIFO/sellability rule.

    Baseline lots participate in consumption but never acquire invented BUY ids.
    Financial balances and actual sellability remain owned by _replay.
    """
    service = PrivatePortfolioService(PrivateJournal(Path("unused-read-only")))
    service._replay(records, _validate_theses=False)
    initial = service._replay(records[:1], _validate_theses=False)
    lots = [dict(fill_hash=None, sleeve=lot.sleeve, symbol=lot.symbol, exchange=lot.exchange,
                 remaining=lot.quantity, sellable_on=lot.sellable_on) for lot in initial.state.lots]
    items = {}
    for record in records:
        if record["kind"] != "FILL_CONFIRMED":
            continue
        fill = _fill_from_body(record["body"])
        if fill.side == "BUY":
            digest = record["record_sha256"]
            items[digest] = dict(fill_record_sha256=digest, transaction_id=fill.transaction_id,
                symbol=fill.symbol, exchange=fill.exchange, sleeve=fill.sleeve,
                quantity=str(fill.quantity), remaining_quantity=str(fill.quantity),
                trade_date=fill.trade_date.isoformat(), price_cny=str(fill.price_cny),
                current_binding=None, history=[], candidate_plans=[])
            lots.append(dict(fill_hash=digest, sleeve=fill.sleeve, symbol=fill.symbol,
                exchange=fill.exchange, remaining=fill.quantity, sellable_on=fill.next_sell_session))
        else:
            remaining = fill.quantity
            for lot in lots:
                if (remaining and lot["symbol"] == fill.symbol and lot["exchange"] == fill.exchange
                        and lot["sleeve"] == fill.sleeve and lot["sellable_on"] <= fill.trade_date):
                    sold = min(remaining, lot["remaining"])
                    lot["remaining"] -= sold
                    remaining -= sold
            _require(remaining == 0, "Confirmed sell exceeds source lots")
    for lot in lots:
        if lot["fill_hash"] is not None:
            items[lot["fill_hash"]]["remaining_quantity"] = str(lot["remaining"])
    return items, lots


def _summary(record):
    body = record["body"]
    summary = {**deepcopy(body), "record_sha256": record["record_sha256"],
        "recorded_at": record["recorded_at"], "kind": record["kind"],
        "revision": record["sequence"], "action": "no_order",
        "ownership_verified": record["kind"] == CONFIRMED_KIND,
        "formal_eligibility": False, "personal_sell_permission": False}
    if record["kind"] == CONFIRMED_KIND and body.get("provenance") == "REGISTERED_ARTIFACT_BINDING":
        reader = ReadOnlyArtifactBundleRepository(body["artifact_bundle"])
        stored = reader.load_by_id(body["binding_contract"]["entry_ref"]["artifact_id"])
        entry = decode_artifact(ARTIFACT_ENTRY_THESIS_SNAPSHOT, parse_stored_artifact_payload(stored))
        summary.update(thesis=entry.thesis, hold_logic=entry.hold_logic,
                       invalidation_conditions=list(entry.breakers))
    return summary


def _narrative(value):
    _require(isinstance(value, Mapping) and not set(value) - {
        "thesis", "hold_logic", "invalidation_conditions", "research_version", "strategy_version"},
        "Invalid reconstruction fields")
    for key in ("thesis", "hold_logic"):
        _require(isinstance(value.get(key), str) and 0 < len(value[key].strip()) <= 8000,
                 key + " requires bounded nonempty text")
    conditions = value.get("invalidation_conditions")
    _require(isinstance(conditions, list) and 0 < len(conditions) <= 30
             and all(isinstance(x, str) and 0 < len(x.strip()) <= 2000 for x in conditions),
             "Explicit invalidation conditions required")
    for key in ("research_version", "strategy_version"):
        if key in value:
            _require(isinstance(value[key], str) and 0 < len(value[key].strip()) <= 500,
                     "Invalid declared version")
    return deepcopy(dict(value))


def _replay_confirmations(records, *, account_scope, authenticated_subject, as_of, repository=None):
    items, lots = _sources(records)
    active, history = {}, []
    for index, record in enumerate(records):
        if record["kind"] not in {CONFIRMED_KIND, REVOKED_KIND}:
            continue
        body = record["body"]
        _require(body.get("schema_version") == EVENT_SCHEMA and body.get("account_scope") == account_scope,
                 "Personal entry event account/schema mismatch")
        _require(record.get("changes_holdings") is False, "Thesis event cannot change holdings")
        _require(body.get("journal_revision") == index
                 and type(body.get("journal_revision")) is int
                 and body.get("journal_tip_sha256") == record["previous_record_sha256"],
                 "Personal entry event revision mismatch")
        _require(body.get("action") == "no_order", "Personal entry event action mismatch")
        subject = _subject(body.get("authenticated_subject"))
        if authenticated_subject is not None:
            _require(subject == authenticated_subject, "Authenticated subject mismatch")
        _require(_clock(body["confirmed_at"]) <= _clock(record["recorded_at"]) <= as_of,
                 "Personal entry event timestamp mismatch")
        _require(body.get("read_and_confirmed") is True and isinstance(body.get("confirmation_note"), str)
                 and bool(body["confirmation_note"].strip()), "Explicit confirmation required")
        digest = body["fill_record_sha256"]
        _require(digest in items, "Personal entry event must bind a confirmed BUY")
        prefix_items, _ = _sources(records[:index])
        _require(digest in prefix_items, "Personal entry event must bind a prior BUY")
        if record["kind"] == CONFIRMED_KIND:
            _require(Decimal(prefix_items[digest]["remaining_quantity"]) > 0,
                     "Personal entry event must bind a surviving prior BUY")
        _require(_clock(records[index - 1]["recorded_at"]) <= _clock(body["confirmed_at"]),
                 "Personal entry confirmation predates journal tip")
        fill = items[digest]
        for field in ("symbol", "exchange", "sleeve", "transaction_id"):
            _require(body.get(field) == fill[field], "Personal entry event fill mismatch")
        previous = active.get(digest)
        if record["kind"] == REVOKED_KIND:
            _require(previous is not None and body["confirmation_record_sha256"] == previous["record_sha256"],
                     "Revocation does not bind active confirmation")
            del active[digest]
        else:
            _require(body.get("supersedes_record_sha256") == (previous["record_sha256"] if previous else None),
                     "Correction must supersede active confirmation")
            _require(body.get("original_pit_proven") is False and body.get("advisory_eligible") is False,
                     "Confirmation cannot assert investment/PIT admission")
            if body.get("provenance") == "USER_NARRATIVE_RECONSTRUCTION":
                _require(body.get("binding_mode") == "HISTORICAL_RECONSTRUCTION",
                         "Narrative cannot become contemporaneous evidence")
                _narrative(body["reconstruction"])
            else:
                _require(body.get("provenance") == "REGISTERED_ARTIFACT_BINDING", "Unknown thesis provenance")
                saved = ReadOnlyArtifactBundleRepository(body["artifact_bundle"])
                b = body["binding_contract"]
                _require(b["confirmation"]["confirmed_at"] == body["confirmed_at"]
                         and b["confirmation"]["note"] == body["confirmation_note"]
                         and all(b[key] == body[key] for key in (
                             "fill_record_sha256", "transaction_id", "symbol", "exchange", "sleeve")),
                         "Stored binding differs from authenticated event")
                reader = repository or saved
                entry = reader.load_by_id(b["entry_ref"]["artifact_id"])
                consistency = reader.load_by_id(b["consistency_ref"]["artifact_id"])
                _require(entry == saved.load_by_id(entry.artifact_id)
                         and consistency == saved.load_by_id(consistency.artifact_id), "Stored artifact changed")
                _validate_binding_contract(records=records[:index], account_scope=account_scope,
                    authenticated_subject=subject, expected_revision=index, binding_candidate=b,
                    entry_artifact=entry, consistency_artifact=consistency, repository=reader,
                    as_of=_clock(body["confirmed_at"]), binding_mode=body["binding_mode"])
            active[digest] = _summary(record)
        summary = _summary(record)
        history.append(summary)
        fill["history"].append(summary)
    for digest, value in active.items():
        items[digest]["current_binding"] = value
    return list(items.values()), active, history


def registered_entry_workbenches(root, *, chain=None):
    """Read the existing primary publication binding and additional audit bindings."""
    from ..product.publication_chain import load_current_chain, bound_object
    chain = load_current_chain(Path(root)) if chain is None else chain
    bindings = [row for row in chain["model"].get("audit", {}).get("evidence", [])
                if row.get("artifact_type") == "verified_decision_workbench"]
    primary = chain.get("sources", {}).get("decision_workbench_binding")
    if primary is not None:
        bindings.append(primary)
    unique = {(row["path"], row["sha256"]) for row in bindings}
    return [bound_object(Path(root), {"path": path, "sha256": digest})
            for path, digest in sorted(unique)]


def _application_repository(root, *, as_of=None):
    """Read only registered, hash-bound workbenches, never scan arbitrary JSON."""
    from ..product.decision_surface import verify_current_decision_workbench
    from ..product.research_reviews import verify_human_approval_transport_provenance
    artifacts = {}
    for workbench in registered_entry_workbenches(root):
        if as_of is not None:
            _require(_clock(workbench["generated_at"]) <= _clock(as_of), "Future registered workbench")
        verify_current_decision_workbench(workbench,
            human_approval_provenance_verifier=lambda approval:
                verify_human_approval_transport_provenance(Path(root), approval))
        reader = ReadOnlyArtifactBundleRepository(workbench["artifact_bundle"])
        for row in workbench["artifact_bundle"]["artifacts"]:
            stored = reader.load_by_id(row["artifact_id"])
            _require(stored.artifact_id not in artifacts or artifacts[stored.artifact_id] == stored,
                     "Ambiguous published artifact id")
            artifacts[stored.artifact_id] = stored
    return _CandidateRepository(list(artifacts.values()))


class _CandidateRepository:
    def __init__(self, artifacts):
        self.artifacts = artifacts

    def load_by_id(self, artifact_id):
        matches = [a for a in self.artifacts if a.artifact_id == artifact_id]
        _require(len(matches) == 1, "Unavailable or ambiguous registered artifact")
        return matches[0]

    def list_versions(self, scope_type, scope_key, artifact_type, *, limit=100):
        matches = [a for a in self.artifacts if a.envelope.identity.scope_type == scope_type
                   and a.envelope.identity.scope_key == scope_key
                   and a.envelope.identity.artifact_type == artifact_type]
        return sorted(matches, key=lambda a: (a.envelope.identity.available_at, a.created_at),
                      reverse=True)[:limit]


def resolve_current_entry_consistency(repository_root, *, entry_artifact, as_of, repository=None):
    """Resolve a current registered review without replacing the owned original entry."""
    cutoff = _clock(as_of)
    original = ReadOnlyArtifactBundleRepository(export_artifact_bundle([entry_artifact]))
    entry = _artifact(entry_artifact, repository=original,
        artifact_type=ARTIFACT_ENTRY_THESIS_SNAPSHOT,
        symbol=entry_artifact.envelope.identity.scope_key, cutoff=cutoff)
    _require(isinstance(entry, EntryThesisSnapshot), "Typed original entry required")
    reader = repository if repository is not None else _application_repository(repository_root, as_of=cutoff)
    # A saturated bounded listing cannot establish the newest entry-matched version.
    versions = reader.list_versions("security", entry.symbol, ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
                                    limit=1000)
    _require(len(versions) < 1000, "Current consistency review listing is incomplete")
    candidates = {}
    for stored in versions:
        identity = stored.envelope.identity
        if _clock(identity.available_at) > cutoff or _clock(stored.created_at) > cutoff:
            continue
        review = _artifact(stored, repository=reader,
            artifact_type=ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW, symbol=entry.symbol, cutoff=cutoff)
        _require(isinstance(review, InvestmentConsistencyReview), "Typed current consistency review required")
        if review.entry_id != entry.entry_id:
            continue
        _require(review.symbol == entry.symbol and identity.as_of == review.as_of,
                 "Current consistency review identity/date mismatch")
        if review.as_of > cutoff.astimezone(_SHANGHAI).date():
            continue
        _require(bool(review.evidence_refs) and all(c.evidence_refs for c in review.comparisons),
                 "Current consistency review requires source-bound comparisons")
        validate_advisory_dependencies(symbol=entry.symbol,
            decision_as_of=cutoff.astimezone(_SHANGHAI).date(),
            recommendation_schema_version=DECISION_RECOMMENDATION_V3_SCHEMA,
            entry_thesis=entry, investment_consistency_review=review)
        key = (_clock(identity.available_at), _clock(stored.created_at), review.as_of)
        candidates.setdefault(key, {})[stored.artifact_id] = (stored, review)
    _require(bool(candidates), "Current entry-matched consistency review unavailable")
    newest = list(candidates[max(candidates)].values())
    _require(len({s.envelope.payload_sha256 for s, _ in newest}) == 1,
             "Ambiguous newest current consistency review")
    stored, review = min(newest, key=lambda row: row[0].artifact_id)
    _require(not review.blockers, "Current consistency review is blocked")
    return {"schema_version": "owned-current-consistency-resolution-v1", "action": "no_order",
            "entry_artifact": entry_artifact, "entry_thesis": entry,
            "consistency_artifact": stored, "investment_consistency_review": review,
            "entry_ref": _ref(entry_artifact), "consistency_ref": _ref(stored)}


def _binding(records, row, subject, now, entry, review, note):
    return dict(schema_version=BINDING_SCHEMA, action="no_order",
        account_scope=records[0]["body"]["account_scope"], journal_revision=len(records),
        journal_tip_sha256=records[-1]["record_sha256"],
        **{key: row[key] for key in ("fill_record_sha256", "transaction_id", "symbol", "exchange", "sleeve")},
        entry_ref=_ref(entry), consistency_ref=_ref(review), confirmation=dict(subject=subject,
            confirmed_at=now.isoformat(), note=note, explicit_original_entry_binding=True))


def list_personal_entry_thesis_candidates(service, *, repository_root, authenticated_subject, repository=None):
    subject, now = _subject(authenticated_subject), service._now()
    records = service.records()
    if not records:
        return dict(status="NOT_CONNECTED", revision=0, account_scope=None, items=[], candidates=[],
                    confirmations=[], action="no_order")
    account = records[0]["body"]["account_scope"]
    resolved = resolve_personal_entry_thesis(records=records, account_scope=account,
        expected_revision=len(records), as_of=now, authenticated_subject=subject)
    blockers = []
    if repository is None:
        try:
            repository = _application_repository(repository_root, as_of=now)
        except (ValueError, KeyError, TypeError, OSError) as error:
            blockers.append("REGISTERED_ENTRY_ARTIFACTS_UNAVAILABLE:" + type(error).__name__)
    for row in resolved["items"]:
        if repository is None or not hasattr(repository, "list_versions"):
            continue
        entries = repository.list_versions("security", row["symbol"], ARTIFACT_ENTRY_THESIS_SNAPSHOT, limit=30)
        reviews = repository.list_versions("security", row["symbol"], ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW, limit=30)
        for entry in entries:
            for review in reviews:
                modes = []
                for mode in ("CONTEMPORANEOUS", "HISTORICAL_RECONSTRUCTION"):
                    try:
                        b = _binding(records, row, subject, now, entry, review, "Candidate validation only")
                        checked = _validate_binding_contract(records=records, account_scope=account,
                            authenticated_subject=subject, expected_revision=len(records), binding_candidate=b,
                            entry_artifact=entry, consistency_artifact=review, repository=repository,
                            as_of=now, binding_mode=mode)
                        modes.append(mode)
                    except (ValueError, KeyError, TypeError, AttributeError):
                        continue
                if modes:
                    thesis = checked["entry_thesis"]
                    row["candidate_plans"].append(dict(entry_artifact_id=entry.artifact_id,
                        consistency_artifact_id=review.artifact_id, entry_ref=_ref(entry),
                        consistency_ref=_ref(review), thesis=thesis.thesis, hold_logic=thesis.hold_logic,
                        invalidation_conditions=list(thesis.breakers), binding_modes=modes,
                        source_bindings=[dict(ref) for artifact in (entry, review) for ref in artifact.envelope.evidence_refs]))
    return dict(status="AVAILABLE", revision=len(records), account_scope=account,
        items=resolved["items"], candidates=deepcopy(resolved["items"]),
        confirmations=resolved["confirmations"], blockers=blockers, action="no_order")


def _write_context(service, request, subject, fields):
    _subject(subject)
    _require(isinstance(request, Mapping) and not set(request) - fields, "Unsupported thesis request fields")
    _require(request.get("read_and_confirmed") is True, "Explicit read acknowledgement required")
    note = request.get("confirmation_note")
    _require(isinstance(note, str) and 0 < len(note.strip()) <= 8000, "Confirmation note required")
    # Include the trusted identity in the existing idempotency digest.
    return {**request, "_authenticated_subject": subject}


def confirm_personal_entry_thesis(service, request, *, authenticated_subject, repository_root, repository=None):
    trusted = _write_context(service, request, authenticated_subject, {
        "idempotency_key", "expected_revision", "fill_record_sha256", "entry_artifact_id",
        "consistency_artifact_id", "binding_mode", "reconstruction", "confirmation_note",
        "read_and_confirmed", "supersedes_record_sha256"})
    now = service._now()
    with service.journal.transaction() as records:
        existing = service._existing(records, trusted)
        if existing is not None:
            return existing
        revision = service._require_revision(records, trusted)
        _require(bool(records), "Confirmed account required")
        account = records[0]["body"]["account_scope"]
        _journal(records, account_scope=account, expected_revision=revision, as_of=now)
        replayed = service._replay(records)
        _require(replayed.pending is None and replayed.pending_policy is None, "Finish pending draft before thesis confirmation")
        rows, active, _ = _replay_confirmations(records, account_scope=account,
            authenticated_subject=authenticated_subject, as_of=now)
        matches = [row for row in rows if row["fill_record_sha256"] == request.get("fill_record_sha256")]
        _require(len(matches) == 1, "Confirmed BUY fill required")
        row = matches[0]
        _require(Decimal(row["remaining_quantity"]) > 0, "Opening fill no longer held")
        old = active.get(row["fill_record_sha256"])
        if request.get("supersedes_record_sha256") != (old["record_sha256"] if old else None):
            raise JournalConflict("THESIS_BINDING_CONFLICT", "Correction must reference active confirmation")
        body = dict(schema_version=EVENT_SCHEMA, account_scope=account,
            authenticated_subject=authenticated_subject, journal_revision=revision,
            journal_tip_sha256=records[-1]["record_sha256"],
            **{key: row[key] for key in ("fill_record_sha256", "transaction_id", "symbol", "exchange", "sleeve")},
            confirmed_at=now.isoformat(), read_and_confirmed=True,
            confirmation_note=request["confirmation_note"], binding_mode=request.get("binding_mode"),
            supersedes_record_sha256=request.get("supersedes_record_sha256"),
            original_pit_proven=False, advisory_eligible=False, action="no_order")
        if "reconstruction" in request:
            _require(body["binding_mode"] == "HISTORICAL_RECONSTRUCTION"
                     and "entry_artifact_id" not in request and "consistency_artifact_id" not in request,
                     "Narrative reconstruction cannot claim original artifacts")
            body.update(provenance="USER_NARRATIVE_RECONSTRUCTION", reconstruction=_narrative(request["reconstruction"]))
        else:
            reader = repository or _application_repository(repository_root, as_of=now)
            entry = reader.load_by_id(request["entry_artifact_id"])
            review = reader.load_by_id(request["consistency_artifact_id"])
            if not any(marker in account.upper() for marker in ("TEST_ONLY", "SIMULATED", "SYNTHETIC")):
                _require(not any(marker in artifact.envelope.run_id.upper()
                    for artifact in (entry, review) for marker in ("TEST_ONLY", "SIMULATED", "SYNTHETIC")),
                    "Test artifacts cannot bind an actual account")
            b = _binding(records, row, authenticated_subject, now, entry, review, request["confirmation_note"])
            _validate_binding_contract(records=records, account_scope=account,
                authenticated_subject=authenticated_subject, expected_revision=revision, binding_candidate=b,
                entry_artifact=entry, consistency_artifact=review, repository=reader, as_of=now,
                binding_mode=body["binding_mode"])
            body.update(provenance="REGISTERED_ARTIFACT_BINDING", binding_contract=b,
                        artifact_bundle=export_artifact_bundle([entry, review]))
        response = dict(status=CONFIRMED_KIND, revision=revision + 1, account_scope=account,
            fill_record_sha256=row["fill_record_sha256"], confirmation=deepcopy(body),
            changes_holdings=False, action="no_order")
        record = service.journal.append(kind=CONFIRMED_KIND, body=body, response=response,
            idempotency_key=_idempotency_key(trusted), request_sha256=request_digest(trusted),
            recorded_at=now, changes_holdings=False)
        return dict(record["response"]), record["record_sha256"]


def revoke_personal_entry_thesis(service, request, *, authenticated_subject):
    trusted = _write_context(service, request, authenticated_subject, {"idempotency_key", "expected_revision",
        "confirmation_record_sha256", "confirmation_note", "read_and_confirmed"})
    now = service._now()
    with service.journal.transaction() as records:
        existing = service._existing(records, trusted)
        if existing is not None:
            return existing
        revision = service._require_revision(records, trusted)
        _require(bool(records), "Confirmed account required")
        account = records[0]["body"]["account_scope"]
        _journal(records, account_scope=account, expected_revision=revision, as_of=now)
        _, active, _ = _replay_confirmations(records, account_scope=account,
            authenticated_subject=authenticated_subject, as_of=now)
        matches = [value for value in active.values()
                   if value["record_sha256"] == request.get("confirmation_record_sha256")]
        if len(matches) != 1:
            raise JournalConflict("THESIS_BINDING_CONFLICT", "No matching active confirmation")
        old = matches[0]
        body = dict(schema_version=EVENT_SCHEMA, account_scope=account,
            authenticated_subject=authenticated_subject, journal_revision=revision,
            journal_tip_sha256=records[-1]["record_sha256"],
            **{key: old[key] for key in ("fill_record_sha256", "transaction_id", "symbol", "exchange", "sleeve")},
            confirmed_at=now.isoformat(), read_and_confirmed=True,
            confirmation_note=request["confirmation_note"],
            confirmation_record_sha256=old["record_sha256"], action="no_order")
        response = dict(status=REVOKED_KIND, revision=revision + 1, account_scope=account,
            fill_record_sha256=old["fill_record_sha256"], confirmation=deepcopy(body),
            changes_holdings=False, action="no_order")
        record = service.journal.append(kind=REVOKED_KIND, body=body, response=response,
            idempotency_key=_idempotency_key(trusted), request_sha256=request_digest(trusted),
            recorded_at=now, changes_holdings=False)
        return dict(record["response"]), record["record_sha256"]


class PersonalEntryThesisService:
    """Route adapter: subject and clock come only from authenticated server context."""

    def __init__(self, journal, *, repository=None):
        self.journal, self.repository = journal, repository

    def view(self, *, repository_root, authenticated_subject, now):
        service = PrivatePortfolioService(self.journal, clock=lambda: _clock(now))
        return service.entry_thesis_candidates(repository_root=repository_root,
            authenticated_subject=authenticated_subject, repository=self.repository)

    def confirm(self, payload, *, repository_root, authenticated_subject, now):
        service = PrivatePortfolioService(self.journal, clock=lambda: _clock(now))
        try:
            return service.confirm_entry_thesis(payload, repository_root=repository_root,
                authenticated_subject=authenticated_subject, repository=self.repository)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise JournalValidationError(str(error)) from error

    def revoke(self, payload, *, authenticated_subject, now):
        service = PrivatePortfolioService(self.journal, clock=lambda: _clock(now))
        try:
            return service.revoke_entry_thesis(payload, authenticated_subject=authenticated_subject)
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise JournalValidationError(str(error)) from error


def owned_entry_context(*, records, symbol, sleeve, authenticated_subject, as_of):
    """Resolve surviving owned lots; reconstruction is visible but not advisory input."""
    result = dict(ownership_verified=False, advisory_dependencies_valid=False,
        entry_thesis_record_sha256=None, bindings=[], blockers=[], action="no_order")
    if not authenticated_subject:
        result["blockers"] = ["AUTHENTICATED_PERSONAL_ENTRY_SUBJECT_REQUIRED"]
        return result
    if not records:
        result["blockers"] = ["PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED"]
        return result
    account = records[0]["body"]["account_scope"]
    result.update(account_scope=account, journal_revision=len(records), symbol=symbol, sleeve=sleeve,
        namespace="TEST_ONLY" if any(marker in account.upper() for marker in
            ("TEST_ONLY", "SIMULATED", "SYNTHETIC")) else "ACTUAL")
    resolved = resolve_personal_entry_thesis(records=records, account_scope=account,
        expected_revision=len(records), as_of=as_of, authenticated_subject=authenticated_subject)
    rows = [row for row in resolved["items"] if row["symbol"] == symbol and row["sleeve"] == sleeve
            and Decimal(row["remaining_quantity"]) > 0]
    _, lots = _sources(records)
    baseline_unbound = any(lot["fill_hash"] is None and lot["symbol"] == symbol and lot["sleeve"] == sleeve
                           and lot["remaining"] > 0 for lot in lots)
    if not rows or baseline_unbound or any(row["current_binding"] is None for row in rows):
        result["blockers"] = ["PERSONAL_ENTRY_THESIS_CONFIRMATION_REQUIRED"]
        return result
    bindings = [row["current_binding"] for row in rows]
    result.update(ownership_verified=True, bindings=bindings,
        entry_thesis_record_sha256=bindings[-1]["record_sha256"],
        held_quantity=str(sum((Decimal(row["remaining_quantity"]) for row in rows), Decimal(0))))
    if any(b["binding_mode"] != "CONTEMPORANEOUS" or b["provenance"] != "REGISTERED_ARTIFACT_BINDING"
           for b in bindings):
        result["blockers"] = ["HISTORICAL_RECONSTRUCTION_NOT_ORIGINAL_PIT_ENTRY"]
        return result
    result["advisory_dependencies_valid"] = True
    entries, reviews = [], []
    for binding in bindings:
        reader = ReadOnlyArtifactBundleRepository(binding["artifact_bundle"])
        contract = binding["binding_contract"]
        entries.append(reader.load_by_id(contract["entry_ref"]["artifact_id"]))
        reviews.append(reader.load_by_id(contract["consistency_ref"]["artifact_id"]))
    if len({entry.artifact_id for entry in entries}) != 1:
        result.update(advisory_dependencies_valid=False,
            blockers=["MULTIPLE_OWNED_ENTRY_THESES_REQUIRE_SEPARATE_REVIEW"])
        return result
    result.update(entry_artifact=entries[-1], consistency_artifact=reviews[-1],
        entry_thesis=decode_artifact(ARTIFACT_ENTRY_THESIS_SNAPSHOT, parse_stored_artifact_payload(entries[-1])),
        investment_consistency_review=decode_artifact(ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW,
            parse_stored_artifact_payload(reviews[-1])))
    return result
