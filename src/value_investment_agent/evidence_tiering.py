"""DEPRECATED_COMPATIBILITY_SHIM: forward to infrastructure evidence tiering."""

from .infrastructure.evidence.evidence_tiering import (
    build_cold_archive_manifest,
    resolve_server_evidence_path,
    sha256_file,
)

__all__ = [
    "build_cold_archive_manifest",
    "resolve_server_evidence_path",
    "sha256_file",
]
