from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from value_investment_agent import backup


@pytest.mark.parametrize('size', [None, 0, -1, '100', True])
def test_unknown_size_refuses(tmp_path, size):
    with pytest.raises(RuntimeError, match='size unavailable'):
        backup.check_backup_space(tmp_path, size)


def test_reserve_boundary(tmp_path, monkeypatch):
    needed = 2 * 1024**3 + 200 + 64 * 1024**2
    monkeypatch.setattr(backup.shutil, 'disk_usage', lambda _: SimpleNamespace(free=needed - 1))
    with pytest.raises(RuntimeError, match='Insufficient'):
        backup.check_backup_space(tmp_path, 100)
    monkeypatch.setattr(backup.shutil, 'disk_usage', lambda _: SimpleNamespace(free=needed))
    assert backup.check_backup_space(tmp_path, 100)['reserve_bytes'] == 2 * 1024**3


def test_empty_evidence_directory_refuses_backup_before_database_access(tmp_path, monkeypatch):
    (tmp_path / 'evidence').mkdir()
    connect = Mock(side_effect=AssertionError('database must not be accessed'))
    monkeypatch.setattr(backup, 'connect', connect)
    with pytest.raises(RuntimeError, match='No evidence originals'):
        backup.create_backup('unused', tmp_path)
    connect.assert_not_called()
    assert not list(tmp_path.glob('*.manifest.json'))


@pytest.mark.parametrize('drop_after_checks', [False, True])
def test_low_disk_never_starts_dump_or_creates_manifest(tmp_path, monkeypatch, drop_after_checks):
    (tmp_path / 'evidence').mkdir()
    (tmp_path / 'evidence' / 'original.pdf').write_bytes(b'evidence')
    connection = Mock()
    connection.execute.return_value.fetchone.return_value = {'bytes': 100, 'id': 'snapshot'}

    @contextmanager
    def connect(_):
        yield connection

    monkeypatch.setattr(backup, 'connect', connect)
    free = iter([10 * 1024**3, 1] if drop_after_checks else [1])
    monkeypatch.setattr(backup.shutil, 'disk_usage', lambda _: SimpleNamespace(free=next(free)))
    checks = Mock(return_value={})
    run = Mock()
    monkeypatch.setattr(backup, 'table_checks', checks)
    monkeypatch.setattr(backup.subprocess, 'run', run)
    with pytest.raises(RuntimeError, match='Insufficient'):
        backup.create_backup('unused', tmp_path)
    run.assert_not_called()
    assert list(tmp_path.iterdir()) == [tmp_path / 'evidence']
    assert checks.call_count == int(drop_after_checks)
