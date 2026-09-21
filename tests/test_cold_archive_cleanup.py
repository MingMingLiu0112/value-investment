import hashlib
from datetime import datetime, timezone

import pytest

from value_investment_agent.evidence_tiering import sha256_file
from scripts.cleanup_cold_archive import verified_cleanup_paths


class _Connection:
    def __init__(self, row):
        self.row = row

    def execute(self, statement, params):
        row = self.row
        return type('Result', (), {'fetchall': lambda self: [row]})()


def test_cleanup_preflight_requires_recorded_matching_cold_archive(tmp_path):
    file = tmp_path / '600519' / 'annual.pdf'
    file.parent.mkdir()
    file.write_bytes(b'official-pdf')
    digest = sha256_file(file)
    manifest_digest = hashlib.sha256(b'manifest').hexdigest()
    candidate = {'disclosure_id': '00000000-0000-0000-0000-000000000001', 'sha256': digest,
                 'server_path': str(file), 'relative_path': '600519/annual.pdf', 'bytes': file.stat().st_size}
    row = {'disclosure_id': candidate['disclosure_id'], 'sha256': digest,
           'archive_status': 'cold_archived', 'archive_manifest_sha256': manifest_digest,
           'extraction_status': 'extracted'}

    assert verified_cleanup_paths({'mode': 'copy_and_verify_only', 'deletion_permitted': False,
                                   'candidates': [candidate]}, manifest_sha256=manifest_digest,
                                  evidence_root=tmp_path, connection=_Connection(row)) == [file]


def test_cleanup_preflight_rejects_unrecorded_archive(tmp_path):
    file = tmp_path / 'annual.pdf'
    file.write_bytes(b'official-pdf')
    digest = sha256_file(file)
    candidate = {'disclosure_id': '00000000-0000-0000-0000-000000000001', 'sha256': digest,
                 'server_path': str(file), 'relative_path': 'annual.pdf', 'bytes': file.stat().st_size}
    row = {'disclosure_id': candidate['disclosure_id'], 'sha256': digest,
           'archive_status': 'server_resident', 'archive_manifest_sha256': None,
           'extraction_status': 'extracted'}

    with pytest.raises(ValueError, match='Database archive receipt'):
        verified_cleanup_paths({'mode': 'copy_and_verify_only', 'deletion_permitted': False,
                                'candidates': [candidate]}, manifest_sha256='a' * 64,
                               evidence_root=tmp_path, connection=_Connection(row))
