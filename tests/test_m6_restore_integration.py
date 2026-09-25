"""A disposable two-database restore drill; never uses production credentials."""

import os
from pathlib import Path
import shutil
import uuid

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from value_investment_agent.backup import (
    create_backup, verify_restore, verify_restore_receipt,
)
from value_investment_agent.m6_operational_readiness import (
    DONE, assess_restore_evidence, load_config,
)


ROOT = Path(__file__).parents[1]
SOURCE_DSN = os.environ.get('C3_TEST_POSTGRES_DSN')
RESTORE_DSN = os.environ.get('M6_TEST_RESTORE_DSN')


@pytest.mark.skipif(not SOURCE_DSN or not RESTORE_DSN, reason='two disposable PostgreSQL DSNs required')
def test_disposable_backup_restore_receipt_and_m6_binding(tmp_path):
    if not shutil.which('pg_dump') or not shutil.which('pg_restore'):
        pytest.fail('PostgreSQL client binaries are required for the isolated drill')
    database = 'm6_drill_' + uuid.uuid4().hex[:16]
    with psycopg.connect(SOURCE_DSN, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    source = make_conninfo(SOURCE_DSN, dbname=database)
    try:
        with psycopg.connect(source, autocommit=True) as connection:
            connection.execute('CREATE TABLE data_points (id integer PRIMARY KEY, value text NOT NULL)')
            connection.execute("INSERT INTO data_points VALUES (1, 'first-party-fact')")
            connection.execute('''CREATE TABLE backup_audits (
                backup_id uuid PRIMARY KEY, created_at timestamptz NOT NULL,
                backup_path text NOT NULL, sha256 text NOT NULL,
                manifest jsonb NOT NULL, restore_status text NOT NULL,
                rto_seconds numeric, rpo_seconds numeric, verified_at timestamptz)''')
        evidence_dir = tmp_path / 'evidence'
        evidence_dir.mkdir()
        (evidence_dir / 'synthetic-original.pdf').write_bytes(b'isolated synthetic evidence')
        manifest = create_backup(source, tmp_path)
        (evidence_dir / 'synthetic-original.pdf').unlink()
        result = verify_restore(source, RESTORE_DSN, manifest)
        verified = verify_restore_receipt(source, RESTORE_DSN, Path(result['receipt_path']))
        criterion = assess_restore_evidence(
            load_config(ROOT / 'config/m6-operational-preflight-v1.json'), [],
            receipt_path=Path(result['receipt_path']),
            source_database_url=source, restore_database_url=RESTORE_DSN,
        )
        assert criterion['status'] == DONE
        assert criterion['evidence']['table_check_count'] == 2
        assert verified['database_verifier_result'] == 'table_checks_equal'
        assert verified['evidence_recovery_result'] == 'copied_and_hash_verified'
        assert verified['receipt_sha256'] == result['receipt_sha256']
        artifact_dir = os.environ.get('M6_TEST_ARTIFACT_DIR')
        if artifact_dir:
            shutil.copytree(tmp_path, Path(artifact_dir))
    finally:
        with psycopg.connect(SOURCE_DSN, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))
