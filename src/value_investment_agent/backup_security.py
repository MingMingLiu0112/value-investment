"""Offline encrypted-backup package contract for M6 readiness.

The module is deliberately independent from the live PostgreSQL backup path.
It packages local files into a streaming AES-256-GCM archive, rejects key and
staging placement that would break key separation, and verifies a decrypted
package against its source/config/release hashes. It never connects to a
database, server, cloud destination or broker.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile
import uuid
from typing import Any, BinaryIO, Iterable, Mapping, Sequence

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


SCHEMA_VERSION = "m6-backup-security-v1"
ACTION_NO_ORDER = "no_order"
ALGORITHM = "AES-256-GCM"
FORMAT_MAGIC = b"VIABK01\n"
MANIFEST_ARCHIVE_PATH = "manifest/backup-manifest.json"
KEY_ID_CONTEXT = b"value-investment-agent-backup-key-id-v1"
MIN_CHUNK_BYTES = 1024
MAX_CHUNK_BYTES = 1024**3
_HEX_KEY = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class OffsiteContract:
    sync_kind: str
    forbidden_locations: tuple[str, ...]


@dataclass(frozen=True)
class BackupSecurityPolicy:
    schema_version: str
    action: str
    algorithm: str
    key_encoding: str
    key_min_bytes: int
    chunk_bytes: int
    config_inventory: tuple[str, ...]
    release_inventory: tuple[str, ...]
    offsite: OffsiteContract


@dataclass(frozen=True)
class ArchiveItem:
    kind: str
    archive_path: str
    source_path: Path
    size_bytes: int
    sha256: str


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"backup security policy must be an object: {path}")
    return payload


def load_policy(path: Path) -> BackupSecurityPolicy:
    payload = _load_json_object(path)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported backup security policy schema")
    if payload.get("action") != ACTION_NO_ORDER:
        raise ValueError("backup security policy must be no_order")
    if payload.get("algorithm") != ALGORITHM:
        raise ValueError(f"unsupported encryption algorithm: {payload.get( algorithm)}")
    key_encoding = str(payload.get("key_encoding") or "")
    if key_encoding not in {"raw", "hex"}:
        raise ValueError("key_encoding must be raw or hex")
    key_min_bytes = int(payload.get("key_min_bytes") or 0)
    if key_min_bytes != 32:
        raise ValueError("AES-256 requires a 32-byte key")
    chunk_bytes = int(payload.get("chunk_bytes") or 0)
    if not MIN_CHUNK_BYTES <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError("chunk_bytes is outside the supported range")
    config_inventory = payload.get("config_inventory") or []
    release_inventory = payload.get("release_inventory") or []
    if not isinstance(config_inventory, list) or not config_inventory:
        raise ValueError("config_inventory must be a non-empty list")
    if not isinstance(release_inventory, list):
        raise ValueError("release_inventory must be a list")
    offsite_payload = payload.get("offsite") or {}
    if not isinstance(offsite_payload, dict):
        raise ValueError("offsite must be an object")
    sync_kind = str(offsite_payload.get("sync_kind") or "")
    forbidden = offsite_payload.get("forbidden_locations") or []
    if not sync_kind or not isinstance(forbidden, list) or not forbidden:
        raise ValueError("offsite sync_kind and forbidden_locations are required")
    allowed_forbidden = {"backup_root", "key_file", "offsite_staging"}
    if set(forbidden) - allowed_forbidden:
        raise ValueError("offsite forbidden_locations contains an unknown scope")
    return BackupSecurityPolicy(
        schema_version=SCHEMA_VERSION,
        action=ACTION_NO_ORDER,
        algorithm=ALGORITHM,
        key_encoding=key_encoding,
        key_min_bytes=key_min_bytes,
        chunk_bytes=chunk_bytes,
        config_inventory=tuple(str(item) for item in config_inventory),
        release_inventory=tuple(str(item) for item in release_inventory),
        offsite=OffsiteContract(sync_kind=sync_kind, forbidden_locations=tuple(forbidden)),
    )


def sha256_file(path: Path, chunk_bytes: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_bytes), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_key(path: Path, policy: BackupSecurityPolicy) -> tuple[bytes, str]:
    key_path = path.resolve()
    if not key_path.is_file() or key_path.is_symlink():
        raise ValueError("backup key path must be a regular file")
    material = key_path.read_bytes().rstrip(b"\r\n\t ")
    if policy.key_encoding == "hex":
        if not _HEX_KEY.fullmatch(material.decode("ascii")):
            raise ValueError("hex key must contain exactly 64 lowercase hex characters")
        key = bytes.fromhex(material.decode("ascii"))
    else:
        if len(material) != policy.key_min_bytes:
            raise ValueError("raw key must contain exactly 32 bytes")
        key = material
    key_id = hmac.new(key, KEY_ID_CONTEXT, hashlib.sha256).hexdigest()[:16]
    return key, key_id


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_key_separation(
    source_path: Path,
    output_path: Path,
    key_path: Path,
    *,
    offsite_staging: Path | None = None,
    policy: BackupSecurityPolicy,
) -> dict[str, str]:
    source = source_path.resolve()
    output = output_path.resolve()
    key = key_path.resolve()
    if not source.exists():
        raise ValueError("backup source does not exist")
    if source.is_symlink() or key.is_symlink():
        raise ValueError("backup source and key must not be symbolic links")
    if source.is_dir() and _is_within(output, source):
        raise ValueError("encrypted output must be outside the source directory")
    if _is_within(key, source if source.is_dir() else source.parent):
        raise ValueError("backup key must be outside the backup source")
    if _is_within(key, output.parent):
        raise ValueError("backup key must not live in the encrypted output directory")
    if offsite_staging is not None:
        staging = offsite_staging.resolve()
        if _is_within(key, staging):
            raise ValueError("backup key must be outside the offsite staging directory")
        if source == staging or _is_within(source, staging) or _is_within(staging, source if source.is_dir() else source.parent):
            raise ValueError("backup source and offsite staging must be separate locations")
    return {
        "source": str(source),
        "output": str(output),
        "key": str(key),
        "offsite_staging": str(offsite_staging.resolve()) if offsite_staging else "",
    }


def _collect_source_items(source: Path) -> list[ArchiveItem]:
    resolved = source.resolve()
    if resolved.is_file():
        paths = [resolved]
        relative = resolved.name
    elif resolved.is_dir():
        paths = [
            path.resolve()
            for path in sorted(resolved.rglob("*"))
            if path.is_file() and not path.is_symlink()
        ]
        relative = lambda path: path.resolve().relative_to(resolved).as_posix()
    else:
        raise ValueError("backup source must be a file or directory")
    items = []
    seen: set[str] = set()
    for path in paths:
        if path.is_symlink():
            raise ValueError(f"symbolic links are not packaged: {path}")
        archive_path = f"source/{relative(path) if callable(relative) else relative}"
        if archive_path in seen:
            raise ValueError(f"duplicate backup archive path: {archive_path}")
        seen.add(archive_path)
        items.append(
            ArchiveItem(
                kind="source",
                archive_path=archive_path,
                source_path=path,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return items


def _collect_named_items(
    paths: Iterable[Path],
    *,
    kind: str,
    prefix: str,
) -> list[ArchiveItem]:
    items = []
    seen: set[str] = set()
    for raw_path in paths:
        path = raw_path.resolve()
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"{kind} inventory path is not a regular file: {raw_path}")
        archive_path = f"{prefix}/{path.name}"
        if archive_path in seen:
            raise ValueError(f"duplicate {kind} archive path: {archive_path}")
        seen.add(archive_path)
        items.append(
            ArchiveItem(
                kind=kind,
                archive_path=archive_path,
                source_path=path,
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return items


def _manifest_payload(
    items: Sequence[ArchiveItem],
    *,
    backup_id: str,
    created_at: str,
    code_version: str,
) -> tuple[dict[str, Any], bytes]:
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "backup_id": backup_id,
        "created_at": created_at,
        "code_version": code_version,
        "action": ACTION_NO_ORDER,
        "items": [
            {
                "kind": item.kind,
                "archive_path": item.archive_path,
                "size_bytes": item.size_bytes,
                "sha256": item.sha256,
            }
            for item in items
        ],
    }
    payload = json.dumps(manifest, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return manifest, payload


def _write_header(
    handle: BinaryIO,
    *,
    manifest_sha256: str,
    key_id: str,
    chunk_bytes: int,
    created_at: str,
) -> None:
    header = {
        "schema_version": SCHEMA_VERSION,
        "algorithm": ALGORITHM,
        "chunk_bytes": chunk_bytes,
        "manifest_sha256": manifest_sha256,
        "key_id": key_id,
        "created_at": created_at,
    }
    encoded = json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 65535:
        raise ValueError("encrypted backup header is too large")
    handle.write(FORMAT_MAGIC)
    handle.write(len(encoded).to_bytes(4, "big"))
    handle.write(encoded)


class _EncryptingWriter:
    def __init__(
        self,
        handle: BinaryIO,
        *,
        key: bytes,
        key_id: str,
        chunk_bytes: int,
        manifest_sha256: str,
        created_at: str,
    ) -> None:
        self._handle = handle
        self._key = key
        self._chunk_bytes = chunk_bytes
        self._buffer = bytearray()
        self._closed = False
        _write_header(
            handle,
            manifest_sha256=manifest_sha256,
            key_id=key_id,
            chunk_bytes=chunk_bytes,
            created_at=created_at,
        )

    def _emit(self, payload: bytes) -> None:
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, payload, None)
        self._handle.write(len(payload).to_bytes(4, "big"))
        self._handle.write(nonce)
        self._handle.write(ciphertext)

    def write(self, data: bytes) -> int:
        if self._closed:
            raise ValueError("write to closed encrypted backup")
        if data:
            self._buffer.extend(data)
            while len(self._buffer) >= self._chunk_bytes:
                self._emit(bytes(self._buffer[: self._chunk_bytes]))
                del self._buffer[: self._chunk_bytes]
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            self._emit(bytes(self._buffer))
            self._buffer.clear()

    def close(self) -> None:
        if not self._closed:
            self.flush()
            self._closed = True
            self._handle.close()


def encrypt_package(
    source_path: Path,
    output_path: Path,
    key_path: Path,
    policy_path: Path,
    *,
    config_paths: Sequence[Path] = (),
    release_paths: Sequence[Path] = (),
    offsite_staging: Path | None = None,
    code_version: str = "unknown",
    backup_id: str | None = None,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    key, key_id = load_key(key_path, policy)
    locations = validate_key_separation(
        source_path,
        output_path,
        key_path,
        offsite_staging=offsite_staging,
        policy=policy,
    )
    output = output_path.resolve()
    if output.exists():
        raise FileExistsError(f"encrypted output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    source_items = _collect_source_items(source_path)
    config_items = _collect_named_items(config_paths, kind="config", prefix="config")
    release_items = _collect_named_items(release_paths, kind="release", prefix="release")
    items = source_items + config_items + release_items
    created_at = datetime.now(timezone.utc).isoformat()
    selected_backup_id = backup_id or str(uuid.uuid4())
    manifest, payload = _manifest_payload(
        items,
        backup_id=selected_backup_id,
        created_at=created_at,
        code_version=code_version,
    )
    manifest_sha256 = hashlib.sha256(payload).hexdigest()
    writer = _EncryptingWriter(
        output.open("wb"),
        key=key,
        key_id=key_id,
        chunk_bytes=policy.chunk_bytes,
        manifest_sha256=manifest_sha256,
        created_at=created_at,
    )
    try:
        with tarfile.open(fileobj=writer, mode="w|", format=tarfile.PAX_FORMAT) as archive:
            manifest_info = tarfile.TarInfo(MANIFEST_ARCHIVE_PATH)
            manifest_info.size = len(payload)
            manifest_info.mtime = int(datetime.fromisoformat(created_at).timestamp())
            archive.addfile(manifest_info, io.BytesIO(payload))
            for item in items:
                archive.add(item.source_path, arcname=item.archive_path, recursive=False)
        writer.close()
    except Exception:
        writer.close()
        try:
            output.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "output": str(output),
        "sha256": sha256_file(output),
        "manifest_sha256": manifest_sha256,
        "key_id": key_id,
        "backup_id": selected_backup_id,
        "item_count": len(items),
        "source_files": len(source_items),
        "config_files": len(config_items),
        "release_files": len(release_items),
        "locations": locations,
        "action": ACTION_NO_ORDER,
    }


def _read_header(handle: BinaryIO) -> tuple[dict[str, Any], int]:
    magic = handle.read(len(FORMAT_MAGIC))
    if magic != FORMAT_MAGIC:
        raise ValueError("not a value-investment encrypted backup")
    raw_length = handle.read(4)
    if len(raw_length) != 4:
        raise ValueError("truncated encrypted backup header")
    header_length = int.from_bytes(raw_length, "big")
    encoded = handle.read(header_length)
    if len(encoded) != header_length:
        raise ValueError("truncated encrypted backup header")
    header = json.loads(encoded.decode("utf-8"))
    if header.get("schema_version") != SCHEMA_VERSION or header.get("algorithm") != ALGORITHM:
        raise ValueError("unsupported encrypted backup header")
    chunk_bytes = int(header.get("chunk_bytes") or 0)
    if not MIN_CHUNK_BYTES <= chunk_bytes <= MAX_CHUNK_BYTES:
        raise ValueError("invalid encrypted backup chunk size")
    if not re.fullmatch(r"[0-9a-f]{64}", str(header.get("manifest_sha256") or "")):
        raise ValueError("invalid encrypted backup manifest hash")
    return header, chunk_bytes


def _decrypt_to_temp(handle: BinaryIO, *, key: bytes, key_id: str) -> tuple[BinaryIO, dict[str, Any]]:
    header, _ = _read_header(handle)
    if header["key_id"] != key_id:
        raise ValueError("backup key does not match encrypted package")
    decrypted = tempfile.TemporaryFile()
    try:
        while True:
            raw_length = handle.read(4)
            if not raw_length:
                break
            if len(raw_length) != 4:
                raise ValueError("truncated encrypted backup chunk length")
            chunk_length = int.from_bytes(raw_length, "big")
            nonce = handle.read(12)
            ciphertext = handle.read(chunk_length + 16)
            if len(nonce) != 12 or len(ciphertext) != chunk_length + 16:
                raise ValueError("truncated encrypted backup chunk")
            try:
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
            except Exception as exc:
                raise ValueError("encrypted backup authentication failed") from exc
            decrypted.write(plaintext)
        decrypted.flush()
        decrypted.seek(0)
        return decrypted, header
    except Exception:
        decrypted.close()
        raise


def decrypt_package(
    input_path: Path,
    output_dir: Path,
    key_path: Path,
    policy_path: Path,
) -> dict[str, Any]:
    policy = load_policy(policy_path)
    key, key_id = load_key(key_path, policy)
    output = output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"decrypt output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with input_path.open("rb") as source_handle:
        decrypted, header = _decrypt_to_temp(source_handle, key=key, key_id=key_id)
        with decrypted:
            with tarfile.open(fileobj=decrypted, mode="r|*") as archive:
                archive.extractall(output, filter="data")
    manifest_path = output / MANIFEST_ARCHIVE_PATH
    payload = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(payload).hexdigest()
    if manifest_sha256 != header["manifest_sha256"]:
        raise ValueError("decrypted backup manifest hash does not match header")
    manifest = json.loads(payload.decode("utf-8"))
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("action") != ACTION_NO_ORDER:
        raise ValueError("decrypted backup manifest has an invalid contract")
    verified = []
    for item in manifest.get("items") or []:
        path = output / str(item["archive_path"])
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"decrypted file is missing: {item[archive_path]}")
        if path.stat().st_size != int(item["size_bytes"]):
            raise ValueError(f"decrypted file size differs: {item[archive_path]}")
        actual_hash = sha256_file(path)
        if actual_hash != item["sha256"]:
            raise ValueError(f"decrypted file hash differs: {item[archive_path]}")
        verified.append(
            {
                "kind": item["kind"],
                "archive_path": item["archive_path"],
                "sha256": actual_hash,
            }
        )
    return {
        "output_dir": str(output),
        "backup_id": manifest.get("backup_id"),
        "manifest_sha256": manifest_sha256,
        "key_id": key_id,
        "verified_files": verified,
        "action": ACTION_NO_ORDER,
    }
