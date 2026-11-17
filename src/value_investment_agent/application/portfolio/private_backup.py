"""Minimal private ledger backup and restore (WEB-D2 P0.3).

A backup bundle is a byte-verbatim copy of the private portfolio journal plus
a canonical manifest recording the source digest, the copied digest, the
record count, the chain head and whether the source chain was valid when the
copy was taken. Verification reuses the production journal validator and never
repairs, truncates or rewrites a damaged copy. Restore refuses anything that
does not verify, keeps a pre-restore safety bundle of the bytes it replaces,
and writes through a same-directory temporary file plus ``os.replace``. This
module never submits an order and never writes outside the private journal's
own directory tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ...domain.portfolio.dual_sleeve_records import canonical_bytes
from .private_journal_lock import InterProcessLock, LockTimeout
from .private_portfolio_service import (
    JournalValidationError,
    PrivateJournal,
    PrivateStoreUnavailable,
)

BACKUP_SCHEMA = "private-portfolio-backup-v1"
MANIFEST_NAME = "manifest.json"
JOURNAL_NAME = "journal.jsonl"
BACKUP_DIRECTORY_NAME = "backups"
BACKUP_ID_PREFIX = "backup-"
SAFETY_ID_PREFIX = "pre-restore-"
_MAX_ID_ATTEMPTS = 10


def create_backup(
    journal_path: Path,
    *,
    backup_root: Path | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Copy the live journal bytes into a new bundle inside the private tree."""
    source = Path(journal_path)
    if not source.exists():
        raise FileNotFoundError(f"私人流水不存在，无法备份：{source}")
    if backup_root is None:
        root = source.parent / BACKUP_DIRECTORY_NAME
    else:
        root = _require_backup_root(source.parent, Path(backup_root))
    moment = _require_aware(created_at)
    lock = _acquire_journal_lock(source)
    try:
        return _create_bundle(
            source,
            backup_root=root,
            created_at=moment,
            prefix=BACKUP_ID_PREFIX,
        )
    finally:
        lock.release()


def verify_backup(backup_dir: Path) -> dict[str, Any]:
    """Recompute digests, the manifest digest and the chain without repairing."""
    directory = Path(backup_dir)
    result: dict[str, Any] = {
        "status": "INVALID",
        "reason": None,
        "backup_id": directory.name,
        "record_count": None,
        "head_record_sha256": None,
        "source_status": None,
        "action": "no_order",
    }
    if not directory.exists():
        result["status"] = "MISSING"
        result["reason"] = f"备份目录不存在：{directory}"
        return result
    if not directory.is_dir():
        result["reason"] = "备份路径不是目录"
        return result
    manifest_path = directory / MANIFEST_NAME
    journal_path = directory / JOURNAL_NAME
    if not manifest_path.is_file():
        result["reason"] = "备份缺少 manifest.json"
        return result
    if not journal_path.is_file():
        result["reason"] = "备份缺少 journal.jsonl"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        result["reason"] = f"manifest.json 无法读取：{error}"
        return result
    if not isinstance(manifest, dict):
        result["reason"] = "manifest.json 不是对象"
        return result
    if manifest.get("schema_version") != BACKUP_SCHEMA:
        result["reason"] = "manifest.json 的 schema 无法识别"
        return result
    identifier = manifest.get("backup_id")
    if isinstance(identifier, str) and identifier:
        result["backup_id"] = identifier
    count = manifest.get("record_count")
    result["record_count"] = (
        count if isinstance(count, int) and not isinstance(count, bool) else None
    )
    head = manifest.get("head_record_sha256")
    result["head_record_sha256"] = head if isinstance(head, str) else None
    source_status = manifest.get("source_status")
    result["source_status"] = source_status if isinstance(source_status, str) else None
    digest = manifest.get("manifest_sha256")
    if not isinstance(digest, str):
        result["reason"] = "manifest.json 缺少自身摘要"
        return result
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    if _canonical_sha256(payload) != digest:
        result["reason"] = "manifest.json 的自身摘要不一致"
        return result
    try:
        journal_bytes = journal_path.read_bytes()
    except OSError as error:
        result["reason"] = f"journal.jsonl 无法读取：{error}"
        return result
    if hashlib.sha256(journal_bytes).hexdigest() != manifest.get("copied_sha256"):
        result["reason"] = "journal.jsonl 的字节与 manifest 记录的摘要不一致"
        return result
    try:
        records = PrivateJournal(journal_path).read()
    except JournalValidationError as error:
        result["reason"] = f"哈希链校验失败：{error}"
        return result
    recomputed_count = len(records)
    recomputed_head = str(records[-1]["record_sha256"]) if records else None
    result["record_count"] = recomputed_count
    result["head_record_sha256"] = recomputed_head
    if count != recomputed_count:
        result["reason"] = "备份记录数与 manifest 不一致"
        return result
    if head != recomputed_head:
        result["reason"] = "备份链头摘要与 manifest 不一致"
        return result
    result["status"] = "VERIFIED"
    return result


def list_backups(backup_root: Path) -> list[dict[str, Any]]:
    """List bundles newest first; partially written bundles show as INVALID."""
    root = Path(backup_root)
    if not root.is_dir():
        return []
    keyed: list[tuple[str, str, dict[str, Any]]] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        verification = verify_backup(child)
        created = _manifest_created_at(child)
        try:
            modified = child.stat().st_mtime
        except OSError:
            modified = 0.0
        effective = created or datetime.fromtimestamp(modified, tz=timezone.utc).isoformat()
        keyed.append(
            (
                effective,
                child.name,
                {
                    "backup_id": verification["backup_id"],
                    "path": str(child),
                    "created_at": created,
                    "status": verification["status"],
                    "reason": verification["reason"],
                    "record_count": verification["record_count"],
                    "head_record_sha256": verification["head_record_sha256"],
                    "source_status": verification["source_status"],
                    "action": "no_order",
                },
            )
        )
    keyed.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [entry for _, _, entry in keyed]


def restore_backup(
    backup_dir: Path,
    journal_path: Path,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    """Replace the journal with a verified backup after an explicit confirmation."""
    if confirm is not True:
        raise ValueError("恢复私人账本需要明确用户确认")
    verification = verify_backup(backup_dir)
    if verification["status"] != "VERIFIED":
        raise ValueError(
            f"拒绝恢复未通过校验的备份（{verification['status']}）：{verification['reason']}"
        )
    directory = Path(backup_dir)
    target = Path(journal_path)
    restored_bytes = (directory / JOURNAL_NAME).read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = _acquire_journal_lock(target)
    try:
        safety_backup_id = None
        if target.exists() and target.read_bytes():
            safety = _create_bundle(
                target,
                backup_root=target.parent / BACKUP_DIRECTORY_NAME,
                created_at=datetime.now(timezone.utc),
                prefix=SAFETY_ID_PREFIX,
            )
            safety_backup_id = str(safety["backup_id"])
        _write_journal_atomic(target, restored_bytes)
        try:
            records = PrivateJournal(target).read()
        except JournalValidationError as error:
            raise RuntimeError(f"恢复后的私人流水校验失败：{error}") from error
    finally:
        lock.release()
    restored_head = str(records[-1]["record_sha256"]) if records else None
    return {
        "status": "RESTORED",
        "backup_id": verification["backup_id"],
        "restored_record_count": len(records),
        "head_record_sha256": restored_head,
        "safety_backup_id": safety_backup_id,
        "action": "no_order",
    }


def _create_bundle(
    journal_path: Path,
    *,
    backup_root: Path,
    created_at: datetime,
    prefix: str,
) -> dict[str, Any]:
    source_bytes = journal_path.read_bytes()
    source_digest = hashlib.sha256(source_bytes).hexdigest()
    source_status = "VALID"
    source_invalid_reason = None
    try:
        records = PrivateJournal(journal_path).read()
    except JournalValidationError as error:
        source_status = "INVALID"
        source_invalid_reason = str(error)
        record_count, head = _salvage_counts(source_bytes)
    else:
        record_count = len(records)
        head = str(records[-1]["record_sha256"]) if records else None
    created_iso = _iso_utc(created_at)
    bundle_dir, backup_id = _allocate_bundle(backup_root, prefix, created_at)
    (bundle_dir / JOURNAL_NAME).write_bytes(source_bytes)
    copied_digest = hashlib.sha256((bundle_dir / JOURNAL_NAME).read_bytes()).hexdigest()
    if copied_digest != source_digest:
        raise RuntimeError(f"备份包写入不完整：{bundle_dir}")
    manifest: dict[str, Any] = {
        "schema_version": BACKUP_SCHEMA,
        "backup_id": backup_id,
        "created_at": created_iso,
        "action": "no_order",
        "source_journal_path": str(journal_path),
        "source_sha256": source_digest,
        "copied_sha256": copied_digest,
        "record_count": record_count,
        "head_record_sha256": head,
        "source_status": source_status,
        "source_invalid_reason": source_invalid_reason,
    }
    manifest["manifest_sha256"] = _canonical_sha256(manifest)
    _write_json_atomic(bundle_dir / MANIFEST_NAME, manifest)
    return {
        "status": "CREATED",
        "backup_id": backup_id,
        "path": str(bundle_dir),
        "created_at": created_iso,
        "record_count": record_count,
        "head_record_sha256": head,
        "source_sha256": source_digest,
        "source_status": source_status,
        "action": "no_order",
    }


def _acquire_journal_lock(journal_path: Path) -> InterProcessLock:
    lock = InterProcessLock(journal_path.with_name(journal_path.name + ".lock"))
    try:
        lock.acquire()
    except LockTimeout as error:
        raise PrivateStoreUnavailable(str(error)) from error
    return lock


def _require_backup_root(journal_directory: Path, backup_root: Path) -> Path:
    parent = journal_directory.resolve()
    candidate = backup_root.resolve()
    if candidate != parent and parent not in candidate.parents:
        raise ValueError(
            "备份目录必须位于私人账本目录内部；拒绝把私人流水备份写入 Git 仓库或同步目录"
        )
    return candidate


def _require_aware(created_at: datetime | None) -> datetime:
    if created_at is None:
        return datetime.now(timezone.utc)
    if not isinstance(created_at, datetime):
        raise ValueError("created_at 必须是 datetime")
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at 必须包含时区")
    return created_at


def _iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _allocate_bundle(backup_root: Path, prefix: str, created_at: datetime) -> tuple[Path, str]:
    stamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for _ in range(_MAX_ID_ATTEMPTS):
        backup_id = f"{prefix}{stamp}-{secrets.token_hex(4)}"
        bundle_dir = Path(backup_root) / backup_id
        try:
            bundle_dir.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            continue
        return bundle_dir, backup_id
    raise RuntimeError("无法为备份分配唯一的目录名")


def _salvage_counts(data: bytes) -> tuple[int, str | None]:
    """Best-effort line count and chain head for a source that fails validation."""
    count = 0
    head: str | None = None
    for line in data.decode("utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        count += 1
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and isinstance(record.get("record_sha256"), str):
            head = str(record["record_sha256"])
    return count, head


def _manifest_created_at(bundle_dir: Path) -> str | None:
    try:
        payload = json.loads((bundle_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    created = payload.get("created_at")
    return created if isinstance(created, str) and created else None


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(dict(payload))).hexdigest()


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    data = canonical_bytes(dict(payload))
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass


def _write_journal_atomic(path: Path, data: bytes) -> None:
    temp = path.with_name(f"{path.name}.restore-{secrets.token_hex(4)}.tmp")
    try:
        with temp.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            try:
                temp.unlink()
            except OSError:
                pass
