import hashlib
import json
import pytest
from value_investment_agent.application.historical_validation import event_source_review as service


def test_source_pages_do_not_approve_materiality(tmp_path, monkeypatch):
    pdf = tmp_path / 'original.pdf'
    pdf.write_bytes(b'original')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    binding = dict(id='announcement', path='original.pdf', sha256=digest)
    payload = dict(symbol='600887', evidence_refs=[binding], announcements=[dict(
        announcement_id='123', title='Buyback disclosure', published_at='2026-09-17T00:00:00+08:00',
        source_url='https://example.test/123.pdf', pre_model=True, materiality_candidate=True,
        evidence_refs=[binding])])
    scan = tmp_path / 'scan.json'
    scan.write_text(json.dumps(payload), encoding='utf-8')
    args = dict(root=tmp_path, path=scan, expected_sha256=hashlib.sha256(scan.read_bytes()).hexdigest(), symbol='600887')
    monkeypatch.setattr(service, 'extract_pages', lambda path: ['page one', 'page two'])
    output = service.prepare_event_source_review(**args)
    assert output['events'][0]['sources'][0]['pages'][1]['physical_page'] == 2
    assert not output['materiality_approved']
    assert not output['model_basis_complete']
    assert output['action'] == 'no_order'
    pdf.write_bytes(b'changed')
    output = service.prepare_event_source_review(**args)
    assert output['status'] == 'NOT_READY'
    assert output['events'] == []


def test_changes_during_extraction_fail_closed(tmp_path, monkeypatch):
    pdf = tmp_path / 'original.pdf'
    pdf.write_bytes(b'original')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    binding = dict(id='announcement', path='original.pdf', sha256=digest)
    scan = tmp_path / 'scan.json'
    scan.write_text(json.dumps(dict(symbol='600887', evidence_refs=[binding], announcements=[dict(
        evidence_refs=[binding])])), encoding='utf-8')
    def mutate(path):
        path.write_bytes(b'changed')
        return ['changed']
    monkeypatch.setattr(service, 'extract_pages', mutate)
    with pytest.raises(ValueError, match='during extraction'):
        service.prepare_event_source_review(root=tmp_path, path=scan,
            expected_sha256=hashlib.sha256(scan.read_bytes()).hexdigest(), symbol='600887')
