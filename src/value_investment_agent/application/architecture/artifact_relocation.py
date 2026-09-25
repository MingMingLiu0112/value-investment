"""Audit path and hash consumers before moving repository artifacts.

This module is deliberately read-only. It identifies the evidence a human or
automated cleanup needs before a root artifact can be archived; it never moves,
renames, deletes, or rewrites a file.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Iterable


ARTIFACT_RELOCATION_SCHEMA = "repository-artifact-relocation-inventory-v1"
ACTION = "no_order"
CURRENT_POINTER = Path("config/current-trial-workbook.json")
CANONICAL_WORKBOOK = (
    "\u0041\u80a1\u4ef7\u503c\u6295\u8d44_Agent"
    "\u524d\u7aef\u667a\u80fd\u8ddf\u8e2a\u6a21\u677f.xlsx"
)

_REFERENCE_ROOTS = (
    Path(".github"),
    Path("artifacts"),
    Path("config"),
    Path("deploy"),
    Path("docs"),
    Path("scripts"),
    Path("sql"),
    Path("src"),
    Path("tests"),
)
_ROOT_REFERENCE_FILES = (
    Path("AGENTS.md"),
    Path("CHANGELOG.md"),
    Path("LONG-TERM-GOAL.md"),
    Path("README.md"),
    Path(".env.example"),
)
_ROOT_ARTIFACT_GLOBS = ("*.xlsx", "*manifest.json", "*receipt.json")
_TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
_REFERENCE_SKIP_NAMES = {
    "artifact-relocation-inventory-20260925.json",
}
_MAX_REFERENCE_FILE_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ArtifactReference:
    path: str
    kind: str


@dataclass(frozen=True)
class ArtifactRecord:
    path: str
    sha256: str
    size_bytes: int
    tracked: bool
    references: tuple[ArtifactReference, ...]
    classification: str
    recommended_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "tracked": self.tracked,
            "classification": self.classification,
            "recommended_action": self.recommended_action,
            "references": [
                {"path": item.path, "kind": item.kind} for item in self.references
            ],
        }


@dataclass(frozen=True)
class ArtifactRelocationInventory:
    root: str
    artifacts: tuple[ArtifactRecord, ...]

    def as_dict(self) -> dict[str, object]:
        counts: dict[str, int] = {}
        for artifact in self.artifacts:
            counts[artifact.classification] = (
                counts.get(artifact.classification, 0) + 1
            )
        return {
            "schema_version": ARTIFACT_RELOCATION_SCHEMA,
            "action": ACTION,
            "root": self.root,
            "artifact_count": len(self.artifacts),
            "classification_counts": counts,
            "artifacts": [artifact.as_dict() for artifact in self.artifacts],
        }


def _iter_reference_files(root: Path) -> Iterable[Path]:
    seen: set[Path] = set()
    for relative in _REFERENCE_ROOTS:
        base = root / relative
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name in _REFERENCE_SKIP_NAMES:
                continue
            if path.suffix.lower() not in _TEXT_SUFFIXES:
                continue
            try:
                if path.stat().st_size > _MAX_REFERENCE_FILE_BYTES:
                    continue
            except OSError:
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path
    for relative in _ROOT_REFERENCE_FILES:
        path = root / relative
        if path.is_file() and not path.is_symlink():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path
    for pattern in _ROOT_ARTIFACT_GLOBS:
        for path in root.glob(pattern):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name in _REFERENCE_SKIP_NAMES:
                continue
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                yield path


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _reference_kind(relative: Path) -> str:
    if relative == CURRENT_POINTER:
        return "CURRENT_POINTER"
    suffix = relative.suffix.lower()
    if suffix in {".py", ".ps1", ".sh", ".yml", ".yaml", ".toml", ".sql"}:
        return "CODE_OR_CONFIG"
    if suffix == ".json":
        return "JSON_OR_RECEIPT"
    if suffix == ".md":
        return "DOCUMENTATION"
    return "OTHER_TEXT"


def _references_for(root: Path, name: str) -> tuple[ArtifactReference, ...]:
    references: list[ArtifactReference] = []
    for path in _iter_reference_files(root):
        text = _read_text(path)
        if text is None or name not in text:
            continue
        relative = path.relative_to(root)
        if relative.as_posix() == name:
            continue
        references.append(
            ArtifactReference(
                path=relative.as_posix(),
                kind=_reference_kind(relative),
            )
        )
    return tuple(sorted(references, key=lambda item: (item.kind, item.path)))


def _classify(
    name: str, references: tuple[ArtifactReference, ...]
) -> tuple[str, str]:
    if name == CANONICAL_WORKBOOK:
        return "CANONICAL_WORKBOOK", "KEEP_CANONICAL"
    if name.endswith("manifest.json") or name.endswith("receipt.json"):
        return "PROVENANCE_ARTIFACT", "KEEP_PROVENANCE"
    kinds = {item.kind for item in references}
    if "CURRENT_POINTER" in kinds:
        return "CURRENT_POINTER", "KEEP_CURRENT"
    if "JSON_OR_RECEIPT" in kinds:
        return "POSSIBLE_HASH_OR_RECEIPT_BINDING", "KEEP_UNTIL_RELOCATION_VERIFIER"
    if "CODE_OR_CONFIG" in kinds:
        return "STATIC_CONSUMER", "KEEP_UNTIL_CONSUMERS_MIGRATE"
    if "DOCUMENTATION" in kinds:
        return "HISTORICAL_REFERENCE", "ARCHIVE_AFTER_DOC_UPDATE"
    return "UNREFERENCED", "REVIEW_FOR_ARCHIVE_OR_DELETE"


def build_artifact_relocation_inventory(
    root: Path,
    *,
    tracked_paths: Iterable[str] = (),
) -> ArtifactRelocationInventory:
    root = root.resolve()
    tracked = {str(path).replace("\\", "/") for path in tracked_paths}
    records: list[ArtifactRecord] = []
    artifact_paths: dict[str, Path] = {}
    for pattern in _ROOT_ARTIFACT_GLOBS:
        for path in root.glob(pattern):
            if path.is_file() and not path.is_symlink():
                artifact_paths[path.name] = path
    for name, path in sorted(artifact_paths.items()):
        references = _references_for(root, path.name)
        classification, action = _classify(name, references)
        records.append(
            ArtifactRecord(
                path=path.name,
                sha256=sha256(path.read_bytes()).hexdigest(),
                size_bytes=path.stat().st_size,
                tracked=path.name in tracked,
                references=references,
                classification=classification,
                recommended_action=action,
            )
        )
    return ArtifactRelocationInventory(root=".", artifacts=tuple(records))
