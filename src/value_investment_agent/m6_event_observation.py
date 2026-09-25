"""Offline lineage check for a future Shadow event observation candidate.

Cryptographic consistency is not proof of a real production observation.
This module never grants operational event credit or authorizes an order.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping
from urllib.parse import urlsplit

from .event_materiality import event_materiality_review_from_payload
from .m5_event_run import M5EventRunReceipt
from .m6_shadow_receipts import verify_shadow_bundle


SCHEMA = "m6-shadow-event-observation-v1"
_FIELDS = frozenset({
    "schema_version", "action", "symbol", "event_id", "source_event_id",
    "materiality_decision_id", "source_sha256", "source_url",
    "m5_review_file_sha256", "m5_receipt_file_sha256", "m5_receipt_id",
    "m5_state_sha256", "m6_authorization_sha256", "m6_run_id",
    "session_date", "observed_at",
})


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha(payload: Mapping[str, Any]) -> str:
    return _sha(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8"))


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw, object_pairs_hook=_unique_pairs)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Event observation time must have a timezone")
    return parsed


def verify_event_observation_candidate(
    *, source_bytes: bytes, materiality_review_bytes: bytes,
    m5_receipt_bytes: bytes, observation_bytes: bytes,
    shadow_bundle: Mapping[str, Any], trust_root: Mapping[str, str],
    schedule: Mapping[str, Any], cutoff: datetime,
    expected_materiality_review_sha256: str, expected_m5_receipt_sha256: str,
    approved_source_hosts: frozenset[str],
) -> dict[str, Any]:
    """Check exact source-to-Shadow lineage, returning zero operational credit."""
    observation = _json_object(observation_bytes, "Observation")
    if (set(observation) != _FIELDS or observation["schema_version"] != SCHEMA
            or observation["action"] != "no_order"):
        raise ValueError("Event observation schema or action differs")
    if (_sha(materiality_review_bytes) != expected_materiality_review_sha256
            or _sha(m5_receipt_bytes) != expected_m5_receipt_sha256):
        raise ValueError("M5 evidence does not match externally supplied expected hashes")
    review_payload = json.loads(materiality_review_bytes,
                                object_pairs_hook=_unique_pairs)
    if not isinstance(review_payload, list) or len(review_payload) != 1:
        raise ValueError("Exactly one materiality review is required")
    review = event_materiality_review_from_payload(review_payload[0])
    if review.as_policy() != review_payload[0] or review.action != "no_order":
        raise ValueError("Materiality review is not canonical no_order evidence")
    wrapper = _json_object(m5_receipt_bytes, "M5 receipt")
    receipt = M5EventRunReceipt.from_payload(wrapper)
    if receipt.namespace != "ACTUAL" or receipt.action != "no_order":
        raise ValueError("Event observation requires committed ACTUAL M5 receipt")

    decisions = [item for item in review.decisions
                 if item.event_decision_id == observation["materiality_decision_id"]]
    events = [item for item in receipt.active_events
              if item.event_id == observation["event_id"]]
    current_ingest = [item for item in receipt.ingest_results
                      if item.event is not None and item.event.event_id == observation["event_id"]
                      and item.status == "ACCEPTED"]
    if len(decisions) != 1 or len(events) != 1:
        raise ValueError("Event or materiality decision is missing or duplicated")
    decision, event = decisions[0], events[0]
    source_url = urlsplit(str(decision.source_ref.get("source_url", "")))
    if (decision.human_decision != "MATERIAL_REQUIRES_RECALCULATION"
            or decision.reviewed_at is None
            or not source_bytes.startswith(b"%PDF-")
            or source_url.scheme != "https" or source_url.hostname not in approved_source_hosts
            or source_url.username is not None or source_url.password is not None
            or source_url.port not in (None, 443) or bool(source_url.fragment)
            or not source_url.path.lower().endswith(".pdf")
            or observation["symbol"] != decision.symbol or event.symbol != decision.symbol
            or event.source_event_id != "materiality-review:" + decision.event_decision_id
            or observation["source_event_id"] != event.source_event_id
            or observation["source_sha256"] != decision.source_sha256
            or decision.source_sha256 != _sha(source_bytes)
            or event.current_state.get("source_sha256") != decision.source_sha256
            or event.current_state.get("source_ref_id") != decision.source_ref.get("id")
            or event.current_state.get("source_ref_sha256") != decision.source_sha256
            or observation["source_url"] != decision.source_ref.get("source_url")
            or decision.source_ref.get("source_status") != "SOURCE_ARCHIVED"
            or len(current_ingest) != 1
            or observation["event_id"] not in receipt.checkpoint.ingested_event_ids
            or observation["m5_review_file_sha256"] != _sha(materiality_review_bytes)
            or observation["m5_receipt_file_sha256"] != _sha(m5_receipt_bytes)
            or observation["m5_receipt_id"] != receipt.receipt_id
            or observation["m5_state_sha256"] != receipt.state_sha256):
        raise ValueError("Original, materiality decision and M5 event lineage differ")

    session_hashes = verify_shadow_bundle(shadow_bundle, trust_root, schedule, cutoff)
    matches = [item["session"]["payload"] for item in shadow_bundle["sessions"]
               if item["session"]["payload"]["run_id"] == observation["m6_run_id"]
               and item["session"]["payload"]["session_date"] == observation["session_date"]]
    if len(matches) != 1:
        raise ValueError("Event observation has no unique Shadow run")
    session = matches[0]
    authorization = shadow_bundle["authorization"]["payload"]
    observed_at = _time(observation["observed_at"])
    prior_dates = sorted(date.fromisoformat(item["session_date"])
                         for item in schedule["sessions"]
                         if item["session_date"] < observation["session_date"])
    current_date = date.fromisoformat(observation["session_date"])
    if not prior_dates or current_date - prior_dates[-1] > timedelta(days=14):
        raise ValueError("Prior official session is required to bound event arrival")
    prior_close = datetime.combine(prior_dates[-1], time(15, 5),
                                   tzinfo=timezone(timedelta(hours=8)))
    if (observation["m6_authorization_sha256"] != _canonical_sha(
            shadow_bundle["authorization"])
            or observation["session_date"] not in session_hashes
            or session["artifact_sha256"] != _sha(observation_bytes)
            or not (prior_close < decision.published_at
                    <= decision.reviewed_at <= receipt.generated_at
                    and _time(session["started_at"]) <= receipt.generated_at <= observed_at
                    <= _time(session["completed_at"]))
            or decision.published_at < _time(authorization["valid_from"])):
        raise ValueError("Event is retrospective or not bound to the authorized run artifact")
    return {
        "schema_version": SCHEMA,
        "offline_candidate_valid": True,
        "operational_event_proven": False,
        "verified_real_event_count": 0,
        "event_id": event.event_id,
        "session_date": observation["session_date"],
        "source_sha256": _sha(source_bytes),
        "observation_sha256": _sha(observation_bytes),
        "session_receipt_sha256": session_hashes[observation["session_date"]],
        "action": "no_order",
    }
