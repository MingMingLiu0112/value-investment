"""Resolve sealed owned-entry research references, never grant trade authority.

The caller supplies an authenticated, journal-replayed owned context. This adapter
cross-checks its sealed artifacts against exact confirmed fills; hashes alone do
not authenticate a journal or establish execution-time knowledge.
"""
from datetime import datetime
from hashlib import sha256
from decimal import Decimal

from ..decision.artifact_bundle import ReadOnlyArtifactBundleRepository
from ..hotspot.current_case_review import inspect_current_price_case
from ..hotspot.lifecycle_review import build_hotspot_lifecycle_review
from ..hotspot.price_action_case import project_current_price_action_plan
from ...domain.portfolio.dual_sleeve_records import canonical_bytes
from ...research_artifacts import ARTIFACT_ENTRY_THESIS_SNAPSHOT, parse_stored_artifact_payload
from ...research_artifact_codecs import decode_artifact
from ...investment_decision import ENTRY_TYPE_ACTUAL


ORIGINAL_CASE_ROLE = "ORIGINAL_HOTSPOT_CASE"


def _require(condition, reason):
    if not condition:
        raise ValueError(reason)


def _time(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    _require(isinstance(stamp, datetime) and stamp.utcoffset() is not None,
             "AWARE_TIME_REQUIRED")
    return stamp


def _digest(value, field):
    return sha256(canonical_bytes({k: v for k, v in value.items() if k != field})).hexdigest()


def _one(*, root, context, binding, records, current_plan, now):
    contract = binding["binding_contract"]
    symbol = context["symbol"]
    _require(binding["provenance"] == "REGISTERED_ARTIFACT_BINDING"
             and binding["binding_mode"] == "CONTEMPORANEOUS", "ORIGINAL_BINDING_REQUIRED")
    _require(contract["action"] == "no_order"
             and contract["account_scope"] == context["account_scope"], "CONTEXT_IDENTITY_MISMATCH")
    for key in ("symbol", "sleeve", "exchange", "transaction_id", "fill_record_sha256"):
        _require(binding[key] == contract[key], "SEALED_BINDING_MISMATCH")
    _require(contract["symbol"] == symbol and contract["sleeve"] == "HOTSPOT_SATELLITE"
             and context["sleeve"] == contract["sleeve"], "CONTEXT_IDENTITY_MISMATCH")
    matches = [r for r in records if r.get("record_sha256") == contract["fill_record_sha256"]]
    _require(len(matches) == 1, "EXACT_CONFIRMED_FILL_REQUIRED")
    record = matches[0]
    _require(record["kind"] == "FILL_CONFIRMED"
             and _digest(record, "record_sha256") == record["record_sha256"], "FILL_HASH_MISMATCH")
    fill = record["body"]["fill"]
    _require(fill["side"] == "BUY", "ORIGINAL_BUY_REQUIRED")
    for key in ("symbol", "sleeve", "exchange", "transaction_id"):
        _require(fill[key] == contract[key], "FILL_IDENTITY_MISMATCH")
    reader = ReadOnlyArtifactBundleRepository(binding["artifact_bundle"])
    artifact = reader.load_by_id(contract["entry_ref"]["artifact_id"])
    identity = artifact.envelope.identity
    _require(identity.scope_type == "security" and identity.scope_key == symbol
             and identity.artifact_type == ARTIFACT_ENTRY_THESIS_SNAPSHOT, "ENTRY_IDENTITY_MISMATCH")
    _require(contract["entry_ref"] == dict(artifact_id=artifact.artifact_id,
        payload_sha256=artifact.envelope.payload_sha256, available_at=identity.available_at.isoformat()),
        "ENTRY_REFERENCE_MISMATCH")
    _require(context.get("entry_artifact") == artifact, "CONTEXT_ENTRY_MISMATCH")
    entry = decode_artifact(ARTIFACT_ENTRY_THESIS_SNAPSHOT, parse_stored_artifact_payload(artifact))
    _require(entry.symbol == symbol and entry.entry_type == ENTRY_TYPE_ACTUAL
             and entry.entry_date.isoformat() == fill["trade_date"]
             and entry.entry_price == Decimal(fill["price_cny"]), "ENTRY_FILL_MISMATCH")
    _require(context.get("entry_thesis") == entry, "CONTEXT_ENTRY_MISMATCH")
    refs = [ref for ref in artifact.envelope.evidence_refs if ref.get("role") == ORIGINAL_CASE_ROLE]
    _require(len(refs) == 1, "UNIQUE_ORIGINAL_CASE_REFERENCE_REQUIRED")
    ref = refs[0]
    evaluated = _time(ref["evaluated_at"])
    snapshot = fill["judgment_snapshot"]
    _require(snapshot["schema_version"] == "private-recording-time-judgment-snapshot-v1"
             and snapshot["action"] == "no_order"
             and snapshot["snapshot_sha256"] == _digest(snapshot, "snapshot_sha256"),
             "SNAPSHOT_HASH_MISMATCH")
    _require(snapshot["scope"] == "IMMUTABLE_PUBLICATION_AT_RECORDING_TIME_NOT_PROVEN_PRETRADE_KNOWLEDGE"
             and snapshot["trade_time_availability_proven"] is False, "SNAPSHOT_SCOPE_MISMATCH")
    plan = snapshot["plan"]
    _require(snapshot["decision_id"] == fill["decision_id"] == "hotspot-" + symbol
             and snapshot["research_version"] == fill["research_version"] == plan["research_version"]
             and plan["symbol"] == symbol and plan["action"] == "no_order", "SNAPSHOT_IDENTITY_MISMATCH")
    original_binding = dict(path=ref["path"], sha256=ref["sha256"])
    _require(original_binding == dict(path=plan["case_path"], sha256=plan["case_sha256"])
             and ref["rule_version"] == plan["model_or_rule_version"], "ORIGINAL_CASE_MISMATCH")
    if "evaluated_at" in plan:
        _require(_time(plan["evaluated_at"]) == evaluated, "EVALUATION_TIME_MISMATCH")
    recorded = _time(snapshot["recorded_at"])
    confirmed = _time(record["body"]["confirmation"]["confirmed_at"])
    _require(evaluated <= _time(identity.available_at) <= confirmed
             and evaluated <= recorded <= confirmed <= _time(record["recorded_at"]) <= now
             and evaluated <= _time(artifact.created_at) <= confirmed
             and _time(entry.confirmed_at) <= confirmed
             and evaluated <= _time(entry.confirmed_at)
             and confirmed <= _time(binding["confirmed_at"]) <= now,
             "ENTRY_TIME_MISMATCH")
    _require(_time(contract["confirmation"]["confirmed_at"]) == _time(binding["confirmed_at"]),
             "BINDING_TIME_MISMATCH")
    original = inspect_current_price_case(root=root, symbol=symbol,
        case_binding=original_binding, now=evaluated)
    _require(original["data_status"] == "CURRENT" and original["source_integrity"] == "VERIFIED",
             "ORIGINAL_SOURCE_NOT_REPLAYABLE")
    replayed = project_current_price_action_plan(original["case"])
    _require(replayed["model_or_rule_version"] == ref["rule_version"], "ORIGINAL_RULE_MISMATCH")
    _require(current_plan["symbol"] == symbol and current_plan["action"] == "no_order",
             "CURRENT_PLAN_IDENTITY_MISMATCH")
    current_binding = dict(path=current_plan["case_path"], sha256=current_plan["case_sha256"])
    current = inspect_current_price_case(root=root, symbol=symbol,
        case_binding=current_binding, now=now)
    _require(current["data_status"] == "CURRENT", "CURRENT_SOURCE_NOT_REPLAYABLE")
    _require(project_current_price_action_plan(current["case"])["model_or_rule_version"]
             == current_plan["model_or_rule_version"], "CURRENT_RULE_MISMATCH")
    review = build_hotspot_lifecycle_review(root=root, symbol=symbol,
        current_case_binding=current_binding,
        entry_case_binding=original_binding, entry_at=evaluated, now=now)
    return dict(entry_id=entry.entry_id, entry_artifact_id=artifact.artifact_id,
        fill_record_sha256=record["record_sha256"], original_case_binding=original_binding,
        original_evaluated_at=evaluated.isoformat(), snapshot_recorded_at=recorded.isoformat(),
        trade_date=fill["trade_date"], execution_at=None,
        scope="ORIGINAL_RESEARCH_REFERENCE_NOT_EXECUTION_CONTINUITY", research_reference=review,
        status="NOT_ASSESSABLE", source_reference_status="SOURCE_REPLAYED",
        blockers=["EXACT_EXECUTION_TIME_NOT_PROVEN"], pretrade_proven=False,
        personal_add_permission=False, formal_eligibility=False, action="no_order")


def resolve_owned_hotspot_lifecycle(*, root, context, confirmed_fill_records, current_plan, now):
    """Return per-fill research references from a previously verified owned context.

No raw journal access or mutable candidate lookup occurs. The input context must
come from owned_entry_context, not an HTTP body. Execution-time continuity remains
unproven even if a caller supplies an extra execution timestamp.
    """
    result = dict(status="NOT_ASSESSABLE", ownership_verified=False, items=[], blockers=[],
        pretrade_proven=False, personal_add_permission=False, formal_eligibility=False,
        position_guidance=None, action="no_order")
    try:
        now = _time(now)
        _require(context.get("ownership_verified") is True and context.get("action") == "no_order",
                 "VERIFIED_OWNED_CONTEXT_REQUIRED")
        parts = context.get("entry_contexts") or [context]
        _require(bool(parts) and all(part.get("bindings") for part in parts), "OWNED_BINDINGS_REQUIRED")
        seen = set()
        for part in parts:
            _require(all(part.get(key) == context.get(key) for key in
                ("account_scope", "symbol", "sleeve")), "CROSS_ENTRY_CONTEXT_MISMATCH")
            for binding in part["bindings"]:
                fill_hash = binding["fill_record_sha256"]
                _require(fill_hash not in seen, "DUPLICATE_OWNED_FILL")
                seen.add(fill_hash)
                try:
                    item = _one(root=root, context=part, binding=binding,
                        records=confirmed_fill_records, current_plan=current_plan, now=now)
                except (ValueError, KeyError, TypeError, AttributeError, ArithmeticError, OSError) as error:
                    item = dict(status="NOT_ASSESSABLE", fill_record_sha256=fill_hash,
                        source_reference_status="UNVERIFIED", research_reference=None,
                        blockers=[str(error)], personal_add_permission=False,
                        formal_eligibility=False, pretrade_proven=False, action="no_order")
                result["items"].append(item)
        # Ownership is inherited only; this adapter never independently certifies it.
        result["ownership_verified"] = True
        result["ownership_scope"] = "INHERITED_AUTHENTICATED_JOURNAL_CONTEXT"
        result["blockers"] = list(dict.fromkeys(b for item in result["items"] for b in item["blockers"]))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        result.update(items=[], blockers=[str(error)])
    return result
