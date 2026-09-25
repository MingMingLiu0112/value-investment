from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from .db import connect
from .backup_snapshot import compare_checks, table_checks


RESTORE_VERIFIER_VERSION = 'isolated-restore-v1'
RESTORE_TIMEOUT_SECONDS = 4 * 3600


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def _database_identity(database_url: str) -> dict[str, str]:
    parts = conninfo_to_dict(database_url)
    return {key: str(parts.get(key) or '') for key in ('host', 'port', 'dbname')}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_manifest(evidence_directory: Path) -> list[dict[str, str | int]]:
    """Record every first-party original in the daily backup manifest.

    The originals live beneath the same server backup root. Keeping their hash
    inventory alongside the PostgreSQL dump makes a restore drill able to prove
    both structured facts and the original disclosure evidence survived.
    """
    if not evidence_directory.is_dir():
        return []
    records: list[dict[str, str | int]] = []
    for path in sorted(evidence_directory.rglob("*.pdf")):
        records.append({
            "path": path.relative_to(evidence_directory.parent).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        })
    return records


def check_backup_space(target_dir: Path, database_bytes: int) -> dict[str, int]:
    """Conservative admission check, not a reservation against concurrent writers."""
    if type(database_bytes) is not int or database_bytes <= 0:
        raise RuntimeError('Database size unavailable; backup refused')
    reserve = 2 * 1024**3
    estimate = 2 * database_bytes + 64 * 1024**2
    free = shutil.disk_usage(target_dir).free
    if free < reserve + estimate:
        raise RuntimeError(f'Insufficient backup space: free={free}, '
                           f'estimated_write={estimate}, reserve={reserve}')
    return {'free_bytes': free, 'estimated_write_bytes': estimate, 'reserve_bytes': reserve}


def create_backup(database_url: str, target_dir: Path, container_runtime: str = 'podman', container_name: str = 'value-investment-postgres') -> Path:
    pg_dump = shutil.which('pg_dump')
    target_dir.mkdir(parents=True, exist_ok=True)
    backup_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    dump_path = target_dir / f'value-agent-{now:%Y%m%dT%H%M%SZ}-{backup_id}.dump'
    with connect(database_url) as snapshot_connection:
        snapshot_connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        database_bytes = snapshot_connection.execute(
            'SELECT pg_database_size(current_database()) AS bytes').fetchone()['bytes']
        check_backup_space(target_dir, database_bytes)
        snapshot = snapshot_connection.execute(
            'SELECT pg_export_snapshot() AS id, transaction_timestamp() AS captured_at').fetchone()
        checks = table_checks(snapshot_connection)
        space_check = check_backup_space(target_dir, database_bytes)
        if pg_dump:
            subprocess.run([pg_dump, '--snapshot', snapshot['id'], '--format=custom',
                            '--file', str(dump_path), database_url], check=True)
        else:
            runtime = shutil.which(container_runtime)
            if not runtime:
                raise RuntimeError(f'找不到 pg_dump 或容器运行时 {container_runtime}。')
            with dump_path.open('wb') as output:
                subprocess.run([runtime, 'exec', container_name, 'pg_dump',
                    '--snapshot', snapshot['id'], '-Fc', '-U', 'value_agent_admin',
                    'value_agent'], stdout=output, check=True)
    manifest = {
        'backup_id': str(backup_id), 'created_at': now.isoformat(), 'database_dump': dump_path.name,
        'sha256': sha256_file(dump_path), 'schema_version': '001_init',
        'evidence_files': evidence_manifest(target_dir / 'evidence'),
        'table_check_version': 1, 'table_checks': checks,
        'snapshot_at': snapshot['captured_at'].isoformat(),
        'space_preflight': space_check,
    }
    manifest_path = dump_path.with_suffix('.manifest.json')
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with connect(database_url) as connection:
        connection.execute(
            """INSERT INTO backup_audits(backup_id, created_at, backup_path, sha256, manifest, restore_status)
               VALUES (%s, %s, %s, %s, %s, 'created')""",
            (backup_id, now, str(dump_path), manifest['sha256'], json.dumps(manifest, ensure_ascii=False)),
        )
    return manifest_path


def validate_restore_target(database_url: str, restore_database_url: str) -> None:
    """Only the project's explicitly configured local drill database is writable."""
    try:
        source = conninfo_to_dict(database_url)
        target = conninfo_to_dict(restore_database_url)
    except Exception:
        raise RuntimeError('Invalid database configuration; restore refused') from None
    if (not source.get('dbname') or source['dbname'] == target.get('dbname')
            or target.get('dbname') != 'value_agent_restore'
            or target.get('host') != '127.0.0.1' or target.get('port') != '5433'
            or any(key in target for key in ('service', 'hostaddr', 'options'))):
        raise RuntimeError('Restore target is not the dedicated local drill database')


def _manifest_file(manifest_path: Path, value: str, *, dump: bool = False) -> Path:
    if not isinstance(value, str) or not value or '\\' in value:
        raise RuntimeError('Backup manifest contains an invalid file path')
    relative = Path(value)
    if relative.anchor or '..' in relative.parts or (dump and len(relative.parts) != 1):
        raise RuntimeError('Backup manifest file path escapes the backup directory')
    root = manifest_path.parent.resolve()
    candidate = (root / relative).resolve()
    if not candidate.is_relative_to(root) or not candidate.is_file():
        raise RuntimeError('Backup manifest file is missing or outside the backup directory')
    return candidate


def verify_restore(database_url: str, restore_database_url: str, backup_manifest: Path, container_runtime: str = 'podman', restore_container_name: str = 'value-investment-restore-postgres', attempt_started_at: datetime | None = None) -> dict:
    validate_restore_target(database_url, restore_database_url)
    started_at = attempt_started_at or datetime.now(timezone.utc)
    if started_at.tzinfo is None or started_at > datetime.now(timezone.utc):
        raise RuntimeError('Restore attempt start time is invalid')
    started = time.monotonic()
    pg_restore = shutil.which('pg_restore')
    manifest = json.loads(backup_manifest.read_text(encoding='utf-8'))
    if manifest.get('table_check_version') != 1 or not manifest.get('table_checks'):
        raise RuntimeError('Backup has no snapshot content baseline; create a new backup')
    if datetime.fromisoformat(manifest['snapshot_at']) > started_at:
        raise RuntimeError('Backup snapshot is in the future')
    dump_path = _manifest_file(backup_manifest, manifest['database_dump'], dump=True)
    if sha256_file(dump_path) != manifest['sha256']:
        raise RuntimeError('备份 Hash 不匹配，已拒绝恢复。')
    for evidence in manifest.get('evidence_files', []):
        evidence_path = _manifest_file(backup_manifest, evidence['path'])
        if sha256_file(evidence_path) != evidence['sha256']:
            raise RuntimeError(f"证据原件 Hash 不匹配，已拒绝恢复验证：{evidence['path']}")
    with connect(database_url) as source:
        registered = source.execute(
            'SELECT sha256, manifest FROM backup_audits WHERE backup_id = %s',
            (manifest['backup_id'],),
        ).fetchone()
    if (not registered or registered['sha256'] != manifest['sha256']
            or registered['manifest'] != manifest):
        raise RuntimeError('Backup manifest does not match the registered source audit')
    if not pg_restore:
        raise RuntimeError('pg_restore is required for the verified isolated target')
    result = subprocess.run(
        [pg_restore, '--clean', '--if-exists', '--no-owner', '--no-acl', '--dbname', restore_database_url, str(dump_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=RESTORE_TIMEOUT_SECONDS,
    )
    if result.returncode:
        raise RuntimeError(f'pg_restore failed: {result.stderr.strip()}')
    with connect(restore_database_url) as restored:
        restored.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        restored_checks = table_checks(restored)
    compare_checks(manifest['table_checks'], restored_checks)
    source_count = manifest['table_checks']['data_points']['rows']
    restore_duration_seconds = round(time.monotonic() - started, 2)
    completed_at = datetime.now(timezone.utc)
    rto_seconds = round((completed_at - started_at).total_seconds(), 2)
    backup_age_seconds = (completed_at - datetime.fromisoformat(manifest['snapshot_at'])).total_seconds()
    if backup_age_seconds < 0:
        raise RuntimeError('Backup snapshot is in the future')
    receipt = {
        'schema_version': RESTORE_VERIFIER_VERSION,
        'verifier_version': RESTORE_VERIFIER_VERSION,
        'action': 'no_order',
        'observed': 'actual',
        'backup_id': manifest['backup_id'], 'status': 'passed', 'rto_seconds': rto_seconds,
        'restore_duration_seconds': restore_duration_seconds,
        'data_points': source_count, 'evidence_files': len(manifest.get('evidence_files', [])),
        'verified_tables': len(restored_checks), 'snapshot_at': manifest['snapshot_at'],
        'backup_manifest': backup_manifest.name,
        'backup_manifest_sha256': sha256_file(backup_manifest),
        'database_dump_sha256': sha256_file(dump_path),
        'evidence_file_sha256': [item['sha256'] for item in manifest.get('evidence_files', [])],
        'source_database_identity': _database_identity(database_url),
        'restore_target_identity': _database_identity(restore_database_url),
        'restore_started_at': started_at.isoformat(),
        'restore_completed_at': completed_at.isoformat(),
        'backup_age_seconds': backup_age_seconds,
        'table_check_version': manifest['table_check_version'],
        'table_checks': restored_checks,
        'schema_migration_version': manifest.get('schema_version'),
        'restore_command_result': 'exit_0',
        'database_verifier_result': 'table_checks_equal',
    }
    receipt['receipt_sha256'] = hashlib.sha256(_canonical_bytes(receipt)).hexdigest()
    receipt_path = backup_manifest.with_name(f"restore-{receipt['receipt_sha256']}.json")
    with receipt_path.open('x', encoding='utf-8') as output:
        json.dump(receipt, output, ensure_ascii=False, indent=2)
        output.write('\n')
    with connect(database_url) as connection:
        updated = connection.execute(
            """UPDATE backup_audits SET restore_status = 'passed', rto_seconds = %s,
               rpo_seconds = %s, verified_at = now() WHERE backup_id = %s
               AND sha256 = %s AND manifest = %s""",
            (rto_seconds, receipt['backup_age_seconds'], manifest['backup_id'],
             manifest['sha256'], json.dumps(manifest, ensure_ascii=False)),
        )
        if updated.rowcount != 1:
            raise RuntimeError('Registered backup audit disappeared before restore receipt commit')
    return {**receipt, 'receipt_path': str(receipt_path)}


def verify_restore_receipt(
    database_url: str, restore_database_url: str, receipt_path: Path,
) -> dict:
    """Read-only recheck against local isolated restore; never trusts a summary alone."""
    validate_restore_target(database_url, restore_database_url)
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    expected_hash = receipt.pop('receipt_sha256', None)
    if expected_hash != hashlib.sha256(_canonical_bytes(receipt)).hexdigest():
        raise RuntimeError('Restore receipt hash mismatch')
    if (receipt.get('schema_version') != RESTORE_VERIFIER_VERSION
            or receipt.get('verifier_version') != RESTORE_VERIFIER_VERSION
            or receipt.get('action') != 'no_order'
            or receipt.get('observed') != 'actual'
            or receipt.get('status') != 'passed'
            or receipt.get('restore_command_result') != 'exit_0'
            or receipt.get('database_verifier_result') != 'table_checks_equal'):
        raise RuntimeError('Restore receipt is not an accepted verifier result')
    if (receipt.get('source_database_identity') != _database_identity(database_url)
            or receipt.get('restore_target_identity') != _database_identity(restore_database_url)):
        raise RuntimeError('Restore receipt database identity mismatch')
    try:
        started_at = datetime.fromisoformat(receipt['restore_started_at'])
        completed_at = datetime.fromisoformat(receipt['restore_completed_at'])
        snapshot_at = datetime.fromisoformat(receipt['snapshot_at'])
        wall_seconds = (completed_at - started_at).total_seconds()
        backup_age = (completed_at - snapshot_at).total_seconds()
        if (started_at.tzinfo is None or completed_at.tzinfo is None or snapshot_at.tzinfo is None
                or wall_seconds < 0 or backup_age < 0
                or abs(wall_seconds - float(receipt['rto_seconds'])) > 2
                or abs(backup_age - float(receipt['backup_age_seconds'])) > 2):
            raise ValueError('inconsistent timing')
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError('Restore receipt timing is invalid') from exc
    manifest_path = _manifest_file(receipt_path, receipt['backup_manifest'], dump=True)
    if sha256_file(manifest_path) != receipt.get('backup_manifest_sha256'):
        raise RuntimeError('Restore manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    dump_path = _manifest_file(manifest_path, manifest['database_dump'], dump=True)
    if (sha256_file(dump_path) != manifest.get('sha256')
            or manifest.get('sha256') != receipt.get('database_dump_sha256')
            or manifest.get('backup_id') != receipt.get('backup_id')):
        raise RuntimeError('Restore dump or backup identity mismatch')
    evidence = manifest.get('evidence_files', [])
    if [item['sha256'] for item in evidence] != receipt.get('evidence_file_sha256'):
        raise RuntimeError('Restore evidence inventory mismatch')
    for item in evidence:
        if sha256_file(_manifest_file(manifest_path, item['path'])) != item['sha256']:
            raise RuntimeError('Restore evidence file hash mismatch')
    if (manifest.get('table_check_version') != receipt.get('table_check_version')
            or manifest.get('table_checks') != receipt.get('table_checks')
            or manifest.get('schema_version') != receipt.get('schema_migration_version')
            or manifest.get('snapshot_at') != receipt.get('snapshot_at')
            or len(evidence) != receipt.get('evidence_files')
            or len(manifest['table_checks']) != receipt.get('verified_tables')):
        raise RuntimeError('Restore snapshot baseline mismatch')
    with connect(database_url) as source:
        registered = source.execute(
            'SELECT sha256, manifest, restore_status, rto_seconds, rpo_seconds '
            'FROM backup_audits WHERE backup_id = %s',
            (manifest['backup_id'],),
        ).fetchone()
    if (not registered or registered['sha256'] != manifest['sha256']
            or registered['manifest'] != manifest or registered['restore_status'] != 'passed'
            or abs(float(registered['rto_seconds']) - float(receipt['rto_seconds'])) > 0.01
            or abs(float(registered['rpo_seconds']) - backup_age) > 2):
        raise RuntimeError('Restore receipt is not bound to a passed source audit')
    with connect(restore_database_url) as restored:
        restored.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        compare_checks(manifest['table_checks'], table_checks(restored))
    return {**receipt, 'receipt_sha256': expected_hash,
            'receipt_file_sha256': sha256_file(receipt_path),
            'verified_at': datetime.now(timezone.utc).isoformat()}
