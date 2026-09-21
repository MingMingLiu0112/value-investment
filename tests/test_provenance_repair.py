import hashlib

import pytest

from value_investment_agent.provenance_repair import verify_archive, repair_batch


def fixture(tmp_path):
    path = tmp_path / 'official.pdf'
    path.write_bytes(b'%PDF retained evidence')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(local_path=str(path), official_hash=digest,
                stored_hash=hashlib.sha256(f'official_evidence_sha256={digest}'.encode()).hexdigest())


def test_only_recognized_reference_and_matching_bytes_are_repairable(tmp_path):
    row = fixture(tmp_path)
    assert verify_archive(row) == row['official_hash']
    row['stored_hash'] = '0' * 64
    with pytest.raises(ValueError, match='recognized'):
        verify_archive(row)


def test_changed_pdf_is_not_repaired(tmp_path):
    row = fixture(tmp_path)
    from pathlib import Path
    Path(row['local_path']).write_bytes(b'different report')
    with pytest.raises(ValueError, match='mismatch'):
        verify_archive(row)


def test_dry_run_does_not_write(tmp_path):
    row = fixture(tmp_path)

    class Connection:
        def execute(self, sql, params):
            assert sql.lstrip().startswith('SELECT')
            return self

        def fetchall(self):
            return [row]

    assert repair_batch(Connection(), apply=False) == {'checked': 1, 'repaired': 0, 'apply': False}


def test_invalid_batch_limit_rejected():
    with pytest.raises(ValueError, match='limit'):
        repair_batch(None, limit=1001)
