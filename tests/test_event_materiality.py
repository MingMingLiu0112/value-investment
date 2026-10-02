from datetime import date, datetime, timezone

import pytest

from value_investment_agent.event_materiality import (
    DECISION_ALREADY_INCORPORATED,
    DECISION_DUPLICATE,
    DECISION_NOT_MATERIAL,
    DECISION_REQUIRES_DECOMPOSITION,
    DECISION_REQUIRES_RECALCULATION,
    DECISION_RISK_MONITOR,
    EVENT_MATERIALITY_SCHEMA,
    EventMaterialityDecision,
    EventMaterialityReview,
    event_materiality_decision_from_payload,
    event_materiality_review_from_payload,
)
from value_investment_agent.model_validity import evaluate_model_validity


REVIEWED_AT = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
PUBLISHED_AT = datetime(2026, 9, 2, tzinfo=timezone.utc)
MODEL_DATE = date(2026, 9, 22)


def _decision(
    human_decision: str,
    *,
    announcement_id="1225542476",
    event_cluster_id=None,
    supersedes_event_id=None,
) -> EventMaterialityDecision:
    expected = {
        DECISION_NOT_MATERIAL: (False, False, False),
        DECISION_ALREADY_INCORPORATED: (False, False, False),
        DECISION_REQUIRES_RECALCULATION: (True, True, False),
        DECISION_RISK_MONITOR: (False, False, True),
        DECISION_DUPLICATE: (False, False, False),
        DECISION_REQUIRES_DECOMPOSITION: (False, False, True),
    }
    recalc, stale, followup = expected[human_decision]
    return EventMaterialityDecision(
        event_decision_id=f"event-decision-{announcement_id}",
        symbol="600887",
        announcement_id=announcement_id,
        title="fixture disclosure",
        published_at=PUBLISHED_AT,
        source_ref={
            "id": f"pdf-{announcement_id}",
            "path": f"fixtures/{announcement_id}.pdf",
        },
        source_sha256="a" * 64,
        machine_candidate_reason="rule candidate from title",
        human_decision=human_decision,
        affected_domains=("balance_sheet_risk",),
        affected_fact_fields=(),
        affected_assumptions=(),
        affected_artifacts=(),
        requires_recalculation=recalc,
        requires_model_stale=stale,
        requires_followup=followup,
        event_cluster_id=event_cluster_id,
        supersedes_event_id=supersedes_event_id,
        reviewed_at=REVIEWED_AT,
        review_notes=("human review note",),
    )


def _review(decisions) -> EventMaterialityReview:
    return EventMaterialityReview(
        review_id="600887-event-review-20260923",
        schema_version=EVENT_MATERIALITY_SCHEMA,
        symbol="600887",
        scan_id="600887-scan-20260923T051018Z",
        scan_sha256="b" * 64,
        scan_from=date(2026, 8, 27),
        scan_to=MODEL_DATE,
        reviewed_at=REVIEWED_AT,
        review_as_of=REVIEWED_AT.date(),
        reviewer_type="human_research_lead",
        decisions=tuple(decisions),
        evidence_refs=({"id": "scan"},),
    )


def _validity(review):
    return evaluate_model_validity(
        model_id="residual-income-equity-shared-v1",
        symbol="600887",
        model_as_of=MODEL_DATE,
        valid_from=MODEL_DATE,
        quote_date=MODEL_DATE,
        events=[],
        event_scan_evidence_refs=[{"id": "scan"}],
        event_materiality=review,
    )


def test_event_decision_round_trip_preserves_classification():
    decision = _decision(DECISION_RISK_MONITOR, event_cluster_id="RISK_CLUSTER")
    restored = event_materiality_decision_from_payload(decision.as_policy())

    assert restored == decision
    assert restored.human_decision == DECISION_RISK_MONITOR
    assert restored.requires_followup is True
    assert restored.requires_model_stale is False


def test_not_material_and_already_incorporated_do_not_stale_model():
    for decision in (
        _decision(DECISION_NOT_MATERIAL),
        _decision(DECISION_ALREADY_INCORPORATED),
    ):
        checked = _validity(_review((decision,)))
        assert checked.status == "VALID"
        assert checked.material_event_found is False


def test_material_recalculation_makes_model_stale():
    checked = _validity(_review((_decision(DECISION_REQUIRES_RECALCULATION),)))

    assert checked.status == "STALE"
    assert checked.material_event_found is True
    assert any("requires recalculation" in blocker for blocker in checked.blockers)


def test_risk_monitor_keeps_model_valid_but_records_review_due():
    checked = _validity(_review((_decision(DECISION_RISK_MONITOR),)))

    assert checked.status == "VALID"
    assert any("event_risk_monitor" in blocker for blocker in checked.blockers)


def test_duplicate_decision_requires_cluster_and_does_not_stale():
    with pytest.raises(ValueError, match="Duplicate"):
        _decision(DECISION_DUPLICATE)

    checked = _validity(
        _review(
            (
                _decision(
                    DECISION_DUPLICATE,
                    event_cluster_id="YILI_BUYBACK_2026",
                ),
            )
        )
    )
    assert checked.status == "VALID"


def test_decomposition_keeps_model_non_stale_but_reports_blocker():
    checked = _validity(_review((_decision(DECISION_REQUIRES_DECOMPOSITION),)))

    assert checked.status == "VALID"
    assert any("event_requires_decomposition" in blocker for blocker in checked.blockers)


def test_review_round_trip_and_coverage_watermark():
    review = _review(
        (
            _decision(DECISION_NOT_MATERIAL),
            _decision(
                DECISION_REQUIRES_RECALCULATION,
                announcement_id="1225511493",
            ),
        )
    )
    restored = event_materiality_review_from_payload(review.as_policy())

    assert restored == review
    assert restored.coverage_watermark == MODEL_DATE
    assert restored.has_unresolved_recalculation is True
    assert restored.covers(MODEL_DATE) is True
    assert restored.covers(date(2026, 9, 23)) is False


def test_shared_materiality_attachment_requires_exact_scan_and_keeps_recalculation(tmp_path):
    from dataclasses import dataclass
    from types import SimpleNamespace
    import hashlib
    import json
    from value_investment_agent.application.product.research_reviews import attach_research_reviews
    from value_investment_agent.research_application import ModelValidityEvaluationInput
    from value_investment_agent.event_scan import EventScanResult, AnnouncementReview
    @dataclass(frozen=True)
    class Spec:
        symbol: str = '600887'
        input_descriptor_sha256: str = 'a' * 64
        model_validity_input: object = None
        event_materiality_review: object = None
        research_case_payload: object = None
        facts_payload: object = None
        assumptions_payload: object = None
    review = _review((_decision(DECISION_REQUIRES_RECALCULATION, announcement_id='1225511493'),))
    source = tmp_path / 'materiality.json'
    source.write_text(json.dumps(review.as_policy()), encoding='utf-8')
    path = tmp_path / 'packet.json'
    path.write_text(json.dumps(dict(schema_version='shared-research-review-inputs-v1',
        symbol='600887', action='no_order', bindings=dict(event_materiality=dict(
            path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest())))), encoding='utf-8')
    decision = review.decisions[0]
    scan = EventScanResult(schema_version='m1-event-scan-v1', symbol='600887', provider='TEST',
        scan_from=review.scan_from, scan_to=review.scan_to,
        validity_from=MODEL_DATE, validity_to=MODEL_DATE, status='PENDING_HUMAN_REVIEW',
        coverage_status='COMPLETE', pre_model_review_status='PENDING_HUMAN_REVIEW',
        announcements=(AnnouncementReview(announcement_id=decision.announcement_id,
            published_at=decision.published_at, title=decision.title, source_url='https://example.test',
            rule_kind='test', review_status='PENDING_HUMAN_REVIEW', materiality_candidate=True,
            pre_model=True, evidence_refs=({**decision.source_ref, 'sha256': decision.source_sha256},)),),
        blockers=('SYNTHETIC_SOURCE_LIMITATION',), evidence_refs=({'id': 'scan'},),
        retrieved_at=REVIEWED_AT, parser_version='test-only')
    spec = Spec(model_validity_input=ModelValidityEvaluationInput(
        model_id='test', valid_from=MODEL_DATE, events=(), event_scan_evidence_refs=(), event_scan=scan))
    kwargs = dict(root=tmp_path, spec=spec, descriptor=SimpleNamespace(as_policy=lambda:
        dict(research_case={}, facts={}, assumptions={})), path=path,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError, match='exact acquired event scan'):
        attach_research_reviews(**kwargs, event_sha256='c' * 64)
    updated = attach_research_reviews(**kwargs, event_sha256='b' * 64)
    assert updated.event_materiality_review.has_unresolved_recalculation is True
    assert updated.model_validity_input.event_scan is None
    assert 'SYNTHETIC_SOURCE_LIMITATION' in updated.model_validity_input.blockers
    from dataclasses import replace
    for bad_scan in (replace(scan, coverage_status='INCOMPLETE'), replace(scan, announcements=()),
                     replace(scan, retrieved_at=datetime(2026, 9, 24, tzinfo=timezone.utc))):
        with pytest.raises(ValueError, match='complete acquired scan|every acquired announcement|observation mismatch'):
            attach_research_reviews(**{**kwargs, 'spec': replace(spec,
                model_validity_input=replace(spec.model_validity_input, event_scan=bad_scan))},
                event_sha256='b' * 64)


def test_attached_materiality_reaches_real_shared_service_and_readable_projection(tmp_path):
    from dataclasses import replace
    import hashlib
    import json
    from types import SimpleNamespace
    from test_research_application import case, residual_facts, _identity_source
    from value_investment_agent.application.product.research_reviews import attach_research_reviews
    from value_investment_agent.application.product.company_research import _serialize_outcome
    from value_investment_agent.research_application import ResearchRunSpec, ModelValidityEvaluationInput, ResearchApplicationService
    from value_investment_agent.research_artifact_repository import InMemoryResearchArtifactRepository
    from value_investment_agent.event_scan import EventScanResult, AnnouncementReview
    from value_investment_agent.quote_snapshot import QuoteSnapshot
    from value_investment_agent.presentation.read_models.shadow_daily_review import render_shadow_company_review
    from decimal import Decimal

    # Synthetic issuer/facts fixture, real shared application/model/bridge; not production evidence.
    model_day = date(2025, 12, 31)
    reviewed = datetime(2026, 9, 23, 5, 30, tzinfo=timezone.utc)
    decision = replace(_decision(DECISION_REQUIRES_RECALCULATION),
        published_at=datetime(2025, 12, 31, tzinfo=timezone.utc))
    review = replace(_review((decision,)), scan_from=model_day, scan_to=model_day)
    scan = EventScanResult(schema_version='m1-event-scan-v1', symbol='600887', provider='TEST',
        scan_from=model_day, scan_to=model_day, validity_from=model_day, validity_to=model_day,
        status='PENDING_HUMAN_REVIEW', coverage_status='COMPLETE', pre_model_review_status='NONE',
        announcements=(AnnouncementReview(announcement_id=decision.announcement_id,
            published_at=decision.published_at, title=decision.title, source_url='https://example.test/fixture',
            rule_kind='test', review_status='PENDING_HUMAN_REVIEW', materiality_candidate=True,
            pre_model=False, evidence_refs=({**decision.source_ref, 'sha256': decision.source_sha256},)),),
        blockers=(), evidence_refs=({'id': 'scan'},), retrieved_at=reviewed, parser_version='test-only')
    spec = ResearchRunSpec(run_id='synthetic-reviewed-service', symbol='600887',
        profile_id='quality_compounder', research_case=case('600887'), facts=residual_facts('600887'),
        available_at=reviewed, input_sources=(_identity_source('600887'),),
        quote=QuoteSnapshot(symbol='600887', quote_date=model_day, current_price=Decimal('5'),
            status='verified_close', evidence_refs=[{'id': 'quote', 'sha256': 'c' * 64}]),
        model_validity_input=ModelValidityEvaluationInput(model_id='residual-income-equity-shared-v1',
            valid_from=model_day, event_scan=scan, event_scan_evidence_refs=({'id': 'scan'},)))
    source = tmp_path / 'review.json'
    source.write_text(json.dumps(review.as_policy()), encoding='utf-8')
    packet = tmp_path / 'packet.json'
    packet.write_text(json.dumps(dict(schema_version='shared-research-review-inputs-v1',
        symbol='600887', action='no_order', bindings=dict(event_materiality=dict(
            path=source.name, sha256=hashlib.sha256(source.read_bytes()).hexdigest())))), encoding='utf-8')
    attached = attach_research_reviews(root=tmp_path, spec=spec,
        descriptor=SimpleNamespace(as_policy=lambda: dict(research_case={'symbol': '600887'},
            facts={'symbol': '600887'}, assumptions={'symbol': '600887'})),
        path=packet, expected_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(), event_sha256='b' * 64)
    outcome = ResearchApplicationService(InMemoryResearchArtifactRepository()).run_company_research(attached)
    assert outcome.event_materiality_review == review
    assert outcome.model_validity.status == 'STALE'
    assert outcome.price_bridge.bridge_status != 'READY'
    assert outcome.valuation.status == 'conditional_research_only'
    assert outcome.pre_decision_eligibility is None  # No human research approval supplied.
    serialized = _serialize_outcome(outcome)
    product = dict(symbol='600887', suggested_state='NOT_READY', position_guidance=None, blockers=list(outcome.blockers))
    card = render_shadow_company_review(research=dict(result=serialized,
        session_date=reviewed.date().isoformat(), run_id=spec.run_id),
        model=dict(model_validity=serialized['model_validity'], price_bridge=serialized['price_bridge'],
                   valuation_result=serialized['valuation']), decision=product, product=product,
        audit=dict(blockers=list(outcome.blockers), input_consistency_status='SHADOW_INPUT_INCOMPLETE'))
    assert 'STALE' in card and 'action=no_order' in card
    assert 'requires recalculation' in card
    (tmp_path / 'synthetic-review-card.md').write_text(card, encoding='utf-8')
