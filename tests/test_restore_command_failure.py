import json
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
        'table_check_version': 1, 'table_checks': {'data_points': {'rows': 1, 'sha256': 'test'}}}), encoding='utf-8')
    monkeypatch.setattr(backup.shutil, 'which', lambda _: '/test/pg_restore')
    monkeypatch.setattr(backup.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stderr=stderr))
    def forbidden_connect(*args):
        pytest.fail('Failed restore must not proceed to success auditing')
    monkeypatch.setattr(backup, 'connect', forbidden_connect)
    with pytest.raises(RuntimeError, match='pg_restore failed'):
        backup.verify_restore('postgresql://127.0.0.1:5432/value_agent',
                              'postgresql://127.0.0.1:5433/value_agent_restore', manifest)
