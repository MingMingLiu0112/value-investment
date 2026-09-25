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

from .disclosures import PDF_BASE_URL
from .event_materiality import event_materiality_review_from_payload
from .m5_event_run import M5EventRunReceipt
from .m6_exchange_sessions import completed_exchange_sessions
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


def _verify_cninfo_index(raw: bytes, expected_sha256: str, review: Any,
                         decision: Any) -> None:
    index = _json_object(raw, "CNINFO index")
    refs = [item for item in review.evidence_refs
            if item.get("id") == f"{review.symbol}-cninfo-index"]
    if (len(refs) != 1 or _sha(raw) != expected_sha256
            or review.scan_sha256 != expected_sha256
            or refs[0].get("sha256") != expected_sha256
            or refs[0].get("source_url") != "https://www.cninfo.com.cn/new/hisAnnouncement/query"
            or index.get("url") != refs[0]["source_url"]):
        raise ValueError("CNINFO index is not bound to the materiality review")
    params = index.get("parameters") or {}
    rows = index.get("announcements")
    if (not isinstance(params, dict) or not isinstance(rows, list)
            or params.get("stock") != f"{review.symbol},gssh0{review.symbol}"
            or params.get("column") != "sse"
            or params.get("tabName") != "fulltext"
            or params.get("pageSize") != "100"
            or params.get("isHLtitle") != "true"
            or any(params.get(key) != "" for key in (
                "searchkey", "secid", "plate", "category", "trade",
                "sortName", "sortType"))
            or params.get("seDate") != f"{review.scan_from}~{review.scan_to}"
            or type(index.get("total_announcements")) is not int
            or index["total_announcements"] != len(rows)
            or refs[0].get("announcement_count") != len(rows)
            or any(not isinstance(item, dict) or item.get("secCode") != review.symbol
                   for item in rows)):
        raise ValueError("CNINFO index coverage or symbol differs")
    ids = [str(item.get("announcementId")) for item in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("CNINFO index contains duplicate announcement IDs")
    matches = [item for item in rows
               if str(item["announcementId"]) == decision.announcement_id]
    if len(matches) != 1:
        raise ValueError("Materiality decision has no unique CNINFO index row")
    row = matches[0]
    milliseconds = row.get("announcementTime")
    if type(milliseconds) is not int:
        raise ValueError("CNINFO announcement timestamp must be Unix milliseconds")
    published = datetime.fromtimestamp(milliseconds / 1000,
                                       timezone(timedelta(hours=8)))
    adjunct = str(row.get("adjunctUrl") or "").lstrip("/")
    pdf_url = PDF_BASE_URL + adjunct
    expected_adjunct = f"finalpage/{published.date()}/{decision.announcement_id}.PDF"
    if (not review.scan_from <= published.date() <= review.scan_to
            or row.get("adjunctType") != "PDF"
            or row.get("announcementTitle") != decision.title
            or published != decision.published_at
            or adjunct.lower() != expected_adjunct.lower()
            or pdf_url != decision.source_ref.get("source_url")):
        raise ValueError("CNINFO index row differs from materiality decision")


def verify_event_observation_candidate(
    *, source_bytes: bytes, source_index_bytes: bytes,
    materiality_review_bytes: bytes,
    m5_receipt_bytes: bytes, observation_bytes: bytes,
    shadow_bundle: Mapping[str, Any], trust_root: Mapping[str, str],
    calendar_evidence: Mapping[str, Any], cutoff: datetime,
    expected_materiality_review_sha256: str, expected_m5_receipt_sha256: str,
    expected_source_index_sha256: str,
    expected_calendar_source_sha256: tuple[str, ...],
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
    _verify_cninfo_index(source_index_bytes, expected_source_index_sha256,
                         review, decision)
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

    documents = calendar_evidence.get("documents")
    if (not isinstance(documents, list) or not documents
            or tuple(sorted(item.get("sha256", "") for item in documents))
            != tuple(sorted(expected_calendar_source_sha256))
            or calendar_evidence.get("observation_cutoff") != cutoff.isoformat()):
        raise ValueError("Calendar documents lack separately supplied source hashes or cutoff")
    schedule = completed_exchange_sessions(
        str(calendar_evidence.get("venue")), documents, cutoff)
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
        "source_index_sha256": _sha(source_index_bytes),
        "observation_sha256": _sha(observation_bytes),
        "session_receipt_sha256": session_hashes[observation["session_date"]],
        "action": "no_order",
    }
