"""Synthetic engineering E2E only; no real issuer research approval is created.

Registered symbol identity is reused solely to exercise the issuer gate. Facts,
quotes, cases and review receipts are synthetic fixtures, never investment evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

import pytest

from test_decision_recommendation import _case
from test_event_materiality import _decision, _review, DECISION_NOT_MATERIAL
from test_human_research_approval import _receipt
from test_quote_sessions import sse_evidence
from test_research_input import _descriptor, _fully_bound_quality_descriptor
from value_investment_agent.application.decision.artifact_bundle import (
    ReadOnlyArtifactBundleRepository,
)
from value_investment_agent.application.decision.restore_decision_recommendation import (
    verify_decision_recommendation_payload,
)
from value_investment_agent.application.product.company_research import (
    _serialize_outcome,
    run_company_research_for_symbol,
)
from value_investment_agent.application.product.research_reviews import attach_research_reviews
from value_investment_agent.event_scan import AnnouncementReview, EventScanResult
from value_investment_agent.human_research_approval import (
    DECISION_APPROVED_RESEARCH_ONLY,
    artifact_fingerprint,
)
from value_investment_agent.m1_valuation_package_builder import build_descriptor
from value_investment_agent.pre_decision_eligibility import STATUS_ELIGIBLE, STATUS_NOT_ELIGIBLE
from value_investment_agent.research_application import ResearchApplicationService
from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
from value_investment_agent.research_artifact_codecs import artifact_payload
from value_investment_agent.research_input import build_research_run_spec
from value_investment_agent.research_run_contract import valuation_result_sha256
from value_investment_agent.valuation_models.residual_income import MODEL_VERSION


SYMBOL = "600519"
DAY = date(2026, 9, 21)
OBSERVED_AT = datetime(2026, 9, 21, 8, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
SYNTHETIC = "SYNTHETIC_ENGINEERING_TEST_ONLY"


def _store(root, name, payload):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def synthetic_chain(tmp_path):
    # Reuse bounded scenario/assumption, complete case and raw quote fixtures.
    canonical = _fully_bound_quality_descriptor(_descriptor()).as_policy()
    case = replace(
        _case(), symbol=SYMBOL, name=SYNTHETIC, as_of=DAY,
        run_id="synthetic-d2-shared-service", generated_at=OBSERVED_AT,
        research_version="synthetic-d2-v1", financial_period=DAY, quote_date=DAY,
        thesis=SYNTHETIC, return_driver=SYNTHETIC, mispricing_hypothesis=SYNTHETIC,
        financial_summary={"period_end": DAY.isoformat(), "scope": SYNTHETIC},
        evidence_refs=[{"id": "case-source", "scope": SYNTHETIC}],
        positives=[{"kind": "hypothesis", "text": SYNTHETIC,
                    "evidence_refs": ["case-source"]} for _ in range(3)],
        counter_evidence=[{"kind": "hypothesis", "text": SYNTHETIC,
                           "evidence_refs": ["case-source"]} for _ in range(3)],
        thesis_breakers=[{"kind": "hypothesis", "text": SYNTHETIC,
                         "evidence_refs": ["case-source"]} for _ in range(3)],
        next_events=[{"kind": "gap", "text": SYNTHETIC}],
    )
    package = {
        **canonical, "schema_version": "m1-valuation-package-v1",
        "descriptor_version": "synthetic-d2-v1", "name": SYNTHETIC,
        "run_id": case.run_id, "research_case": artifact_payload(case)[1],
    }
    package.pop("input_sha256", None)
    package["point_in_time"].update(
        report_period=DAY.isoformat(), research_as_of=DAY.isoformat(),
        valuation_date=DAY.isoformat(), available_at=REVIEWED_AT.isoformat(),
        computed_at=REVIEWED_AT.isoformat(),
    )
    package["facts"].update(kind="quality_compounder", as_of=DAY.isoformat(),
                            confidence="\u4e2d")
    for ref in package["facts"]["evidence_refs"]:
        ref["scope"] = SYNTHETIC
    for assumption in package["assumptions"]["assumptions"]:
        assumption.update(as_of=DAY.isoformat(), basis=SYNTHETIC, rationale=SYNTHETIC)
    for source in package["sources"]:
        source["location"] = "https://www.cninfo.com.cn/synthetic-test-only.pdf"

    quote_evidence = sse_evidence(price=5, day=DAY.isoformat())
    documents, references = {}, {}
    for role in ("tencent", "sina", "calendar_documents"):
        values = quote_evidence[role] if role == "calendar_documents" else [quote_evidence[role]]
        identities = []
        for document in values:
            document = dict(document, http_status=200)
            identity = hashlib.sha256(
                (document["source_url"] + "\n" + document["fetched_at"]
                 + "\n" + document["sha256"]).encode("utf-8")
            ).hexdigest()
            documents[identity] = document
            identities.append(identity)
        references[role] = identities if role == "calendar_documents" else identities[0]
    quote_path, quote_hash = _store(tmp_path, "synthetic-quote.json", {
        "version": "quote-session-collection-v1", "scope": SYNTHETIC,
        "status": "collected_not_verified", "finished_at": OBSERVED_AT.isoformat(),
        "documents": documents,
        "references": {SYMBOL: {"symbol": SYMBOL, "calendar_exchange": "SSE",
                                "document_refs": references}},
    })
    package["quote"] = {"kind": "quote_session", "symbol": SYMBOL,
                        "ref_id": "synthetic-quote", "bundle_path": quote_path.name,
                        "bundle_sha256": quote_hash}

    disclosure_path, disclosure_hash = _store(tmp_path, "synthetic-disclosure.json",
                                               {"scope": SYNTHETIC})
    decision = replace(
        _decision(DECISION_NOT_MATERIAL), symbol=SYMBOL,
        event_decision_id="synthetic-event-decision", announcement_id="9000000001",
        title=SYNTHETIC, published_at=OBSERVED_AT, reviewed_at=REVIEWED_AT,
        source_ref={"id": "synthetic-disclosure", "path": disclosure_path.name},
        source_sha256=disclosure_hash, review_notes=(SYNTHETIC,),
    )
    scan = EventScanResult(
        schema_version="m1-event-scan-v1", symbol=SYMBOL, provider=SYNTHETIC,
        scan_from=DAY, scan_to=DAY, validity_from=DAY, validity_to=DAY,
        status="PENDING_HUMAN_REVIEW", coverage_status="COMPLETE",
        pre_model_review_status="NONE", retrieved_at=OBSERVED_AT,
        parser_version="synthetic-v1", blockers=(),
        evidence_refs=({"id": "synthetic-disclosure", "path": disclosure_path.name,
                        "sha256": disclosure_hash},),
        announcements=(AnnouncementReview(
            announcement_id=decision.announcement_id, published_at=decision.published_at,
            title=SYNTHETIC, source_url="https://example.test/synthetic-disclosure",
            rule_kind="unknown", review_status="PENDING_HUMAN_REVIEW",
            materiality_candidate=True, pre_model=False,
            evidence_refs=({**decision.source_ref, "sha256": disclosure_hash},),
        ),),
    )
    event_path, event_hash = _store(tmp_path, "synthetic-scan.json", scan.as_policy())
    package["model_validity_input"] = {
        "model_id": MODEL_VERSION, "valid_from": DAY.isoformat(),
        "event_scan_ref": {"id": "synthetic-scan", "symbol": SYMBOL,
                           "path": event_path.name, "sha256": event_hash},
    }
    package_path, _ = _store(tmp_path, "synthetic-package.json", package)
    _store(tmp_path, "config/research-evidence-stop-ledger-v1.json",
           {"schema_version": "research-evidence-stop-ledger-v1", "stops": []})

    # Approve the persisted package representation consumed by the product entry.
    descriptor = build_descriptor(
        json.loads(package_path.read_text(encoding="utf-8")), root=tmp_path,
    )
    spec = build_research_run_spec(descriptor)
    app = ResearchApplicationService(InMemoryResearchArtifactRepository())
    baseline = app.run_company_research(spec)
    assert baseline.valuation.status == "conditional_research_only"
    assert baseline.valuation.model_version == MODEL_VERSION
    assert baseline.valuation.bear_value < baseline.valuation.base_value < baseline.valuation.bull_value
    assert baseline.decision_recommendation.recommendation_action == "NO_ACTION"
    exact = descriptor.as_policy()
    approval = replace(
        _receipt(decision=DECISION_APPROVED_RESEARCH_ONLY, price_assessment_eligible=True),
        approval_id="synthetic-approval-not-real-research", symbol=SYMBOL, security_id=SYMBOL,
        valuation_artifact_id="synthetic-valuation", research_case_id="synthetic-case",
        facts_artifact_id="synthetic-facts", assumption_set_id="synthetic-assumptions",
        valuation_artifact_sha256=valuation_result_sha256(baseline.valuation),
        valuation_model_version=baseline.valuation.model_version,
        research_case_sha256=artifact_fingerprint(exact["research_case"]),
        facts_artifact_sha256=artifact_fingerprint(exact["facts"]),
        assumption_set_sha256=artifact_fingerprint(exact["assumptions"]),
        reviewed_at=REVIEWED_AT, review_as_of=DAY,
        evidence_refs=({"id": "synthetic-approval", "scope": SYNTHETIC},),
    )
    review = replace(
        _review((_decision(DECISION_NOT_MATERIAL),)), decisions=(decision,),
        symbol=SYMBOL, review_id="synthetic-materiality-review",
        scan_id="synthetic-scan", scan_sha256=event_hash, scan_from=DAY, scan_to=DAY,
        reviewed_at=REVIEWED_AT, review_as_of=DAY,
        evidence_refs=({"id": "synthetic-scan", "path": event_path.name,
                        "sha256": event_hash},),
    )
    return tmp_path, package_path, descriptor, app, baseline, approval, review, event_hash


def _packet(chain, approval):
    root, _, _, _, _, _, review, _ = chain
    review_path, review_hash = _store(root, "synthetic-materiality.json", review.as_policy())
    bindings = {"event_materiality": {"path": review_path.name, "sha256": review_hash}}
    if approval is not None:
        approval_path, approval_hash = _store(root, "synthetic-approval.json", approval.as_policy())
        bindings["human_approval"] = {"path": approval_path.name, "sha256": approval_hash}
    return _store(root, "synthetic-review-packet.json", {
        "schema_version": "shared-research-review-inputs-v1", "symbol": SYMBOL,
        "action": "no_order", "scope": SYNTHETIC, "bindings": bindings,
    })


@pytest.mark.parametrize("entry", ["shared_service", "product_entry"])
@pytest.mark.parametrize("drift, expected_blocker", [
    (None, None),
    ("missing", "human_research_approval_not_resolved"),
    ("valuation_artifact_sha256", "valuation_artifact_changed"),
    ("valuation_model_version", "valuation_artifact_changed"),
    ("research_case_sha256", "research_case_sha256_changed"),
    ("facts_artifact_sha256", "facts_artifact_sha256_changed"),
    ("assumption_set_sha256", "assumption_set_sha256_changed"),
])
def test_synthetic_conditional_approval_chain_and_bundle_replay(
    synthetic_chain, entry, drift, expected_blocker,
):
    root, package_path, descriptor, app, baseline, approval, _, event_hash = synthetic_chain
    if drift == "missing":
        approval = None
    elif drift is not None:
        approval = replace(approval, **{drift: "synthetic-stale-model" if drift.endswith("version")
                                      else "0" * 64})
    packet_path, packet_hash = _packet(synthetic_chain, approval)
    output_path = root / "synthetic-export.json"
    if entry == "shared_service":
        spec = attach_research_reviews(
            root=root, spec=build_research_run_spec(descriptor), descriptor=descriptor,
            path=packet_path, expected_sha256=packet_hash, event_sha256=event_hash,
        )
        payload = _serialize_outcome(app.run_company_research(spec))
        _store(root, output_path.name, payload)
    else:
        result = run_company_research_for_symbol(
            root=root, symbol=SYMBOL, package_path=package_path, output_path=output_path,
            reviews_path=packet_path, reviews_sha256=packet_hash,
            schedule_request={
                "schema_version": "research-schedule-request-v1", "symbol": SYMBOL,
                "source_id": SYNTHETIC, "period": DAY.isoformat(),
                "research_question_id": "synthetic-conditional-approval-chain",
                "blocker_id": "initial_research", "reopen_condition_met": False,
                "new_evidence_ids": [],
            },
        )
        payload = result["result"]
        assert result["receipt"]["output_sha256"] == hashlib.sha256(output_path.read_bytes()).hexdigest()
        assert result["receipt"]["input_sha256"]["research_reviews"] == packet_hash

    assert payload["valuation"] == json.loads(baseline.valuation.to_json())
    assert payload["valuation"]["status"] == "conditional_research_only"
    assert payload["model_validity"]["status"] == "VALID"
    assert payload["model_validity"]["blockers"] == []
    assert payload["quote_snapshot"]["status"] == "verified_close"
    assert payload["price_bridge"]["bridge_status"] == "READY"
    assert payload["price_bridge"]["blockers"] == []
    assert Decimal(payload["price_bridge"]["current_price"]) == Decimal("5")
    assert payload["event_materiality_review"]["scan_sha256"] == event_hash
    assert payload["event_materiality_review"]["decisions"][0]["human_decision"] == DECISION_NOT_MATERIAL
    assert payload["event_materiality_review"]["action"] == "no_order"
    recommendation = payload["decision_recommendation"]
    assert recommendation["recommendation_type"] == ("BUY_CANDIDATE" if drift is None else "NO_ACTION")
    assert payload["action"] == recommendation["action"] == "no_order"
    assert recommendation["position_guidance"] is None
    assert recommendation["portfolio_input_status"] == "BLOCKED_PRIVATE_INPUT"
    if drift is None:
        assert payload["blockers"] == []
        assert all(payload["gate"]["results"].values())
        assert payload["price_attractiveness"]["status"] == "RESEARCH_ATTRACTIVE"
        assert payload["pre_decision_eligibility"]["status"] == STATUS_ELIGIBLE
        assert payload["pre_decision_eligibility"]["blockers"] == []
        assert payload["pre_decision_eligibility"]["positive_price_review_eligible"] is True
    else:
        assert expected_blocker in recommendation["blockers"]
        if drift == "missing":
            assert payload["pre_decision_eligibility"] is None
        else:
            assert payload["pre_decision_eligibility"]["status"] == STATUS_NOT_ELIGIBLE

    exported = json.loads(output_path.read_text(encoding="utf-8"))
    assert exported == payload
    repository = ReadOnlyArtifactBundleRepository(exported["artifact_bundle"])
    restored = verify_decision_recommendation_payload(
        repository, payload=exported["decision_recommendation"],
        recommendation_artifact=repository.recommendation_artifact(recommendation),
    )
    assert restored.recommendation.as_policy() == recommendation
    assert restored.dependency_objects["valuation"].status == "conditional_research_only"
    assert restored.recommendation.action == "no_order"
    assert restored.recommendation.position_guidance is None
    if drift is None:
        assert restored.dependency_objects["human_approval"] == approval
        assert {"research_case", "financial_facts", "valuation_assumptions", "research_gate",
                "valuation", "human_approval", "event_materiality", "model_validity",
                "price_bridge", "price_attractiveness", "pre_decision"} <= set(restored.dependencies)
        tampered = deepcopy(exported["artifact_bundle"])
        tampered["artifacts"][0]["canonical_payload"] += " "
        with pytest.raises(ValueError, match="payload hash does not match"):
            ReadOnlyArtifactBundleRepository(tampered)
