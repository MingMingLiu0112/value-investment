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


def verify_restore(database_url: str, restore_database_url: str, backup_manifest: Path, container_runtime: str = 'podman', restore_container_name: str = 'value-investment-restore-postgres') -> dict:
    validate_restore_target(database_url, restore_database_url)
    pg_restore = shutil.which('pg_restore')
    manifest = json.loads(backup_manifest.read_text(encoding='utf-8'))
    if manifest.get('table_check_version') != 1 or not manifest.get('table_checks'):
        raise RuntimeError('Backup has no snapshot content baseline; create a new backup')
    dump_path = backup_manifest.with_name(manifest['database_dump'])
    if sha256_file(dump_path) != manifest['sha256']:
        raise RuntimeError('备份 Hash 不匹配，已拒绝恢复。')
    for evidence in manifest.get('evidence_files', []):
        evidence_path = backup_manifest.parent / evidence['path']
        if not evidence_path.is_file():
            raise RuntimeError(f"证据原件缺失，已拒绝恢复验证：{evidence['path']}")
        if sha256_file(evidence_path) != evidence['sha256']:
            raise RuntimeError(f"证据原件 Hash 不匹配，已拒绝恢复验证：{evidence['path']}")
    started = time.monotonic()
    if pg_restore:
        result = subprocess.run(
            [pg_restore, '--clean', '--if-exists', '--no-owner', '--no-acl', '--dbname', restore_database_url, str(dump_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(f'pg_restore failed: {result.stderr.strip()}')
    else:
        runtime = shutil.which(container_runtime)
        if not runtime:
            raise RuntimeError(f'找不到 pg_restore 或容器运行时 {container_runtime}。')
        with dump_path.open('rb') as input_file:
            subprocess.run([runtime, 'exec', '-i', restore_container_name, 'pg_restore', '--clean', '--if-exists', '--no-owner', '-U', 'value_agent_admin', '-d', 'value_agent_restore'], stdin=input_file, check=True)
    with connect(restore_database_url) as restored:
        restored.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        restored_checks = table_checks(restored)
    compare_checks(manifest['table_checks'], restored_checks)
    source_count = manifest['table_checks']['data_points']['rows']
    rto_seconds = round(time.monotonic() - started, 2)
    with connect(database_url) as connection:
        connection.execute(
            """UPDATE backup_audits SET restore_status = 'passed', rto_seconds = %s, verified_at = now()
               WHERE backup_id = %s""",
            (rto_seconds, manifest['backup_id']),
        )
    return {
        'backup_id': manifest['backup_id'], 'status': 'passed', 'rto_seconds': rto_seconds,
        'data_points': source_count, 'evidence_files': len(manifest.get('evidence_files', [])),
        'verified_tables': len(restored_checks), 'snapshot_at': manifest['snapshot_at'],
    }
