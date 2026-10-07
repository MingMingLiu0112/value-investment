import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
NAME = 'A股价值投资_Agent前端智能跟踪模板.xlsx'


def fixture(tmp_path):
    root = tmp_path / 'project'
    (root / 'scripts').mkdir(parents=True)
    (root / 'config').mkdir()
    for relative in ('scripts/open_current_trial_workbook.py', 'config/current-trial-workbook.json'):
        (root / relative).write_bytes((ROOT / relative).read_bytes())
    return root


def run(root, workbook=None, *args):
    env = dict(os.environ)
    env.pop('WORKBOOK_PATH', None)
    if workbook is not None: env['WORKBOOK_PATH'] = str(workbook)
    return subprocess.run([sys.executable, '-X', 'utf8', str(root/'scripts/open_current_trial_workbook.py'), *args],
        cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')


def bind_pointer_to_workbook(root, workbook):
    pointer_path = root/'config/current-trial-workbook.json'
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    pointer['canonical_workbook_sha256'] = hashlib.sha256(workbook.read_bytes()).hexdigest()
    pointer_path.write_text(json.dumps(pointer), encoding='utf-8')


def test_current_entry_is_only_the_temporary_canonical_workbook(tmp_path):
    root = fixture(tmp_path)
    path = tmp_path / NAME
    Workbook().save(path)
    bind_pointer_to_workbook(root, path)
    pointer = json.loads((root/'config/current-trial-workbook.json').read_text(encoding='utf-8'))
    assert pointer['workbook_source'] == 'WORKBOOK_PATH'
    assert pointer['current_trial_pointer'] == 'CANONICAL_WORKBOOK'
    assert 'workbook' not in pointer and 'workbook_path' not in pointer
    assert 'workbook_sha256' not in pointer
    result = run(root, path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['workbook'] == str(path.resolve())
    assert json.loads(result.stdout)['action'] == 'no_order'


@pytest.mark.parametrize('value', [None, 'missing.xlsx', 'other.xlsx'])
def test_missing_or_wrong_workbook_path_fails_closed(tmp_path, value):
    root = fixture(tmp_path)
    path = None if value is None else tmp_path/value
    if value == 'other.xlsx':
        Workbook().save(path)
        bind_pointer_to_workbook(root, path)
    assert run(root, path).returncode != 0


def test_canonical_workbook_hash_mismatch_fails_closed(tmp_path):
    root = fixture(tmp_path)
    path = tmp_path / NAME
    Workbook().save(path)
    pointer_path = root/'config/current-trial-workbook.json'
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    pointer['canonical_workbook_sha256'] = '0' * 64
    pointer_path.write_text(json.dumps(pointer), encoding='utf-8')
    result = run(root, path)
    assert result.returncode != 0
    assert 'CANONICAL_WORKBOOK_HASH_MISMATCH' in result.stderr


def test_canonical_pointer_requires_a_valid_hash(tmp_path):
    root = fixture(tmp_path)
    path = tmp_path / NAME
    Workbook().save(path)
    pointer_path = root/'config/current-trial-workbook.json'
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    pointer.pop('canonical_workbook_sha256')
    pointer_path.write_text(json.dumps(pointer), encoding='utf-8')
    result = run(root, path)
    assert result.returncode != 0
    assert 'CANONICAL_WORKBOOK_POINTER_HASH_INVALID' in result.stderr


def test_runtime_preview_requires_explicit_flag_and_hash(tmp_path):
    root = fixture(tmp_path)
    (root/'runtime').mkdir()
    preview = root/'runtime/preview.xlsx'
    Workbook().save(preview)
    digest = hashlib.sha256(preview.read_bytes()).hexdigest()
    result = run(root, None, '--historical-preview', 'runtime/preview.xlsx', '--preview-sha256', digest)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['current_trial_pointer'] == 'NOT_CURRENT'
    assert run(root, None, '--historical-preview', 'runtime/preview.xlsx').returncode != 0
    assert run(root, None, '--historical-preview', 'runtime/preview.xlsx', '--preview-sha256', '0'*64).returncode != 0


def test_runtime_source_cannot_become_default_pointer(tmp_path):
    root = fixture(tmp_path)
    pointer_path = root/'config/current-trial-workbook.json'
    pointer = json.loads(pointer_path.read_text(encoding='utf-8'))
    pointer['workbook_source'] = 'PRODUCT_UX_RUNTIME'
    pointer_path.write_text(json.dumps(pointer), encoding='utf-8')
    assert run(root).returncode != 0
