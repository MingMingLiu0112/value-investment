import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from value_investment_agent import backup


@pytest.mark.parametrize('stderr', [
    'unrecognized configuration parameter "transaction_timeout"',
    'unrecognized configuration parameter "transaction_timeout"\nERROR: could not create table',
    'ERROR: connection lost',
])
def test_any_failed_restore_cannot_be_marked_passed(tmp_path, monkeypatch, stderr):
    dump = tmp_path / 'test.dump'
    dump.write_bytes(b'fixture')
    manifest = tmp_path / 'test.manifest.json'
    manifest.write_text(json.dumps({'database_dump': dump.name,
        'sha256': backup.sha256_file(dump), 'backup_id': 'test',
        'snapshot_at': '2026-09-24T00:00:00+00:00',
        'table_check_version': 1, 'table_checks': {'data_points': {'rows': 1, 'sha256': 'test'}}}), encoding='utf-8')
    monkeypatch.setattr(backup.shutil, 'which', lambda _: '/test/pg_restore')
    monkeypatch.setattr(backup.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr=stderr))
    class Source:
        def execute(self, *_):
            return self

        def fetchone(self):
            return {'sha256': backup.sha256_file(dump),
                    'manifest': json.loads(manifest.read_text(encoding='utf-8'))}

    @contextmanager
    def source_connect(*_):
        yield Source()

    monkeypatch.setattr(backup, 'connect', source_connect)
    with pytest.raises(RuntimeError, match='pg_restore failed'):
        backup.verify_restore('postgresql://127.0.0.1:5432/value_agent',
                              'postgresql://127.0.0.1:5433/value_agent_restore', manifest)


@pytest.mark.parametrize('field,value', [
    ('database_dump', '../outside.dump'),
    ('database_dump', '/tmp/outside.dump'),
    ('evidence', '../outside.pdf'),
    ('evidence', '/tmp/outside.pdf'),
])
def test_restore_rejects_manifest_paths_outside_backup(tmp_path, monkeypatch, field, value):
    backup_dir = tmp_path / 'backups'
    backup_dir.mkdir()
    outside = tmp_path / ('outside.dump' if field == 'database_dump' else 'outside.pdf')
    outside.write_bytes(b'fixture')
    dump = backup_dir / 'test.dump'
    dump.write_bytes(b'fixture')
    manifest_data = {
        'database_dump': value if field == 'database_dump' else dump.name,
        'sha256': backup.sha256_file(dump),
        'snapshot_at': '2026-09-24T00:00:00+00:00',
        'table_check_version': 1,
        'table_checks': {'data_points': {'rows': 1}},
        'evidence_files': ([{'path': value, 'sha256': backup.sha256_file(outside)}]
                           if field == 'evidence' else []),
    }
    manifest = backup_dir / 'test.manifest.json'
    manifest.write_text(json.dumps(manifest_data), encoding='utf-8')
    monkeypatch.setattr(backup, 'connect', lambda *_: pytest.fail('unsafe path reached database'))
    with pytest.raises(RuntimeError, match='escapes the backup directory'):
        backup.verify_restore('postgresql://127.0.0.1:5432/value_agent',
                              'postgresql://127.0.0.1:5433/value_agent_restore', manifest)
