"""Build fail-closed server-to-cold-archive evidence manifests."""
from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path, PurePosixPath


ARCHIVABLE_EXTRACTION_STATUSES = {"extracted", "no_candidates"}
LEGACY_EVIDENCE_ROOT = PurePosixPath("/app/evidence")


def sha256_file(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def resolve_server_evidence_path(recorded_path: str, evidence_root: Path) -> Path | None:
    """Resolve only the known historic container mount to the server root."""
    root = evidence_root.resolve()
    path = Path(recorded_path).resolve()
    if path.is_relative_to(root):
        return path
    portable = PurePosixPath(recorded_path.replace("\\", "/"))
    if portable.is_relative_to(LEGACY_EVIDENCE_ROOT):
        return root.joinpath(*portable.relative_to(LEGACY_EVIDENCE_ROOT).parts)
    return None


def build_cold_archive_manifest(rows: list[dict], *, evidence_root: Path,
                                retain_symbols: set[str], before: date) -> dict:
    """Return only server-resident, hash-verified PDF candidates.

    The manifest is intentionally advisory: creating it never mutates a database
    and never removes a source file. Any incomplete queue state or path outside
    the evidence root is rejected rather than archived.
    """
    root = evidence_root.resolve()
    candidates = []
    excluded = []
    seen_hashes: set[str] = set()
    for row in rows:
        symbol = str(row["symbol"])
        status = str(row["extraction_status"])
        fetched_at = row["fetched_at"]
        recorded_path = str(row["local_path"])
        path = resolve_server_evidence_path(recorded_path, root)
        if symbol in retain_symbols:
            excluded.append({"sha256": row["sha256"], "reason": "retained_symbol"})
            continue
        if status not in ARCHIVABLE_EXTRACTION_STATUSES:
            excluded.append({"sha256": row["sha256"], "reason": "extraction_not_complete"})
            continue
        if fetched_at.date() >= before:
            excluded.append({"sha256": row["sha256"], "reason": "within_server_retention"})
            continue
        if Path(recorded_path).suffix.lower() != ".pdf":
            excluded.append({"sha256": row["sha256"], "reason": "not_a_pdf"})
            continue
        if path is None:
            excluded.append({"sha256": row["sha256"], "reason": "not_server_resident",
                             "recorded_path": recorded_path})
            continue
        expected = str(row["sha256"])
        if expected in seen_hashes:
            raise ValueError("Duplicate PDF hash in archive candidate query")
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError("Archive candidate is missing or its SHA-256 changed")
        seen_hashes.add(expected)
        candidates.append({
            "disclosure_id": str(row["disclosure_id"]), "symbol": symbol,
            "report_period": str(row["report_period"]), "report_kind": str(row["report_kind"]),
            "published_at": row["published_at"].isoformat(), "fetched_at": fetched_at.isoformat(),
            "sha256": expected, "bytes": path.stat().st_size,
            "server_path": str(path), "relative_path": path.relative_to(root).as_posix(),
        })
    return {
        "manifest_version": "cold-archive-plan-v1",
        "mode": "copy_and_verify_only",
        "evidence_root": str(root), "retained_symbols": sorted(retain_symbols),
        "before": before.isoformat(), "candidates": candidates, "excluded": excluded,
        "candidate_count": len(candidates), "candidate_bytes": sum(row["bytes"] for row in candidates),
        "deletion_permitted": False,
    }
