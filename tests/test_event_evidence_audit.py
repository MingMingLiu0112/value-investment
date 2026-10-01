import hashlib
import json
import pytest
from value_investment_agent.application.historical_validation.event_evidence_audit import audit_event_evidence


@pytest.mark.parametrize('fault', ['none', 'changed', 'missing', 'escape'])
def test_originals_are_checked_not_only_scan_hash(tmp_path, fault):
    original = tmp_path / 'original.json'
    original.write_text('{}', encoding='utf-8')
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    scan = tmp_path / 'scan.json'
    scan.write_text(json.dumps(dict(symbol='600887', evidence_refs=[dict(
        id='index', path='../outside' if fault == 'escape' else 'original.json',
        sha256=digest)])), encoding='utf-8')
    scan_hash = hashlib.sha256(scan.read_bytes()).hexdigest()
    if fault == 'changed': original.write_text('{"changed":true}', encoding='utf-8')
    if fault == 'missing': original.unlink()
    args = dict(root=tmp_path, path=scan, expected_sha256=scan_hash, symbol='600887')
    if fault == 'escape':
        with pytest.raises(ValueError): audit_event_evidence(**args)
        return
    result = audit_event_evidence(**args)
    assert result['status'] == ('PASS' if fault == 'none' else 'NOT_READY')
    assert not result['model_validity_admitted']
    assert not result['strict_pit_admitted']
    assert result['action'] == 'no_order'
