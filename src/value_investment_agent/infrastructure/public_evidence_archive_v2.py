"""Versioned atomic archive adapter; the frozen v1 restore contract is unchanged."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import tempfile

from .public_evidence_archive import restore_public_archive

VERSION = "public-evidence-closure-archive-v2"
MARKER = ".public-evidence-restore-v2.json"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_runtime(name):
    if (not isinstance(name, str) or "\\" in name
            or PureWindowsPath(name).drive or PurePosixPath(name).is_absolute()
            or any(part in {"", ".", ".."} for part in name.split("/"))
            or not name.startswith("runtime/")):
        raise ValueError("ARCHIVE_RUNTIME_PATH_REQUIRED")
    return name


def binding(value):
    if (not isinstance(value, dict) or set(value) != {"path", "sha256"}
            or not isinstance(value["sha256"], str)
            or re.fullmatch("[0-9a-f]{64}", value["sha256"]) is None):
        raise ValueError("ARCHIVE_BINDING_INVALID")
    relative_runtime(value["path"])
    return value


def _inside(root, name):
    path = root / name
    # Reject links/junctions, including internal aliases: exact portable paths only.
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("ARCHIVE_LINK_NOT_ALLOWED")
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("ARCHIVE_PATH_ESCAPE")
    return resolved


@contextmanager
def _exclusive_lock(path):
    handle = path.open("x")
    try:
        yield
    finally:
        handle.close()
        path.unlink()


def _publish(stage, destination):
    """Same-filesystem directory publish; never merge into an existing root."""
    if destination.exists():
        raise FileExistsError("ARCHIVE_DESTINATION_ALREADY_EXISTS")
    os.rename(stage, destination)


def create_archive(*, root, bindings, bundle_binding, output_dir):
    root = Path(root).resolve()
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    output = _inside(root, output.relative_to(root).as_posix())
    if not (output.is_relative_to(root / "runtime") or output.is_relative_to(root / "artifacts")):
        raise ValueError("ARCHIVE_OUTPUT_SCOPE_INVALID")
    if output in {root / "runtime", root / "artifacts"}:
        raise ValueError("ARCHIVE_OUTPUT_DIRECTORY_REQUIRED")
    rows, contents = [], {}
    seen = set()
    for ref in bindings:
        binding(ref)
        if ref["path"] in seen:
            raise ValueError("ARCHIVE_DUPLICATE_PATH")
        seen.add(ref["path"])
        raw = _inside(root, ref["path"]).read_bytes()
        if digest(raw) != ref["sha256"]:
            raise ValueError("ARCHIVE_SOURCE_CHANGED")
        contents[ref["sha256"]] = raw
        rows.append(dict(original_path=ref["path"],
                         archive_path="artifacts/objects/" + ref["sha256"],
                         sha256=ref["sha256"]))
    if not rows or bundle_binding not in bindings:
        raise ValueError("ARCHIVE_BUNDLE_NOT_IN_CLOSURE")
    manifest = dict(schema_version=VERSION, action="no_order", private_data=False,
                    formal_eligibility=False, strict_historical_pit=False,
                    scope="EXPLICIT_PUBLIC_BUNDLE_CLOSURE_WITH_PREDECESSORS",
                    bundle=bundle_binding, items=sorted(rows, key=lambda x: x["original_path"]))
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    # Repeat is read-only; a different archive cannot be merged or replaced.
    if output.exists():
        read_archive(archive_root=output, manifest_sha256=digest(encoded))
        return dict(path=(output / "manifest.json").relative_to(root).as_posix(), sha256=digest(encoded))
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.with_name(output.name + ".archive-lock")
    with _exclusive_lock(lock):
        if output.exists():
            raise FileExistsError("ARCHIVE_DESTINATION_ALREADY_EXISTS")
        stage = Path(tempfile.mkdtemp(prefix=".public-archive-", dir=output.parent))
        try:
            objects = stage / "artifacts/objects"
            objects.mkdir(parents=True)
            for sha, raw in contents.items():
                (objects / sha).write_bytes(raw)
            (stage / "manifest.json").write_bytes(encoded)
            read_archive(archive_root=stage, manifest_sha256=digest(encoded))
            # Detect source mutation before publishing the archive.
            for ref in bindings:
                if digest(_inside(root, ref["path"]).read_bytes()) != ref["sha256"]:
                    raise ValueError("ARCHIVE_SOURCE_CHANGED")
            _publish(stage, output)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return dict(path=(output / "manifest.json").relative_to(root).as_posix(), sha256=digest(encoded))


def read_archive(*, archive_root, manifest_sha256):
    root = Path(archive_root).resolve()
    raw = _inside(root, "manifest.json").read_bytes()
    if digest(raw) != manifest_sha256:
        raise ValueError("ARCHIVE_MANIFEST_HASH_MISMATCH")
    packet = json.loads(raw)
    if (set(packet) != {"schema_version", "action", "private_data", "formal_eligibility",
                       "strict_historical_pit", "scope", "bundle", "items"}
            or packet["schema_version"] != VERSION or packet["action"] != "no_order"
            or packet["private_data"] is not False or packet["formal_eligibility"] is not False
            or packet["strict_historical_pit"] is not False
            or packet["scope"] != "EXPLICIT_PUBLIC_BUNDLE_CLOSURE_WITH_PREDECESSORS"
            or not isinstance(packet["items"], list) or not packet["items"]):
        raise ValueError("ARCHIVE_MANIFEST_INVALID")
    binding(packet["bundle"])
    seen = set()
    for row in packet["items"]:
        if not isinstance(row, dict) or set(row) != {"original_path", "archive_path", "sha256"}:
            raise ValueError("ARCHIVE_ITEM_INVALID")
        binding(dict(path=row["original_path"], sha256=row["sha256"]))
        if row["original_path"] in seen or row["archive_path"] != "artifacts/objects/" + row["sha256"]:
            raise ValueError("ARCHIVE_ITEM_DUPLICATE_OR_OBJECT_INVALID")
        seen.add(row["original_path"])
        if digest(_inside(root, row["archive_path"]).read_bytes()) != row["sha256"]:
            raise ValueError("ARCHIVE_OBJECT_HASH_MISMATCH")
    if not any(row["original_path"] == packet["bundle"]["path"]
               and row["sha256"] == packet["bundle"]["sha256"] for row in packet["items"]):
        raise ValueError("ARCHIVE_BUNDLE_NOT_IN_CLOSURE")
    return packet


def restore_archive(*, archive_root, manifest_sha256, destination, validate):
    """Publish a complete isolated root only after all bytes and semantics validate."""
    archive = Path(archive_root).resolve()
    destination = Path(destination)
    if destination.is_symlink() or (hasattr(destination, "is_junction") and destination.is_junction()):
        raise ValueError("ARCHIVE_LINK_NOT_ALLOWED")
    destination = destination.resolve()
    packet = read_archive(archive_root=archive, manifest_sha256=manifest_sha256)
    marker = dict(schema_version=VERSION, manifest_sha256=manifest_sha256, action="no_order")
    if destination.exists():
        if not (destination / MARKER).is_file() or json.loads((destination / MARKER).read_bytes()) != marker:
            raise FileExistsError("RESTORE_REQUIRES_NEW_ISOLATED_ROOT")
        for row in packet["items"]:
            if digest(_inside(destination, row["original_path"]).read_bytes()) != row["sha256"]:
                raise ValueError("RESTORED_ORIGINAL_DIFFERS")
        validate(destination, packet)
        return packet
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_name(destination.name + ".restore-lock")
    with _exclusive_lock(lock):
        if destination.exists():
            raise FileExistsError("RESTORE_REQUIRES_NEW_ISOLATED_ROOT")
        stage = Path(tempfile.mkdtemp(prefix=".public-restore-", dir=destination.parent))
        try:
            # The old restore implementation is reused unchanged inside an unpublished root.
            legacy = dict(schema_version="tl11-p4-public-evidence-archive-v1",
                          action="no_order", private_data=False, items=packet["items"])
            legacy_path = stage / "legacy-manifest.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")
            restore_public_archive(archive, legacy_path, stage)
            legacy_path.unlink()
            validate(stage, packet)
            read_archive(archive_root=archive, manifest_sha256=manifest_sha256)
            (stage / MARKER).write_text(json.dumps(marker, sort_keys=True), encoding="utf-8")
            _publish(stage, destination)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return packet
