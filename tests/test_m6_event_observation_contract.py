"""Portable synthetic tests for the M6 event lineage boundary."""
import base64
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from types import SimpleNamespace

import pytest

from value_investment_agent import m6_event_observation as observation
from value_investment_agent.quote_sessions import (
    SSE_2026_CLOSURE_NOTICE_URL, SSE_2026_NOTICE_MARKERS,
)


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _fixture(monkeypatch, *, published_at="2026-09-24T09:00:00+08:00",
             index_mutate=None):
    source = b"%PDF-synthetic-source"
    review_payload = {"synthetic_review": True}
    review_bytes = _bytes([review_payload])
    receipt_bytes = _bytes({"synthetic_receipt": True})
    published = datetime.fromisoformat(published_at)
    adjunct = f"finalpage/{published.date()}/123.PDF"
    source_url = "https://static.cninfo.com.cn/" + adjunct
    index = {
        "url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
        "parameters": {"stock": "600519,gssh0600519", "column": "sse",
                       "tabName": "fulltext", "pageSize": "100",
                       "isHLtitle": "true", "searchkey": "", "secid": "",
                       "plate": "", "category": "", "trade": "",
                       "sortName": "", "sortType": "",
                       "seDate": "2026-09-23~2026-09-24"},
        "total_announcements": 1,
        "announcements": [{"secCode": "600519", "announcementId": "123",
                           "announcementTitle": "Synthetic filing",
                           "announcementTime": int(published.timestamp() * 1000),
                           "adjunctType": "PDF", "adjunctUrl": adjunct}],
    }
    if index_mutate:
        index_mutate(index)
    index_bytes = _bytes(index)
    decision = SimpleNamespace(
        event_decision_id="decision-1", human_decision="MATERIAL_REQUIRES_RECALCULATION",
        reviewed_at=datetime.fromisoformat("2026-09-24T09:30:00+08:00"),
        published_at=published, symbol="600519", announcement_id="123",
        title="Synthetic filing",
        source_sha256=_sha(source), source_ref={
            "id": "source-1", "source_status": "SOURCE_ARCHIVED",
            "source_url": source_url},
    )
    event = SimpleNamespace(event_id="m5-event-1", symbol="600519",
                            source_event_id="materiality-review:decision-1",
                            current_state={"source_sha256": _sha(source),
                                           "source_ref_id": "source-1",
                                           "source_ref_sha256": _sha(source)})
    review = SimpleNamespace(decisions=(decision,), action="no_order",
                             evidence_refs=({"id": "600519-cninfo-index",
                                             "sha256": _sha(index_bytes),
                                             "source_url": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                                             "announcement_count": 1},),
                             scan_sha256=_sha(index_bytes), symbol="600519",
                             scan_from=datetime.fromisoformat("2026-09-23").date(),
                             scan_to=datetime.fromisoformat("2026-09-24").date(),
                             as_policy=lambda: review_payload)
    receipt = SimpleNamespace(namespace="ACTUAL", action="no_order",
                              active_events=(event,), receipt_id="m5-receipt-1",
                              state_sha256="a" * 64,
                              ingest_results=(SimpleNamespace(event=event, status="ACCEPTED"),),
                              checkpoint=SimpleNamespace(ingested_event_ids=(event.event_id,)),
                              generated_at=datetime.fromisoformat(
                                  "2026-09-24T10:00:00+08:00"))
    monkeypatch.setattr(observation, "event_materiality_review_from_payload",
                        lambda _: review)
    monkeypatch.setattr(observation.M5EventRunReceipt, "from_payload",
                        lambda _: receipt)
    monkeypatch.setattr(observation, "verify_shadow_bundle",
                        lambda *args: {"2026-09-24": "c" * 64})
    auth = {"payload": {"valid_from": "2026-09-23T08:00:00+08:00"}}
    row = {
        "schema_version": observation.SCHEMA, "action": "no_order", "symbol": "600519",
        "event_id": event.event_id, "source_event_id": event.source_event_id,
        "materiality_decision_id": decision.event_decision_id,
        "source_sha256": _sha(source), "source_url": decision.source_ref["source_url"],
        "m5_review_file_sha256": _sha(review_bytes),
        "m5_receipt_file_sha256": _sha(receipt_bytes),
        "m5_receipt_id": receipt.receipt_id, "m5_state_sha256": receipt.state_sha256,
        "m6_authorization_sha256": observation._canonical_sha(auth),
        "m6_run_id": "shadow-1", "session_date": "2026-09-24",
        "observed_at": "2026-09-24T15:08:00+08:00",
    }
    raw = _bytes(row)
    session = {"payload": {
        "run_id": "shadow-1", "session_date": "2026-09-24",
        "artifact_sha256": _sha(raw),
        "started_at": "2026-09-24T09:00:00+08:00",
        "completed_at": "2026-09-24T15:10:00+08:00",
    }}
    raw_calendar = "\n".join(SSE_2026_NOTICE_MARKERS).encode("utf-8")
    document = {"source_url": SSE_2026_CLOSURE_NOTICE_URL,
                "fetched_at": "2026-09-24T06:30:00+00:00",
                "raw_base64": base64.b64encode(raw_calendar).decode(),
                "sha256": _sha(raw_calendar)}
    cutoff = datetime.fromisoformat("2026-09-24T15:30:00+08:00")
    evidence = dict(source_bytes=source, source_index_bytes=index_bytes,
                    materiality_review_bytes=review_bytes,
                    m5_receipt_bytes=receipt_bytes, observation_bytes=raw,
                    shadow_bundle={"authorization": auth,
                                   "sessions": [{"session": session}]},
                    trust_root={}, calendar_evidence={
                        "venue": "SSE", "documents": [document],
                        "observation_cutoff": cutoff.isoformat()},
                    expected_materiality_review_sha256=_sha(review_bytes),
                    expected_m5_receipt_sha256=_sha(receipt_bytes),
                    expected_source_index_sha256=_sha(index_bytes),
                    expected_calendar_source_sha256=(document["sha256"],),
                    approved_source_hosts=frozenset({"static.cninfo.com.cn"}),
                    cutoff=cutoff)
    return evidence, row


def _replace_row(evidence, row):
    updated = dict(evidence)
    updated["observation_bytes"] = _bytes(row)
    updated["shadow_bundle"] = json.loads(json.dumps(evidence["shadow_bundle"]))
    updated["shadow_bundle"]["sessions"][0]["session"]["payload"][
        "artifact_sha256"] = _sha(updated["observation_bytes"])
    return updated


def test_lineage_candidate_never_grants_operational_credit(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    result = observation.verify_event_observation_candidate(**evidence)
    assert result["offline_candidate_valid"] is True
    assert result["operational_event_proven"] is False
    assert result["verified_real_event_count"] == 0
    assert result["action"] == "no_order"


@pytest.mark.parametrize("field,value", [
    ("event_id", "other-event"),
    ("source_event_id", "materiality-review:other"),
    ("materiality_decision_id", "other-decision"),
    ("m5_receipt_file_sha256", "f" * 64),
    ("m6_run_id", "other-run"),
    ("observed_at", "2026-09-24T15:12:00+08:00"),
])
def test_fully_rehashed_id_run_or_time_mismatch_fails(monkeypatch, field, value):
    evidence, row = _fixture(monkeypatch)
    row[field] = value
    with pytest.raises(ValueError):
        observation.verify_event_observation_candidate(**_replace_row(evidence, row))


def test_source_bytes_and_historical_publication_fail(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError):
        observation.verify_event_observation_candidate(**{
            **evidence, "source_bytes": b"%PDF-swapped"})
    old, _ = _fixture(monkeypatch, published_at="2026-09-23T15:00:00+08:00")
    with pytest.raises(ValueError, match="retrospective"):
        observation.verify_event_observation_candidate(**old)


def test_external_pins_and_source_host_are_required(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError, match="expected hashes"):
        observation.verify_event_observation_candidate(**{
            **evidence, "expected_m5_receipt_sha256": "f" * 64})
    with pytest.raises(ValueError, match="lineage"):
        observation.verify_event_observation_candidate(**{
            **evidence, "approved_source_hosts": frozenset({"other.test"})})


def test_wrong_calendar_pin_cannot_define_arrival_window(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    with pytest.raises(ValueError, match="Calendar documents"):
        observation.verify_event_observation_candidate(**{
            **evidence, "expected_calendar_source_sha256": ("f" * 64,)})


@pytest.mark.parametrize("mutate", [
    lambda index: index["announcements"][0].update(announcementId="999"),
    lambda index: index["announcements"][0].update(announcementTitle="Other filing"),
    lambda index: index["announcements"][0].update(announcementTime=1),
    lambda index: index["announcements"][0].update(adjunctUrl="finalpage/2026-09-24/999.PDF"),
    lambda index: index.update(total_announcements=2),
    lambda index: index["announcements"].append(dict(index["announcements"][0])),
])
def test_coherently_rehashed_index_row_mismatch_fails(monkeypatch, mutate):
    evidence, _ = _fixture(monkeypatch, index_mutate=mutate)
    with pytest.raises(ValueError, match="CNINFO index|Materiality decision"):
        observation.verify_event_observation_candidate(**evidence)


def test_duplicate_index_key_and_forged_calendar_bytes_fail(monkeypatch):
    evidence, _ = _fixture(monkeypatch)
    duplicate = evidence["source_index_bytes"].replace(
        b'"url":"https://www.cninfo.com.cn/new/hisAnnouncement/query"',
        b'"url":"https://www.cninfo.com.cn/new/hisAnnouncement/query",'
        b'"url":"https://www.cninfo.com.cn/new/hisAnnouncement/query"')
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        observation.verify_event_observation_candidate(**{
            **evidence, "source_index_bytes": duplicate})

    forged = deepcopy(evidence["calendar_evidence"])
    raw = b"forged closure notice"
    forged["documents"][0]["raw_base64"] = base64.b64encode(raw).decode()
    forged["documents"][0]["sha256"] = _sha(raw)
    with pytest.raises(ValueError):
        observation.verify_event_observation_candidate(**{
            **evidence, "calendar_evidence": forged,
            "expected_calendar_source_sha256": (_sha(raw),)})


@pytest.mark.parametrize("key,value", [
    ("category", "category_ndbg_szsh"), ("searchkey", "年度报告"),
    ("tabName", "title"), ("stock", "600519,wrong-security-id"),
])
def test_filtered_index_cannot_claim_complete_coverage(monkeypatch, key, value):
    evidence, _ = _fixture(
        monkeypatch, index_mutate=lambda index: index["parameters"].update({key: value}))
    with pytest.raises(ValueError, match="coverage"):
        observation.verify_event_observation_candidate(**evidence)


@pytest.mark.parametrize("published_at", [
    "2026-09-22T09:00:00+08:00", "2026-09-25T09:00:00+08:00",
])
def test_index_row_outside_review_window_fails(monkeypatch, published_at):
    evidence, _ = _fixture(monkeypatch, published_at=published_at)
    with pytest.raises(ValueError, match="CNINFO index row"):
        observation.verify_event_observation_candidate(**evidence)
