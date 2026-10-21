"""Read-only personal entry binding contract, without a journal write authority.

Callers authenticate the account/subject and read records through PrivateJournal.
Hashes establish integrity, never authentication. Candidate confirmation fields
are validated here but cannot substitute for a durable authenticated user event.
The current journal has no such event; resolution therefore remains CODE_GAP.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence
from zoneinfo import ZoneInfo

from .private_portfolio_service import PrivateJournal, _fill_from_body
from ...domain.decision.advisory_dependency_admission import validate_advisory_dependencies
from ...domain.decision.decision_recommendation import DECISION_RECOMMENDATION_V3_SCHEMA
from ...investment_decision import EntryThesisSnapshot, InvestmentConsistencyReview
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
    """Validate a proposed explicit confirmation against authenticated journal facts.

    This is a preparation interface for a future confirmation use case. It does
    not authenticate supplied fields, persist a confirmation, assert ownership,
    check current lot survival, or produce advisory/trading admission. Invalid
    content raises ValueError; missing identities/fields fail closed.
    """
    try:
        return _validate_binding_contract(records=records, account_scope=account_scope,
            authenticated_subject=authenticated_subject, expected_revision=expected_revision,
            binding_candidate=binding_candidate, entry_artifact=entry_artifact,
            consistency_artifact=consistency_artifact, repository=repository, as_of=as_of)
    except (KeyError, TypeError, AttributeError, ArithmeticError) as error:
        raise ValueError("Invalid personal entry binding input or unavailable registered artifact") from error


def _validate_binding_contract(*, records, account_scope, authenticated_subject, expected_revision,
        binding_candidate, entry_artifact, consistency_artifact, repository, as_of):
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
    entry = _artifact(entry_artifact, repository=repository,
        artifact_type=ARTIFACT_ENTRY_THESIS_SNAPSHOT, symbol=b["symbol"], cutoff=fill_confirmed)
    review = _artifact(consistency_artifact, repository=repository,
        artifact_type=ARTIFACT_INVESTMENT_CONSISTENCY_REVIEW, symbol=b["symbol"], cutoff=confirmed)
    _require(isinstance(entry, EntryThesisSnapshot) and isinstance(review, InvestmentConsistencyReview),
             "Existing entry/consistency domain objects required")
    _require(b["entry_ref"] == _ref(entry_artifact) and b["consistency_ref"] == _ref(consistency_artifact),
             "Exact artifact ID/hash/available_at binding required")
    _require(entry.entry_date.isoformat() == fill["trade_date"]
             and entry.entry_price == Decimal(fill["price_cny"]), "Entry date/price differs from original fill")
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
) -> dict:
    """Current production read contract: no supported durable binding event exists.

    Do not search public artifacts or recording-time snapshots for ownership.
    A future journal confirmation adapter must explicitly replace this boundary.
    """
    _journal(records, account_scope=account_scope, expected_revision=expected_revision, as_of=as_of)
    return {"status": "CODE_GAP", "gap_category": "CODE_GAP",
        "code": MISSING_CONFIRMATION_INTERFACE, "journal_revision": expected_revision,
        "required_interface": "Authenticated journal confirmation event binding account/subject, "
            "revision/tip, confirmed BUY hash/transaction/security/sleeve and exact registered "
            "entry/consistency artifact ID/hash/available_at; journal writer and reader must support it.",
        "action": "no_order", "ownership_verified": False, "formal_eligibility": False,
        "personal_sell_permission": False, "position_guidance": None}
