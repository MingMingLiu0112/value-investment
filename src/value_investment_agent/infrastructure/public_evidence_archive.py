"""Restore hash-bound public copies without overwriting captured originals."""
import hashlib
import json
from pathlib import Path
import shutil


def restore_public_archive(repository: Path, manifest_path: Path, destination: Path) -> dict:
    repository, destination = repository.resolve(), destination.resolve()
    manifest = json.loads(manifest_path.read_bytes())
    if (manifest.get("schema_version") != "tl11-p4-public-evidence-archive-v1"
            or manifest.get("private_data") is not False or manifest.get("action") != "no_order"):
        raise ValueError("Only a public no-order archive may be restored")
    verified = []
    targets = set()
    for item in manifest["items"]:
        source = (repository / item["archive_path"]).resolve()
        target = (destination / item["original_path"]).resolve()
        if (not source.is_relative_to(repository / "artifacts")
                or not target.is_relative_to(destination / "runtime") or target in targets):
            raise ValueError("Archive path escapes permitted boundary or is duplicated")
        targets.add(target)
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Archived original hash mismatch")
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Refusing to overwrite a different restored original")
        verified.append((source, target, item))
    # Verify the entire package before copying any file.
    for source, target, item in verified:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            with target.open("xb") as output, source.open("rb") as original:
                shutil.copyfileobj(original, output)
        if hashlib.sha256(target.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("Restored original verification failed")
    return dict(action="no_order", status="PUBLIC_ARCHIVE_RESTORED_AND_VERIFIED",
                restored_files=len(verified), private_data=False,
                full_inherited_research_restored=False)
