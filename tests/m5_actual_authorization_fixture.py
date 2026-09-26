"""Synthetic signed M5 ACTUAL approval-receipt fixture for negative tests."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import base64
import hashlib
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from authorization_trust_registry_fixture import pin_test_trust_root

from value_investment_agent.event_materiality import (
    DECISION_REQUIRES_RECALCULATION,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
)
from value_investment_agent.m5_event_dependencies import (
    KIND_CURRENT_STATUS,
    KIND_DECISION_REVIEW,
    KIND_FACTS,
    KIND_MODEL_VALIDITY,
    KIND_VALUATION_INPUTS,
    DependencyGraph,
    DependencyNode,
)
from value_investment_agent.m5_materiality_bridge import build_materiality_bridge_batch
from value_investment_agent.operations.authorization.m5_actual_approval_receipt import (
    BUNDLE_VERSION,
    PURPOSE,
    RECEIPT_VERSION,
    TRUST_ROOT_VERSION,
    build_subject,
    event_identity_sha256,
    graph_sha256,
)


TZ = timezone(timedelta(hours=8))
PUBLISHED_AT = datetime(2026, 9, 2, 9, 0, tzinfo=TZ)
REVIEWED_AT = datetime(2026, 9, 24, 9, 30, tzinfo=TZ)
RUN_ID = "600887-synthetic-run-20260924"
ANNOUNCEMENT_ID = "1225549001"


def _decision() -> EventMaterialityDecision:
    return EventMaterialityDecision(
        event_decision_id=f"event-decision-{ANNOUNCEMENT_ID}",
        symbol="600887",
        announcement_id=ANNOUNCEMENT_ID,
        title="synthetic offline fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"pdf-{ANNOUNCEMENT_ID}",
            "path": f"synthetic/{ANNOUNCEMENT_ID}.pdf",
            "sha256": "c" * 64,
        },
        source_sha256="c" * 64,
        machine_candidate_reason="synthetic title rule candidate",
        human_decision=DECISION_REQUIRES_RECALCULATION,
        affected_domains=("balance_sheet_risk",),
        affected_fact_fields=("total_debt",),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=True,
        requires_model_stale=True,
        requires_followup=False,
        reviewed_at=REVIEWED_AT,
        review_notes=("synthetic offline review note",),
    )


def _review() -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-synthetic-event-review-20260924",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol="600887",
        scan_id="600887-synthetic-scan-20260924",
        scan_sha256="d" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=date(2026, 9, 24),
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=(_decision(),),
        evidence_refs=({"id": "synthetic-scan"},),
    )


def _graph() -> DependencyGraph:
    return DependencyGraph(
        (
            DependencyNode(
                node_id="facts-600887",
                kind=KIND_FACTS,
                symbol="600887",
                inputs=(),
                version="synthetic-v1",
                evidence_refs=({"id": "facts"},),
            ),
            DependencyNode(
                node_id="valuation-inputs-600887",
                kind=KIND_VALUATION_INPUTS,
                symbol="600887",
                inputs=("facts-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "valuation"},),
            ),
            DependencyNode(
                node_id="model-validity-600887",
                kind=KIND_MODEL_VALIDITY,
                symbol="600887",
                inputs=(),
                version="synthetic-v1",
                evidence_refs=({"id": "model"},),
            ),
            DependencyNode(
                node_id="decision-review-600887",
                kind=KIND_DECISION_REVIEW,
                symbol="600887",
                inputs=("valuation-inputs-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "decision"},),
            ),
            DependencyNode(
                node_id="current-status-600887",
                kind=KIND_CURRENT_STATUS,
                symbol="600887",
                inputs=("decision-review-600887",),
                version="synthetic-v1",
                evidence_refs=({"id": "status"},),
            ),
        )
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _envelope(value: object) -> dict[str, str]:
    raw = _canonical(value)
    return {
        "raw_base64": base64.b64encode(raw).decode("ascii"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _public(key: Ed25519PrivateKey) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    ).hex()


def synthetic_actual_receipt(
    *,
    namespace: str = "ACTUAL",
    authorization_id: str = "m5-synthetic-approved",
    review_sha256: str | None = None,
    current_queue_bytes: bytes | None = None,
    bridge_bytes: bytes | None = None,
):
    review = _review()
    batch = build_materiality_bridge_batch(review, namespace=namespace)
    graph = _graph()
    review_raw = _canonical(review.as_policy())
    bridge_raw = _canonical([batch.as_policy()])
    queue_raw = current_queue_bytes or _canonical(
        {"action": "no_order", "queue_id": "synthetic-current-queue"}
    )
    reconciliation_raw = _canonical(
        {
            "action": "no_order",
            "reconciliation_id": "synthetic-reconciliation",
            "current_queue_sha256": hashlib.sha256(queue_raw).hexdigest(),
            "prior_review_ids": [batch.review_id],
        }
    )
    graph_receipt_raw = _canonical({"symbol": batch.symbol, "graph": graph.as_policy()})
    if bridge_bytes is not None:
        bridge_raw = bridge_bytes
    artifacts = {
        "reviews": _envelope(review.as_policy()),
        "bridge_batches": {
            "raw_base64": base64.b64encode(bridge_raw).decode("ascii"),
            "sha256": hashlib.sha256(bridge_raw).hexdigest(),
        },
        "current_queue": {
            "raw_base64": base64.b64encode(queue_raw).decode("ascii"),
            "sha256": hashlib.sha256(queue_raw).hexdigest(),
        },
        "reconciliation": {
            "raw_base64": base64.b64encode(reconciliation_raw).decode("ascii"),
            "sha256": hashlib.sha256(reconciliation_raw).hexdigest(),
        },
        "graph_receipt": {
            "raw_base64": base64.b64encode(graph_receipt_raw).decode("ascii"),
            "sha256": hashlib.sha256(graph_receipt_raw).hexdigest(),
        },
    }
    if review_sha256 is not None:
        artifacts["reviews"]["sha256"] = review_sha256
    subject = build_subject(
        run_id=RUN_ID,
        batch_id=RUN_ID,
        stream_id=RUN_ID,
        symbol=batch.symbol,
        review_id=batch.review_id,
        event_ids=[event.source_event_id for event in batch.events],
        event_identity_sha256_value=event_identity_sha256(
            batch.events, batch.observed_times
        ),
        dependency_graph_sha256=graph_sha256(graph),
        review_sha256=artifacts["reviews"]["sha256"],
        queue_sha256="e" * 64,
        current_queue_sha256=artifacts["current_queue"]["sha256"],
        bridge_batches_sha256=artifacts["bridge_batches"]["sha256"],
        graph_receipt_sha256=artifacts["graph_receipt"]["sha256"],
        reconciliation_sha256=artifacts["reconciliation"]["sha256"],
    )
    key = Ed25519PrivateKey.generate()
    payload = {
        "action": "no_order",
        "authorization_id": authorization_id,
        "review_provenance": "USER_CONFIRMED_DELEGATED_REVIEW",
        "authorized_at": (REVIEWED_AT - timedelta(minutes=1)).isoformat(),
        "sequence": 1,
        "previous_receipt_sha256": None,
        "reviewed_artifact_sha256": {
            name: envelope["sha256"] for name, envelope in artifacts.items()
        },
        "subject": subject,
    }
    receipt = {
        "version": RECEIPT_VERSION,
        "payload": payload,
        "signature": key.sign(PURPOSE + _canonical(payload)).hex(),
    }
    bundle = {
        "schema_version": BUNDLE_VERSION,
        "receipt_chain": [receipt],
        "reviewed_artifacts": artifacts,
    }
    trust_root = {
        "schema_version": TRUST_ROOT_VERSION,
        "approval_public_key": _public(key),
        "approved_receipt_sha256": _sha256(receipt),
        "approved_sequence": 1,
        "approved_previous_receipt_sha256": None,
    }
    # Synthetic roots are pinned into the temporary test registry so the
    # default verification path can stay fail-closed for unpinned roots.
    pin_test_trust_root(trust_root)
    return {
        "bundle": bundle,
        "trust_root": trust_root,
        "subject": deepcopy(subject),
        "graph": graph,
        "batch": batch,
        "review": review,
        "review_raw": review_raw,
        "bridge_raw": bridge_raw,
        "queue_raw": queue_raw,
        "reconciliation_raw": reconciliation_raw,
        "graph_receipt_raw": graph_receipt_raw,
        "private_key": key,
    }
