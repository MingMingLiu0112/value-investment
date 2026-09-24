"""Encrypted, fail-closed private portfolio intake for M4.

This boundary is deliberately small: it accepts a human-confirmed actual
portfolio bundle from a private location, decrypts it in memory, and returns
the existing domain contract.  It neither connects to a broker nor writes a
decision, position target, or order.  Public repository paths and configured
sync roots are rejected so personal portfolio data cannot silently enter Git
or the shared WPS workspace.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from .investment_decision import ACTION_NO_ORDER
from .portfolio_contracts import (
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    PortfolioInputBundle,
    portfolio_input_bundle_from_payload,
)


SCHEMA_VERSION = "m4-private-portfolio-intake-v1"
ALGORITHM = "AES-256-GCM"
KEY_ID_CONTEXT = b"value-investment-agent-private-portfolio-key-id-v1"
_HEX_KEY = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_SYNC_DIRECTORY_NAMES = frozenset({"wpsdrive"})


@dataclass(frozen=True)
class PrivatePortfolioIntakeReceipt:
    """Non-sensitive audit metadata; it intentionally excludes portfolio values."""

    schema_version: str
    action: str
    encrypted_sha256: str
    key_id: str
    created_at: str
    guidance_input_status: str

    def as_policy(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "action": self.action,
            "encrypted_sha256": self.encrypted_sha256,
            "key_id": self.key_id,
            "created_at": self.created_at,
            "guidance_input_status": self.guidance_input_status,
        }


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _containing_git_root(path: Path) -> Path | None:
    """Return the nearest Git worktree marker without invoking Git.

    Private inputs must remain outside every local worktree, not merely outside
    this project's currently checked-out root.  A ``.git`` file is also valid
    for linked worktrees, so both supported Git marker forms are rejected.
    """

    for candidate in (path, *path.parents):
        marker = candidate / ".git"
        if marker.is_dir() or marker.is_file():
            return candidate
    return None


def _has_builtin_sync_directory(path: Path) -> bool:
    return any(part.casefold() in _FORBIDDEN_SYNC_DIRECTORY_NAMES for part in path.parts)


def _require_private_paths(
    *,
    private_root: Path,
    repository_root: Path,
    encrypted_path: Path,
    key_path: Path,
    forbidden_sync_roots: Iterable[Path] = (),
) -> tuple[Path, Path, Path, tuple[Path, ...]]:
    root = private_root.resolve()
    repository = repository_root.resolve()
    encrypted = encrypted_path.resolve()
    key = key_path.resolve()
    forbidden = tuple(path.resolve() for path in forbidden_sync_roots)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("private_root must be an existing non-symbolic-link directory")
    if _is_within(root, repository) or _is_within(repository, root):
        raise ValueError("private_root must be separate from the repository")
    if _containing_git_root(root) is not None:
        raise ValueError("private_root must be separate from every git repository")
    if _is_within(key, repository):
        raise ValueError("private portfolio key must be outside the repository")
    if any(_has_builtin_sync_directory(path) for path in (root, encrypted, key)):
        raise ValueError("private portfolio paths must not use WPSDrive")
    if not _is_within(encrypted, root):
        raise ValueError("encrypted portfolio input must live under private_root")
    if _is_within(key, root):
        raise ValueError("private portfolio key must be outside private_root")
    for sync_root in forbidden:
        if _is_within(root, sync_root) or _is_within(encrypted, sync_root):
            raise ValueError("private portfolio input must not live in a configured sync root")
        if _is_within(key, sync_root):
            raise ValueError("private portfolio key must not live in a configured sync root")
    return root, encrypted, key, forbidden


def _load_key(path: Path) -> tuple[bytes, str]:
    if not path.is_file() or path.is_symlink():
        raise ValueError("private portfolio key must be a regular non-symbolic-link file")
    material = path.read_bytes().rstrip(b"\r\n\t ")
    try:
        encoded = material.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("private portfolio key must be 64 lowercase hex characters") from error
    if not _HEX_KEY.fullmatch(encoded):
        raise ValueError("private portfolio key must be 64 lowercase hex characters")
    key = bytes.fromhex(encoded)
    key_id = hmac.new(key, KEY_ID_CONTEXT, hashlib.sha256).hexdigest()[:16]
    return key, key_id


def _canonical_header(*, key_id: str, created_at: str) -> bytes:
    header = {
        "action": ACTION_NO_ORDER,
        "algorithm": ALGORITHM,
        "created_at": created_at,
        "key_id": key_id,
        "schema_version": SCHEMA_VERSION,
    }
    return json.dumps(header, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _receipt(encrypted_path: Path, *, key_id: str, created_at: str) -> PrivatePortfolioIntakeReceipt:
    digest = hashlib.sha256(encrypted_path.read_bytes()).hexdigest()
    return PrivatePortfolioIntakeReceipt(
        schema_version=SCHEMA_VERSION,
        action=ACTION_NO_ORDER,
        encrypted_sha256=digest,
        key_id=key_id,
        created_at=created_at,
        guidance_input_status="PRIVATE_ACTUAL_HUMAN_CONFIRMED",
    )


def _validate_actual_bundle(bundle: PortfolioInputBundle) -> None:
    if bundle.action != ACTION_NO_ORDER:
        raise ValueError("private portfolio input must remain no_order")
    if bundle.policy.confirmation_status != CONFIRMATION_HUMAN:
        raise ValueError("private portfolio input requires human-confirmed policy")
    if bundle.snapshot.namespace != NAMESPACE_ACTUAL:
        raise ValueError("private portfolio input requires ACTUAL snapshot namespace")
    missing = bundle.missing_guidance_inputs()
    if missing:
        raise ValueError(f"private portfolio input cannot support guidance: {', '.join(missing)}")


def encrypt_private_portfolio_bundle(
    bundle: PortfolioInputBundle,
    encrypted_path: Path,
    key_path: Path,
    *,
    private_root: Path,
    repository_root: Path,
    forbidden_sync_roots: Iterable[Path] = (),
    created_at: datetime | None = None,
) -> PrivatePortfolioIntakeReceipt:
    """Write one new encrypted bundle; existing files are never overwritten."""
    _validate_actual_bundle(bundle)
    _, encrypted, key_path, _ = _require_private_paths(
        private_root=private_root,
        repository_root=repository_root,
        encrypted_path=encrypted_path,
        key_path=key_path,
        forbidden_sync_roots=forbidden_sync_roots,
    )
    if encrypted.exists():
        raise FileExistsError(f"encrypted private portfolio input already exists: {encrypted}")
    key, key_id = _load_key(key_path)
    timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    header = _canonical_header(key_id=key_id, created_at=timestamp)
    plaintext = json.dumps(bundle.as_policy(), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, header)
    envelope = {
        "header": json.loads(header),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }
    encrypted.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=encrypted.parent,
        prefix=f".{encrypted.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        json.dump(envelope, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    try:
        os.replace(temporary, encrypted)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return _receipt(encrypted, key_id=key_id, created_at=timestamp)


def encrypt_private_portfolio_payload(
    payload: Mapping[str, Any],
    encrypted_path: Path,
    key_path: Path,
    *,
    private_root: Path,
    repository_root: Path,
    forbidden_sync_roots: Iterable[Path] = (),
    created_at: datetime | None = None,
) -> PrivatePortfolioIntakeReceipt:
    """Validate a private JSON payload before encrypting it as one new bundle."""
    if not isinstance(payload, Mapping):
        raise ValueError("private portfolio payload must be an object")
    return encrypt_private_portfolio_bundle(
        portfolio_input_bundle_from_payload(payload),
        encrypted_path,
        key_path,
        private_root=private_root,
        repository_root=repository_root,
        forbidden_sync_roots=forbidden_sync_roots,
        created_at=created_at,
    )


def load_private_portfolio_bundle(
    encrypted_path: Path,
    key_path: Path,
    *,
    private_root: Path,
    repository_root: Path,
    forbidden_sync_roots: Iterable[Path] = (),
) -> tuple[PortfolioInputBundle, PrivatePortfolioIntakeReceipt]:
    """Decrypt and validate a private actual bundle without persisting its contents."""
    _, encrypted, key_path, _ = _require_private_paths(
        private_root=private_root,
        repository_root=repository_root,
        encrypted_path=encrypted_path,
        key_path=key_path,
        forbidden_sync_roots=forbidden_sync_roots,
    )
    if not encrypted.is_file() or encrypted.is_symlink():
        raise ValueError("encrypted private portfolio input must be a regular file")
    key, key_id = _load_key(key_path)
    try:
        envelope = json.loads(encrypted.read_text(encoding="utf-8"))
        header = envelope["header"]
        if not isinstance(header, Mapping):
            raise ValueError("encrypted private portfolio header must be an object")
        created_at = str(header["created_at"])
        authenticated_header = _canonical_header(key_id=str(header["key_id"]), created_at=created_at)
        if header != json.loads(authenticated_header):
            raise ValueError("encrypted private portfolio header has an invalid contract")
        if header["key_id"] != key_id:
            raise ValueError("private portfolio key does not match encrypted input")
        plaintext = AESGCM(key).decrypt(
            base64.b64decode(envelope["nonce"], validate=True),
            base64.b64decode(envelope["ciphertext"], validate=True),
            authenticated_header,
        )
        payload = json.loads(plaintext.decode("utf-8"))
    except (
        InvalidTag,
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("encrypted private portfolio input is invalid or authentication failed") from error
    if not isinstance(payload, Mapping):
        raise ValueError("encrypted private portfolio payload must be an object")
    bundle = portfolio_input_bundle_from_payload(payload)
    _validate_actual_bundle(bundle)
    return bundle, _receipt(encrypted, key_id=key_id, created_at=created_at)
