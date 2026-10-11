import hashlib
import json

import pytest

from value_investment_agent.infrastructure.evidence.workbook_publication import (
    MANAGED_NATIVE_SHEETS, verify_workbook_publication,
)
from test_quote_session_collection import Session
from test_quote_sessions import NOW
from value_investment_agent.quote_session_collection import collect_session_bundle


def write_bound(root, relative, data):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding='utf-8')
    return {'path': relative, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def registration(root):
    current, old = 'a' * 64, hashlib.sha256(b'old workbook').hexdigest()
    backup = root / 'runtime/workbook-backups/original.xlsx'
    backup.parent.mkdir(parents=True)
    backup.write_bytes(b'old workbook')
    quote = write_bound(root, 'runtime/quote.json', collect_session_bundle(
        ['000333'], session=Session(), clock=lambda: NOW))
    handoff = write_bound(root, 'runtime/publication-input.json', {
        'schema_version': 'research-publication-input-v1', 'action': 'no_order',
        'snapshot': {'schema_version': 'm7-product-workbench-v1', 'action': 'no_order', 'audit_evidence': [{
            **quote, 'evidence_id': 'test-quote', 'artifact_type': 'QUOTE_SESSION_REVALIDATED',
            'action': 'no_order'}]},
    })
    sources = write_bound(root, 'runtime/source-bindings.json', {
        'schema_version': 'existing-workbench-preview-bindings-v1', 'action': 'no_order',
        'integrated_canonical': True, 'historical_preview': True, 'canonical_written': False,
        'workbook_sha256': current, 'output_manifest_sha256': 'c' * 64,
        'publication_input_binding': handoff, 'source_bindings': [quote],
    })
    receipt = {
        'schema_version': 'canonical-reviewed-research-publication-v1',
        'status': 'PUBLISHED_PENDING_WPS_VERIFICATION', 'action': 'no_order',
        'canonical_written': True, 'after_sha256': current, 'candidate_sha256': current,
        'before_sha256': old, 'backup_sha256': old,
        'backup': 'runtime/workbook-backups/original.xlsx',
        'workbook_source': 'WORKBOOK_PATH', 'workbook_path_unchanged': True,
        'preservation_proof_sha256': 'c' * 64,
        'source_bindings_path': sources['path'], 'source_bindings_sha256': sources['sha256'],
    }
    sheets = {}
    for index, name in enumerate(MANAGED_NATIVE_SHEETS):
        path = root / f'runtime/native/{index}.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'%PDF synthetic native page ' + str(index).encode())
        sheets[name] = {'pdf': path.relative_to(root).as_posix(),
                        'pdf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'used_range': 'A1:E11'}
    native = {
        'schema_version': 'm7-product-ux-trial-wps-receipt-v1', 'status': 'passed',
        'action': 'no_order', 'readonly_open': 'PASS', 'read_only': True,
        'workbook_sha256': current, 'sheets': sheets,
    }
    binding = {}
    for role, data in [('receipt', receipt), ('wps_receipt', native)]:
        path = root / ('runtime/publication-receipts/receipt.json' if role == 'receipt' else 'runtime/wps_receipt.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding='utf-8')
        binding[role] = path.relative_to(root).as_posix()
        binding[role + '_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    binding.update(quote_observation_as_of='2026-09-07', price_admitted=False)
    return dict(schema_version='m7-current-trial-workbook-v5',
                action='no_order',
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
    contract['current_publication']['price_admitted'] = False
    config = tmp_path / 'config'
    config.mkdir()
    (config / 'current-trial-workbook.json').write_text(json.dumps(contract), encoding='utf-8')
    _require_monotonic_quote_session(tmp_path, '2026-09-07', 'a' * 64)
    with pytest.raises(ValueError, match='DAILY_QUOTE_SESSION_REGRESSION'):
        _require_monotonic_quote_session(tmp_path, '2026-09-04', 'a' * 64)
    assert contract['current_publication']['price_admitted'] is False


@pytest.mark.parametrize('floor', ['2026-09-04', '2026-09-08', None])
def test_v5_rejects_unbound_or_changed_floor(tmp_path, floor):
    contract = registration(tmp_path)
    contract['current_publication']['quote_observation_as_of'] = floor
    with pytest.raises(ValueError, match='QUOTE_FLOOR_MISMATCH'):
        verify_workbook_publication(tmp_path, contract)


@pytest.mark.parametrize('fault', ['missing', 'tampered', 'wrong-workbook', 'wrong-proof'])
def test_v5_source_binding_receipt_must_exist_match_hash_and_bind_publication(tmp_path, fault):
    contract = registration(tmp_path)
    path = tmp_path / 'runtime/source-bindings.json'
    if fault == 'missing':
        path.unlink()
    elif fault == 'tampered':
        path.write_text('{}')
    else:
        data = json.loads(path.read_text())
        data['workbook_sha256' if fault == 'wrong-workbook' else 'output_manifest_sha256'] = 'f' * 64
        sources = write_bound(tmp_path, 'runtime/source-bindings.json', data)
        receipt = json.loads((tmp_path / contract['current_publication']['receipt']).read_text())
        receipt['source_bindings_sha256'] = sources['sha256']
        pinned = write_bound(tmp_path, contract['current_publication']['receipt'], receipt)
        contract['current_publication']['receipt_sha256'] = pinned['sha256']
    with pytest.raises(ValueError):
        verify_workbook_publication(tmp_path, contract)


@pytest.mark.parametrize('fault', ['unrelated-sheets', 'missing-sheet', 'empty-export',
                                 'duplicate-export', 'outside-export', 'missing-pdf', 'tampered-pdf'])
def test_native_receipt_requires_each_named_page_and_its_export(tmp_path, fault):
    contract = registration(tmp_path)
    relative = contract['current_publication']['wps_receipt']
    native = json.loads((tmp_path / relative).read_text())
    sheets = native['sheets']
    first = sheets[MANAGED_NATIVE_SHEETS[0]]
    if fault == 'unrelated-sheets':
        native['sheets'] = {str(i): {} for i in range(7)}
    elif fault == 'missing-sheet':
        sheets.pop(MANAGED_NATIVE_SHEETS[-1])
    elif fault == 'empty-export':
        sheets[MANAGED_NATIVE_SHEETS[0]] = {}
    elif fault == 'duplicate-export':
        sheets[MANAGED_NATIVE_SHEETS[1]] = dict(first)
    elif fault == 'outside-export':
        first['pdf'] = '../outside.pdf'
    elif fault == 'missing-pdf':
        (tmp_path / first['pdf']).unlink()
    else:
        (tmp_path / first['pdf']).write_bytes(b'changed')
    pin = write_bound(tmp_path, relative, native)
    contract['current_publication']['wps_receipt_sha256'] = pin['sha256']
    with pytest.raises(ValueError):
        verify_workbook_publication(tmp_path, contract)


def test_v4_does_not_require_successor_publication_receipts(tmp_path):
    assert verify_workbook_publication(tmp_path, {'schema_version': 'm7-current-trial-workbook-v4'}) is None


def test_publisher_cannot_lower_v5_floor_by_editing_pointer(tmp_path):
    from scripts.current.publish_product_workbench_to_canonical import _require_monotonic_quote_session
    contract = registration(tmp_path)
    contract['current_publication']['quote_observation_as_of'] = '2026-09-04'
    write_bound(tmp_path, 'config/current-trial-workbook.json', contract)
    with pytest.raises(ValueError, match='CURRENT_QUOTE_SESSION_POINTER_INVALID'):
        _require_monotonic_quote_session(tmp_path, '2026-09-04', 'a' * 64)


@pytest.mark.parametrize('fault', ['missing-bundle', 'tampered-bundle', 'missing-handoff', 'tampered-handoff'])
def test_floor_requires_the_pinned_published_handoff_and_quote_bytes(tmp_path, fault):
    contract = registration(tmp_path)
    path = tmp_path / ('runtime/quote.json' if fault.endswith('bundle') else 'runtime/publication-input.json')
    if fault.startswith('missing'):
        path.unlink()
    else:
        path.write_text('{}')
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        verify_workbook_publication(tmp_path, contract)


def test_actual_published_v5_registration_replays_typed_snapshot_and_native_exports():
    from datetime import date
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    contract = json.loads((root / 'config/current-trial-workbook.json').read_text(encoding='utf-8'))
    if contract.get('schema_version') != 'm7-current-trial-workbook-v5':
        pytest.skip('local v5 publication registration is absent')
    if not (root / contract['current_publication']['receipt']).exists():
        pytest.skip('local publication evidence is absent')
    assert verify_workbook_publication(root, contract) == date.fromisoformat(
        contract['current_publication']['quote_observation_as_of'])
