from __future__ import annotations

from contextlib import nullcontext
import hashlib
import io
import json
import os
from pathlib import Path
import stat

import pytest

from value_investment_agent import backup_security
from value_investment_agent.backup_security import (
    ACTION_NO_ORDER,
    MANIFEST_ARCHIVE_PATH,
    decrypt_package,
    encrypt_package,
    load_policy,
    validate_key_separation,
)


def _policy_path(tmp_path: Path, *, chunk_bytes: int = 4096) -> Path:
    path = tmp_path / "backup-security.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "m6-backup-security-v1",
                "action": "no_order",
                "algorithm": "AES-256-GCM",
                "key_encoding": "hex",
                "key_min_bytes": 32,
                "chunk_bytes": chunk_bytes,
                "config_inventory": ["config.txt"],
                "release_inventory": ["release.txt"],
                "offsite": {
                    "sync_kind": "authorized_cloud_sync_required",
                    "forbidden_locations": ["backup_root", "key_file", "offsite_staging"],
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _hex_key() -> str:
    return "ab" * 32


def _package(
    tmp_path: Path,
    *,
    chunk_bytes: int = 4096,
    key_value: str | None = None,
) -> tuple[Path, Path, Path, Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "data.txt").write_text("database-archive-payload\n", encoding="utf-8")
    nested = source / "evidence"
    nested.mkdir()
    (nested / "filing.pdf").write_bytes(b"pdf-bytes")
    config = tmp_path / "config.txt"
    config.write_text("config-content", encoding="utf-8")
    release = tmp_path / "release.txt"
    release.write_text("excel-hash-and-version", encoding="utf-8")
    key = tmp_path / "backup.key"
    key.write_text(key_value or _hex_key(), encoding="ascii")
    policy = _policy_path(tmp_path, chunk_bytes=chunk_bytes)
    output = tmp_path / "backups" / "package.enc"
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    result = encrypt_package(
        source,
        output,
        key,
        policy,
        config_paths=[config],
        release_paths=[release],
        offsite_staging=offsite,
        code_version="0.1.0-test",
    )
    assert result["action"] == ACTION_NO_ORDER
    assert result["source_files"] == 2
    assert result["config_files"] == 1
    assert result["release_files"] == 1
    return source, config, release, key, policy, output


def test_policy_rejects_non_no_order_and_bad_key_encoding(tmp_path):
    policy = _policy_path(tmp_path)
    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["action"] = "BUY"
    bad = tmp_path / "bad-action.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="no_order"):
        load_policy(bad)

    payload = json.loads(policy.read_text(encoding="utf-8"))
    payload["key_encoding"] = "base64"
    bad = tmp_path / "bad-key.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="key_encoding"):
        load_policy(bad)


def test_key_separation_rejects_key_inside_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    key = source / "backup.key"
    key.write_text(_hex_key(), encoding="ascii")
    policy = load_policy(_policy_path(tmp_path))
    with pytest.raises(ValueError, match="outside the backup source"):
        validate_key_separation(
            source,
            tmp_path / "package.enc",
            key,
            offsite_staging=tmp_path / "offsite",
            policy=policy,
        )


def test_encrypt_decrypt_round_trip_and_hash_verification(tmp_path):
    source, config, release, key, policy, output = _package(tmp_path)
    restore = tmp_path / "restore"

    result = decrypt_package(output, restore, key, policy)

    assert result["action"] == ACTION_NO_ORDER
    assert result["verified_files"] and len(result["verified_files"]) == 4
    assert (restore / "source" / "data.txt").read_text(encoding="utf-8") == "database-archive-payload\n"
    assert (restore / "source" / "evidence" / "filing.pdf").read_bytes() == b"pdf-bytes"
    assert (restore / "config" / "config.txt").read_text(encoding="utf-8") == "config-content"
    assert (restore / "release" / "release.txt").read_text(encoding="utf-8") == "excel-hash-and-version"
    manifest = json.loads((restore / MANIFEST_ARCHIVE_PATH).read_text(encoding="utf-8"))
    assert manifest["code_version"] == "0.1.0-test"
    assert all(item["sha256"] for item in manifest["items"])
    assert json.dumps(manifest) != "" and "backup.key" not in json.dumps(manifest)


def test_private_backup_scratch_is_project_local_and_restrictive(monkeypatch):
    project_root = Path(backup_security.__file__).resolve().parents[2]
    guarded = []
    open_guard = backup_security._open_windows_directory_guard

    def tracked_guard(path):
        handle = open_guard(path)
        guarded.append(Path(path))
        return handle

    if os.name == "nt":
        monkeypatch.setattr(backup_security, "_open_windows_directory_guard", tracked_guard)

    with backup_security._private_backup_scratch() as scratch:
        assert scratch.is_relative_to(project_root / ".tmp")
        assert not scratch.is_symlink()
        if os.name != "nt":
            assert stat.S_IMODE(scratch.stat().st_mode) == 0o700
        else:
            assert guarded == [
                project_root.parent,
                project_root,
                project_root / ".tmp",
                scratch,
            ]


def test_decrypt_refuses_output_directory_outside_project_temp_root(tmp_path):
    _, _, _, key, policy, package = _package(tmp_path)
    project_root = Path(backup_security.__file__).resolve().parents[2]
    outside = project_root / (
        f"forbidden-restore-{tmp_path.parent.name}-{tmp_path.name}"
    )

    with pytest.raises(ValueError, match=r"project \.tmp"):
        decrypt_package(package, outside, key, policy)

    assert not outside.exists()


def test_decryption_uses_private_scratch_and_closes_on_authentication_failure(
    tmp_path, monkeypatch
):
    _, _, _, key, policy, output = _package(tmp_path)
    scratch = tmp_path / "private-scratch"
    scratch.mkdir(mode=0o700)
    monkeypatch.setattr(
        backup_security, "_private_backup_scratch", lambda: nullcontext(scratch)
    )
    real_temporary_file = backup_security.tempfile.TemporaryFile
    opened = []

    def tracked_temporary_file(*args, **kwargs):
        assert Path(kwargs["dir"]).resolve() == scratch.resolve()
        handle = real_temporary_file(*args, **kwargs)
        opened.append(handle)
        return handle

    monkeypatch.setattr(
        backup_security.tempfile, "TemporaryFile", tracked_temporary_file
    )
    tampered = tmp_path / "tampered-private-scratch.enc"
    data = bytearray(output.read_bytes())
    data[-1] ^= 1
    tampered.write_bytes(data)

    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_package(tampered, tmp_path / "restore-tampered", key, policy)

    assert len(opened) == 1
    assert opened[0].closed


def test_decrypt_clears_partial_output_when_manifest_validation_fails(
    tmp_path, monkeypatch
):
    _, _, _, key, policy, package = _package(tmp_path)
    output = tmp_path / "restore-invalid"
    manifest_payload = b"{"

    def fake_decrypt(_handle, *, key, key_id, scratch_dir):
        return io.BytesIO(b"decrypted"), {
            "manifest_sha256": hashlib.sha256(manifest_payload).hexdigest()
        }

    class PartialArchive:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extractall(self, destination, *, filter):
            partial = destination / "source" / "data.txt"
            partial.parent.mkdir(parents=True)
            partial.write_text("partial plaintext", encoding="utf-8")
            manifest = destination / MANIFEST_ARCHIVE_PATH
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(manifest_payload)

    monkeypatch.setattr(backup_security, "_decrypt_to_temp", fake_decrypt)
    monkeypatch.setattr(backup_security.tarfile, "open", lambda **_kwargs: PartialArchive())

    with pytest.raises(json.JSONDecodeError):
        decrypt_package(package, output, key, policy)

    assert output.is_dir()
    assert not any(output.iterdir())


def test_multiple_encryption_chunks_round_trip(tmp_path):
    source, config, release, key, policy, output = _package(tmp_path, chunk_bytes=1024)
    (source / "data.txt").write_bytes(b"x" * 9000)
    output.unlink()
    encrypt_package(
        source,
        output,
        key,
        policy,
        config_paths=[config],
        release_paths=[release],
        code_version="0.1.0-test",
    )
    restore = tmp_path / "restore-chunked"
    result = decrypt_package(output, restore, key, policy)
    assert len(result["verified_files"]) == 4
    assert (restore / "source" / "data.txt").read_bytes() == b"x" * 9000


def test_wrong_key_and_tampered_package_fail_closed(tmp_path):
    source, config, release, key, policy, output = _package(tmp_path)
    wrong = tmp_path / "wrong.key"
    wrong.write_text("cd" * 32, encoding="ascii")
    with pytest.raises(ValueError, match="does not match"):
        decrypt_package(output, tmp_path / "restore-wrong", wrong, policy)

    tampered = tmp_path / "tampered.enc"
    data = bytearray(output.read_bytes())
    data[-1] ^= 1
    tampered.write_bytes(data)
    with pytest.raises(ValueError, match="authentication failed"):
        decrypt_package(tampered, tmp_path / "restore-tampered", key, policy)
