import hashlib
import json
from pathlib import Path
import shutil

import pytest

from test_workbook_publication import registration
from value_investment_agent.infrastructure.evidence.workbook_publication import (
    _bound_bytes, _evidence_path, verify_workbook_publication,
)


def restore_fixture(tmp_path):
    original = tmp_path / 'original'
    original.mkdir()
    contract = registration(original)
    # Preserve a real historical contract with absolute paths throughout the chain.
    def absolute_paths(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('path', 'pdf', 'backup', 'source_bindings_path', 'receipt', 'wps_receipt') and isinstance(item, str):
                    value[key] = str(original / item)
                else:
                    absolute_paths(item)
        elif isinstance(value, list):
            for item in value:
                absolute_paths(item)
    def replace(relative):
        path = original / relative
        data = json.loads(path.read_text())
        absolute_paths(data)
        return path, data
    def persist(path, data):
        path.write_text(json.dumps(data), encoding='utf-8')
        return hashlib.sha256(path.read_bytes()).hexdigest()
    hp, handoff = replace('runtime/publication-input.json')
    hh = persist(hp, handoff)
    sp, sources = replace('runtime/source-bindings.json')
    sources['publication_input_binding']['sha256'] = hh
    sh = persist(sp, sources)
    for role in ('receipt', 'wps_receipt'):
        path = Path(contract['current_publication'][role])
        path, data = replace(path)
        if role == 'receipt':
            data['source_bindings_sha256'] = sh
        contract['current_publication'][role + '_sha256'] = persist(path, data)
    absolute_paths(contract)
    restored = tmp_path / 'restored'
    shutil.copytree(original, restored)
    return original, restored, contract


def test_explicit_mapping_replays_full_publication_without_original_reads(tmp_path, monkeypatch):
    original, restored, contract = restore_fixture(tmp_path)
    before = {p: p.read_bytes() for p in restored.rglob('*') if p.is_file()}
    read = Path.open
    def guarded(path, *args, **kwargs):
        assert not path.resolve().is_relative_to(original), 'original root read'
        return read(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    assert verify_workbook_publication(restored, contract, original_root=original).isoformat() == '2026-09-07'
    assert before == {p: p.read_bytes() for p in before}
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        verify_workbook_publication(restored, contract)


@pytest.mark.parametrize('mutation', ['missing', 'changed'])
def test_mapping_never_falls_back_to_valid_original(tmp_path, mutation):
    original, restored, contract = restore_fixture(tmp_path)
    path = restored / 'runtime/native/0.pdf'
    if mutation == 'missing':
        path.unlink()
    else:
        path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        verify_workbook_publication(restored, contract, original_root=original)


@pytest.mark.parametrize('relative', ['../outside.pdf', 'runtime/../../outside.pdf', 'config/file.pdf'])
def test_mapping_preserves_runtime_containment(tmp_path, relative):
    original = tmp_path / 'original'
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        _evidence_path(tmp_path / 'restored', str(original / relative), original_root=original)


def test_mapping_rejects_other_absolute_root_and_prefix_lookalike(tmp_path):
    original = tmp_path / 'original'
    for other in (tmp_path / 'other', tmp_path / 'original-extra'):
        with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
            _evidence_path(tmp_path / 'restored', str(other / 'runtime/a.pdf'), original_root=original)


def test_relative_bindings_still_require_exact_hash_with_mapping(tmp_path):
    path = tmp_path / 'runtime/file.pdf'
    path.parent.mkdir()
    path.write_bytes(b'file')
    assert _bound_bytes(tmp_path, 'runtime/file.pdf', hashlib.sha256(b'file').hexdigest(), original_root=tmp_path/'old') == b'file'
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        _bound_bytes(tmp_path, 'runtime/file.pdf', '0' * 64, original_root=tmp_path/'old')


def test_mapping_rejects_duplicate_pdf_aliases(tmp_path):
    original, restored, contract = restore_fixture(tmp_path)
    path = restored / 'runtime/wps_receipt.json'
    native = json.loads(path.read_text())
    sheets = list(native['sheets'].values())
    sheets[1]['pdf'] = 'runtime/native/0.pdf'
    sheets[1]['pdf_sha256'] = sheets[0]['pdf_sha256']
    path.write_text(json.dumps(native))
    contract['current_publication']['wps_receipt_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match='WPS_RECEIPT_MISMATCH'):
        verify_workbook_publication(restored, contract, original_root=original)


def test_mapping_rejects_restored_symlink_escape_when_supported(tmp_path):
    root = tmp_path / 'restored'
    (root / 'runtime').mkdir(parents=True)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'page.pdf').write_bytes(b'outside')
    try:
        (root / 'runtime/link').symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f'directory symlink unavailable on this host: {error}')
    original = tmp_path / 'original'
    with pytest.raises(ValueError, match='EVIDENCE_MISMATCH'):
        _bound_bytes(root, str(original / 'runtime/link/page.pdf'),
                     hashlib.sha256(b'outside').hexdigest(), original_root=original)
