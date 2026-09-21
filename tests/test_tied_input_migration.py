import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest


def load_script(monkeypatch):
    path = Path(__file__).parents[1] / 'scripts'
    monkeypatch.syspath_prepend(str(path))
    spec = importlib.util.spec_from_file_location('migration_under_test', path / 'migrate_tied_inputs.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.rolled_back = False
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.committed = kind is None and not self.rolled_back

    def execute(self, sql, args=None):
        self.calls.append(sql)
        return SimpleNamespace(fetchall=lambda: self.rows if 'd.local_path' in sql else [])

    def rollback(self):
        self.rolled_back = True


def setup(monkeypatch, tmp_path, argv, valid_hash=True):
    module = load_script(monkeypatch)
    pdf = tmp_path / 'report.pdf'
    pdf.write_bytes(b'retained test evidence')
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    connection = Connection([{'local_path': str(pdf), 'sha256': digest if valid_hash else 'changed'}])
    changes = [{'reason': 'reviewed', 'new_id': str(uuid.uuid4()), 'old_id': str(uuid.uuid4()),
                'sha256': digest, 'previous_metadata': {}}]
    monkeypatch.setattr(module, 'connect', lambda _: connection)
    monkeypatch.setattr(module, 'get_settings', lambda: SimpleNamespace(database_url='unused'))
    monkeypatch.setattr(module, 'plan_resolution', lambda _: changes)
    monkeypatch.setattr(module, 'refresh_affected', lambda _: ['000612', '002125', '300014'])
    monkeypatch.setattr(module, 'begin_run', lambda *_: uuid.uuid4())
    monkeypatch.setattr(module, 'end_run', lambda *_: None)
    monkeypatch.setattr('sys.argv', ['migrate_tied_inputs.py', *argv])
    return module, connection


def test_default_rehearsal_rolls_back_writes(monkeypatch, tmp_path):
    module, connection = setup(monkeypatch, tmp_path, [])
    module.main()
    assert connection.rolled_back and not connection.committed
    assert any('UPDATE data_points' in sql for sql in connection.calls)
    assert not any('DELETE' in sql for sql in connection.calls)


def test_apply_preserves_records_and_commits(monkeypatch, tmp_path):
    module, connection = setup(monkeypatch, tmp_path, ['--apply'])
    module.main()
    assert connection.committed and not connection.rolled_back
    assert not any('DELETE' in sql for sql in connection.calls)


def test_changed_original_hash_prevents_any_update(monkeypatch, tmp_path):
    module, connection = setup(monkeypatch, tmp_path, ['--apply'], valid_hash=False)
    with pytest.raises(ValueError, match='hash'):
        module.main()
    assert not connection.committed
    assert not any('UPDATE' in sql for sql in connection.calls)


def test_refresh_failure_does_not_commit_partial_migration(monkeypatch, tmp_path):
    module, connection = setup(monkeypatch, tmp_path, ['--apply'])
    def fail(_):
        raise RuntimeError('refresh failed')
    monkeypatch.setattr(module, 'refresh_affected', fail)
    with pytest.raises(RuntimeError, match='refresh failed'):
        module.main()
    assert not connection.committed
