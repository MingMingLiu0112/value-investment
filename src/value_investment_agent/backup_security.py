"""Offline encrypted-backup package contract for M6 readiness.

The module is deliberately independent from the live PostgreSQL backup path.
It packages local files into a streaming AES-256-GCM archive, rejects key and
staging placement that would break key separation, and verifies a decrypted
package against its source/config/release hashes. It never connects to a
database, server, cloud destination or broker.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import ctypes
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import uuid
from ctypes import wintypes
from typing import Any, BinaryIO, Iterable, Iterator, Mapping, Sequence

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


def resolve_release_inventory(
    root: Path, inventory: Sequence[str], *, workbook_path: str | None,
) -> list[Path]:
    """Resolve the canonical release input without falling back to a root copy."""
    paths = []
    for item in inventory:
        if item not in {"WORKBOOK_PATH", "A股价值投资_Agent前端智能跟踪模板.xlsx"}:
            paths.append(root / item)
            continue
        if not workbook_path or not workbook_path.strip():
            raise ValueError("CANONICAL_BACKUP_WORKBOOK_NOT_RESOLVED")
        path = Path(workbook_path).expanduser()
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if (not path.is_file()
                or path.name != "A股价值投资_Agent前端智能跟踪模板.xlsx"):
            raise ValueError("CANONICAL_BACKUP_WORKBOOK_NOT_RESOLVED")
        paths.append(path)
    return paths


@dataclass(frozen=True)
class ArchiveItem:
    kind: str
    archive_path: str
    source_path: Path
    size_bytes: int
    sha256: str


def _validate_private_project_path(path: Path) -> Path:
    project_root = Path(__file__).resolve().parents[2]
    temporary_root = project_root / ".tmp"
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = Path(os.path.abspath(candidate))
    if candidate == temporary_root or not candidate.is_relative_to(temporary_root):
        raise ValueError("decrypted backup output must stay below the project .tmp directory")
    for directory in (candidate, *candidate.parents):
        if directory == temporary_root.parent:
            break
        is_junction = getattr(directory, "is_junction", lambda: False)
        if directory.is_symlink() or is_junction():
            raise PermissionError("private backup path cannot use a link or junction")
    return candidate


def _clear_private_directory_contents(path: Path) -> None:
    for child in path.iterdir():
        is_junction = getattr(child, "is_junction", lambda: False)
        if child.is_symlink():
            child.unlink()
        elif is_junction():
            child.rmdir()
        elif child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


@contextmanager
def _private_backup_plaintext_directory(path: Path) -> Iterator[Path]:
    project_root = Path(__file__).resolve().parents[2]
    temporary_root = project_root / ".tmp"
    candidate = _validate_private_project_path(path)
    directory_handles: list[int] = []
    try:
        if os.name == "nt":
            directory_handles = _open_windows_private_path_guards(
                project_root, temporary_root, candidate
            )
        else:
            temporary_root.mkdir(mode=0o700, parents=True, exist_ok=True)
            candidate.mkdir(mode=0o700, parents=True, exist_ok=True)

        resolved = candidate.resolve()
        if not resolved.is_relative_to(temporary_root.resolve()):
            raise PermissionError(
                "private backup path must stay inside the project .tmp directory"
            )
        if any(resolved.iterdir()):
            raise PermissionError("private backup directory must be empty before ACL changes")

        if os.name == "nt":
            _protect_windows_backup_scratch(resolved)
        else:
            resolved.chmod(0o700)
            if stat.S_IMODE(resolved.stat().st_mode) != 0o700:
                raise PermissionError("private backup scratch permissions are too broad")
        if any(resolved.iterdir()):
            raise PermissionError("private backup directory must be empty before use")
        try:
            yield resolved
        except BaseException:
            try:
                _clear_private_directory_contents(resolved)
            except OSError as cleanup_error:
                raise PermissionError(
                    "could not remove partial private backup plaintext"
                ) from cleanup_error
            raise
    finally:
        for directory_handle in reversed(directory_handles):
            _close_windows_directory_guard(directory_handle)


@contextmanager
def _private_backup_scratch() -> Iterator[Path]:
    project_root = Path(__file__).resolve().parents[2]
    path = project_root / ".tmp" / "backup-restore-plaintext"
    with _private_backup_plaintext_directory(path) as scratch:
        yield scratch


def _open_windows_directory_guard(path: Path) -> int:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetFileAttributesW.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.CreateFileW(
        str(path),
        0x00000080,
        0x00000003,
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    handle_value = ctypes.cast(handle, ctypes.c_void_p).value if handle else None
    if handle_value in (None, ctypes.c_void_p(-1).value):
        raise PermissionError("could not hold private backup scratch directory")
    attributes = kernel32.GetFileAttributesW(str(path))
    if attributes == 0xFFFFFFFF or not attributes & 0x10 or attributes & 0x400:
        kernel32.CloseHandle(handle)
        raise PermissionError("private backup scratch is not a stable local directory")
    return handle_value


def _open_windows_private_path_guards(
    project_root: Path,
    temporary_root: Path,
    candidate: Path,
) -> list[int]:
    handles: list[int] = []
    try:
        for directory in (project_root.parent, project_root):
            handles.append(_open_windows_directory_guard(directory))

        temporary_root.mkdir(mode=0o700, exist_ok=True)
        handles.append(_open_windows_directory_guard(temporary_root))

        current = temporary_root
        for part in candidate.relative_to(temporary_root).parts:
            current = current / part
            current.mkdir(mode=0o700, exist_ok=True)
            handles.append(_open_windows_directory_guard(current))
        return handles
    except BaseException:
        for handle in reversed(handles):
            _close_windows_directory_guard(handle)
        raise


def _close_windows_directory_guard(handle: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    if not kernel32.CloseHandle(wintypes.HANDLE(handle)):
        raise OSError(ctypes.get_last_error(), "could not release private scratch directory")


def _protect_windows_backup_scratch(path: Path) -> None:
    candidates = [
        os.environ.get("VALUE_INVESTMENT_PWSH"),
        shutil.which("pwsh"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(str(Path(local_app_data) / "Programs/PowerShell/7/pwsh.exe"))
    candidates.append(r"C:\Program Files\PowerShell\7\pwsh.exe")
    executable = next(
        (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
        None,
    )
    if executable is None:
        raise PermissionError("PowerShell 7 is required to protect backup scratch ACLs")

    script = r"""
$ErrorActionPreference = 'Stop'
$path = [System.IO.Path]::GetFullPath($env:VALUE_INVESTMENT_BACKUP_SCRATCH)
$owner = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$administrators = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$principals = @($owner, $system, $administrators)
$allowed = @($principals | ForEach-Object { $_.Value } | Sort-Object -Unique)
$systemDirectory = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::System)
$aclCommand = Join-Path $systemDirectory 'icacls.exe'
if (-not [System.IO.File]::Exists($aclCommand)) {
    throw 'system icacls.exe was not found'
}
$resetArguments = @($path, '/reset')
& $aclCommand @resetArguments | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'icacls could not reset the private backup DACL'
}
$inheritanceArguments = @($path, '/inheritance:r')
& $aclCommand @inheritanceArguments | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'icacls could not protect the private backup DACL'
}
$grantArguments = @($path, '/grant:r')
foreach ($sid in $allowed) {
    $grantArguments += "*$($sid):(OI)(CI)F"
}
& $aclCommand @grantArguments | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'icacls could not grant the private backup principals'
}
$inheritance = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
$actual = Get-Acl -LiteralPath $path
$rules = @($actual.Access)
$actualOwner = ([System.Security.Principal.NTAccount]::new($actual.Owner)).Translate([System.Security.Principal.SecurityIdentifier]).Value
if ($actualOwner -ne $owner.Value) {
    throw 'private backup scratch owner differs from the current process user'
}
if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne $allowed.Count) {
    throw 'backup scratch DACL is not protected or has unexpected entries'
}
$seen = @()
$fullControl = [int64][System.Security.AccessControl.FileSystemRights]::FullControl
foreach ($rule in $rules) {
    $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    $rights = [int64]$rule.FileSystemRights
    if ($sid -notin $allowed -or $rule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow -or (($rights -band $fullControl) -ne $fullControl) -or (($rule.InheritanceFlags -band $inheritance) -ne $inheritance)) {
        throw 'backup scratch DACL contains an unapproved permission'
    }
    $seen += $sid
}
if (@($allowed | Where-Object { $_ -notin $seen }).Count -ne 0) {
    throw 'backup scratch DACL is missing a required principal'
}
"""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    environment = os.environ.copy()
    environment["VALUE_INVESTMENT_BACKUP_SCRATCH"] = str(path)
    try:
        result = subprocess.run(
            [executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PermissionError("private backup scratch ACL verification failed") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise PermissionError(
            "private backup scratch ACL verification failed"
            + (f": {detail[-500:]}" if detail else "")
        )


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


def _decrypt_to_temp(
    handle: BinaryIO, *, key: bytes, key_id: str, scratch_dir: Path
) -> tuple[BinaryIO, dict[str, Any]]:
    header, _ = _read_header(handle)
    if header["key_id"] != key_id:
        raise ValueError("backup key does not match encrypted package")
    decrypted = tempfile.TemporaryFile(dir=scratch_dir)
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
    except BaseException:
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
    output = _validate_private_project_path(output_dir)
    scratch_root = (
        Path(__file__).resolve().parents[2]
        / ".tmp"
        / "backup-restore-plaintext"
    )
    if output == scratch_root or output.is_relative_to(scratch_root):
        raise ValueError("decrypted output must be separate from the private scratch directory")
    with input_path.open("rb") as source_handle:
        with _private_backup_scratch() as scratch_dir:
            with _private_backup_plaintext_directory(output) as secure_output:
                decrypted, header = _decrypt_to_temp(
                    source_handle, key=key, key_id=key_id, scratch_dir=scratch_dir
                )
                with decrypted:
                    with tarfile.open(fileobj=decrypted, mode="r|*") as archive:
                        archive.extractall(secure_output, filter="data")
                manifest_path = secure_output / MANIFEST_ARCHIVE_PATH
                payload = manifest_path.read_bytes()
                manifest_sha256 = hashlib.sha256(payload).hexdigest()
                if manifest_sha256 != header["manifest_sha256"]:
                    raise ValueError("decrypted backup manifest hash does not match header")
                manifest = json.loads(payload.decode("utf-8"))
                if (
                    manifest.get("schema_version") != SCHEMA_VERSION
                    or manifest.get("action") != ACTION_NO_ORDER
                ):
                    raise ValueError("decrypted backup manifest has an invalid contract")
                verified = []
                for item in manifest.get("items") or []:
                    path = secure_output / str(item["archive_path"])
                    if not path.is_file() or path.is_symlink():
                        raise ValueError(
                            f"decrypted file is missing: {item['archive_path']}"
                        )
                    if path.stat().st_size != int(item["size_bytes"]):
                        raise ValueError(
                            f"decrypted file size differs: {item['archive_path']}"
                        )
                    actual_hash = sha256_file(path)
                    if actual_hash != item["sha256"]:
                        raise ValueError(
                            f"decrypted file hash differs: {item['archive_path']}"
                        )
                    verified.append(
                        {
                            "kind": item["kind"],
                            "archive_path": item["archive_path"],
                            "sha256": actual_hash,
                        }
                    )
                return {
                    "output_dir": str(secure_output),
                    "backup_id": manifest.get("backup_id"),
                    "manifest_sha256": manifest_sha256,
                    "key_id": key_id,
                    "verified_files": verified,
                    "action": ACTION_NO_ORDER,
                }
