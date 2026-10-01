from dataclasses import replace
import pytest
from test_product_workbench_read_model import _payload
from value_investment_agent.presentation.read_models.product_workbench import product_workbench_from_payload, EvidenceRecord
from value_investment_agent.presentation.read_models.company_events import project_company_event_questions


def test_company_events_keep_gates_and_show_scope_and_originals():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    evidence = EvidenceRecord('event-fixture', 'Events', 'research', 'runtime/scan.json', 'a'*64, model.as_of)
    packet = dict(schema_version='event-source-review-packet-v1', action='no_order', symbol=card.symbol,
                  materiality_approved=False, model_basis_complete=False,
                  audit={'evidence_integrity_verified': True}, events=[dict(announcement_id='123',
                      title='回购报告', published_at='2026-09-17', materiality_review='PENDING_HUMAN_REVIEW',
                      sources=[dict(source_url='https://example.test/report.pdf', sha256='b'*64,
                                    pages=[{}], text_status='TEXT_EXTRACTED_NOT_SEMANTICALLY_VERIFIED')])])
    output = project_company_event_questions(model, packet, evidence)
    updated = output.companies[0]
    assert replace(updated, decision_review=card.decision_review, evidence_refs=card.evidence_refs) == card
    assert output.portfolio == model.portfolio
    assert 'https://example.test/report.pdf' in dict(updated.decision_review)['待复核公告 123 回购报告']
    assert '不代表今日' in dict(updated.decision_review)['公告覆盖边界']
    packet['materiality_approved'] = True
    with pytest.raises(ValueError): project_company_event_questions(model, packet, evidence)


def test_failed_originals_do_not_surface_unverified_event_text():
    model = product_workbench_from_payload(_payload())
    card = model.companies[0]
    evidence = EvidenceRecord('failed-event', 'Events', 'research', 'runtime/scan.json', 'a'*64, model.as_of)
    packet = dict(schema_version='event-source-review-packet-v1', action='no_order', symbol=card.symbol,
                  materiality_approved=False, model_basis_complete=False,
                  audit={'evidence_integrity_verified': False}, events=[{'title': 'untrusted'}])
    output = project_company_event_questions(model, packet, evidence)
    assert 'untrusted' not in str(output.companies[0].decision_review)
    assert output.companies[0].decision_process == card.decision_process
