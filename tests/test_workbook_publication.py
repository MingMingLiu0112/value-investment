import hashlib
import json

import pytest

from value_investment_agent.infrastructure.evidence.workbook_publication import verify_workbook_publication


def registration(root):
    current, old = 'a' * 64, hashlib.sha256(b'old workbook').hexdigest()
    backup = root / 'runtime/workbook-backups/original.xlsx'
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b'old workbook')
    receipt = {
        'schema_version': 'canonical-reviewed-research-publication-v1',
        'status': 'PUBLISHED_PENDING_WPS_VERIFICATION', 'action': 'no_order',
        'canonical_written': True, 'after_sha256': current, 'candidate_sha256': current,
        'before_sha256': old, 'backup_sha256': old,
        'backup': 'runtime/workbook-backups/original.xlsx',
        'workbook_source': 'WORKBOOK_PATH', 'workbook_path_unchanged': True,
    }
    native = {
        'schema_version': 'm7-product-ux-trial-wps-receipt-v1', 'status': 'passed',
        'action': 'no_order', 'readonly_open': 'PASS', 'read_only': True,
        'workbook_sha256': current, 'sheets': {str(i): {} for i in range(7)},
    }
    binding = {}
    for role, data in [('receipt', receipt), ('wps_receipt', native)]:
        path = root / ('runtime/publication-receipts/receipt.json' if role == 'receipt' else 'runtime/wps_receipt.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
        binding[role] = path.relative_to(root).as_posix()
        binding[role + '_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(schema_version='m7-current-trial-workbook-v5',
                canonical_workbook_sha256=current, previous_canonical_workbook_sha256=old,
                current_publication=binding)


def test_current_registration_binds_publish_and_native_successor_without_rewriting(tmp_path):
    contract = registration(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob('*') if path.is_file()}
    verify_workbook_publication(tmp_path, contract)
    assert before == {path: path.read_bytes() for path in before}


@pytest.mark.parametrize('role,field,value', [
    ('receipt', 'canonical_written', False),
    ('receipt', 'after_sha256', 'b' * 64),
    ('receipt', 'candidate_sha256', 'b' * 64),
    ('receipt', 'before_sha256', 'b' * 64),
    ('receipt', 'workbook_source', 'PRODUCT_UX_RUNTIME'),
    ('wps_receipt', 'workbook_sha256', 'b' * 64),
    ('wps_receipt', 'read_only', False),
    ('wps_receipt', 'status', 'failed'),
    ('wps_receipt', 'action', 'order'),
])
def test_bound_but_semantically_invalid_receipt_fails(tmp_path, role, field, value):
    contract = registration(tmp_path)
    path = tmp_path / contract['current_publication'][role]
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    contract['current_publication'][role + '_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        verify_workbook_publication(tmp_path, contract)


@pytest.mark.parametrize('change', ['missing', 'tampered', 'outside', 'backup', 'binding'])
def test_missing_or_changed_evidence_fails_closed(tmp_path, change):
    contract = registration(tmp_path)
    path = tmp_path / contract['current_publication']['receipt']
    if change == 'missing':
        path.unlink()
    elif change == 'tampered':
        path.write_text('{}')
    elif change == 'outside':
        contract['current_publication']['receipt'] = '../receipt.json'
    elif change == 'backup':
        (tmp_path / 'runtime/workbook-backups/original.xlsx').write_bytes(b'changed')
    else:
        contract.pop('current_publication')
    with pytest.raises(ValueError):
        verify_workbook_publication(tmp_path, contract)


def test_reviewed_publication_preserves_observation_session_floor_without_admission(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.current.publish_product_workbench_to_canonical import _require_monotonic_quote_session

    contract = registration(tmp_path)
    contract['current_publication']['quote_observation_as_of'] = '2026-10-09'
    contract['current_publication']['price_admitted'] = False
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'current-trial-workbook.json').write_text(json.dumps(contract), encoding='utf-8')
    _require_monotonic_quote_session(tmp_path, '2026-10-09', 'a' * 64)
    with pytest.raises(ValueError, match='DAILY_QUOTE_SESSION_REGRESSION'):
        _require_monotonic_quote_session(tmp_path, '2026-10-08', 'a' * 64)
    assert contract['current_publication']['price_admitted'] is False
