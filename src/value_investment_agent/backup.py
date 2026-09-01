from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .db import connect


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def create_backup(database_url: str, target_dir: Path, container_runtime: str = 'podman', container_name: str = 'value-investment-postgres') -> Path:
    pg_dump = shutil.which('pg_dump')
    target_dir.mkdir(parents=True, exist_ok=True)
    backup_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    dump_path = target_dir / f'value-agent-{now:%Y%m%dT%H%M%SZ}-{backup_id}.dump'
    if pg_dump:
        subprocess.run([pg_dump, '--format=custom', '--file', str(dump_path), database_url], check=True)
    else:
        runtime = shutil.which(container_runtime)
        if not runtime:
            raise RuntimeError(f'找不到 pg_dump 或容器运行时 {container_runtime}。')
        with dump_path.open('wb') as output:
            subprocess.run([runtime, 'exec', container_name, 'pg_dump', '-Fc', '-U', 'value_agent_admin', 'value_agent'], stdout=output, check=True)
    manifest = {
        'backup_id': str(backup_id), 'created_at': now.isoformat(), 'database_dump': dump_path.name,
        'sha256': sha256_file(dump_path), 'schema_version': '001_init',
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


def verify_restore(database_url: str, restore_database_url: str, backup_manifest: Path, container_runtime: str = 'podman', restore_container_name: str = 'value-investment-restore-postgres') -> dict:
    if database_url == restore_database_url:
        raise RuntimeError('RESTORE_DATABASE_URL 不得与 DATABASE_URL 相同。')
    pg_restore = shutil.which('pg_restore')
    manifest = json.loads(backup_manifest.read_text(encoding='utf-8'))
    dump_path = backup_manifest.with_name(manifest['database_dump'])
    if sha256_file(dump_path) != manifest['sha256']:
        raise RuntimeError('备份 Hash 不匹配，已拒绝恢复。')
    started = time.monotonic()
    if pg_restore:
        subprocess.run([pg_restore, '--clean', '--if-exists', '--no-owner', '--dbname', restore_database_url, str(dump_path)], check=True)
    else:
        runtime = shutil.which(container_runtime)
        if not runtime:
            raise RuntimeError(f'找不到 pg_restore 或容器运行时 {container_runtime}。')
        with dump_path.open('rb') as input_file:
            subprocess.run([runtime, 'exec', '-i', restore_container_name, 'pg_restore', '--clean', '--if-exists', '--no-owner', '-U', 'value_agent_admin', '-d', 'value_agent_restore'], stdin=input_file, check=True)
    with connect(database_url) as source, connect(restore_database_url) as restored:
        source_count = source.execute('SELECT count(*) AS count FROM data_points').fetchone()['count']
        restored_count = restored.execute('SELECT count(*) AS count FROM data_points').fetchone()['count']
    if source_count != restored_count:
        raise RuntimeError(f'恢复校验失败：源数据点 {source_count}，恢复库 {restored_count}')
    rto_seconds = round(time.monotonic() - started, 2)
    with connect(database_url) as connection:
        connection.execute(
            """UPDATE backup_audits SET restore_status = 'passed', rto_seconds = %s, verified_at = now()
               WHERE backup_id = %s""",
            (rto_seconds, manifest['backup_id']),
        )
    return {'backup_id': manifest['backup_id'], 'status': 'passed', 'rto_seconds': rto_seconds, 'data_points': source_count}
