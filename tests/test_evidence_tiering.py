from datetime import datetime, timezone, date
from hashlib import sha256
from pathlib import Path

import pytest

from value_investment_agent.evidence_tiering import build_cold_archive_manifest, resolve_server_evidence_path


def row(path: Path, *, symbol="000001", status="extracted", fetched="2026-01-01"):
    return {"disclosure_id": "00000000-0000-0000-0000-000000000001", "symbol": symbol,
            "report_period": "2025-12-31", "report_kind": "annual", "published_at": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "fetched_at": datetime.fromisoformat(fetched + "T00:00:00+00:00"),
            "sha256": sha256(path.read_bytes()).hexdigest(), "local_path": str(path),
            "extraction_status": status}


def test_manifest_is_copy_only_and_excludes_retained_or_unfinished_files(tmp_path):
    old = tmp_path / "000001" / "old.pdf"
    old.parent.mkdir()
    old.write_bytes(b"old")
    kept = tmp_path / "600519" / "keep.pdf"
    kept.parent.mkdir()
    kept.write_bytes(b"keep")
    unfinished = tmp_path / "000002" / "pending.pdf"
    unfinished.parent.mkdir()
    unfinished.write_bytes(b"pending")
    result = build_cold_archive_manifest(
        [row(old), row(kept, symbol="600519"), row(unfinished, symbol="000002", status="pending")],
        evidence_root=tmp_path, retain_symbols={"600519"}, before=date(2026, 6, 1))
    assert result["mode"] == "copy_and_verify_only"
    assert result["deletion_permitted"] is False
    assert result["candidate_count"] == 1
    assert result["candidates"][0]["relative_path"] == "000001/old.pdf"
    assert {entry["reason"] for entry in result["excluded"]} == {"retained_symbol", "extraction_not_complete"}


def test_manifest_rejects_missing_or_changed_source(tmp_path):
    path = tmp_path / "000001" / "old.pdf"
    path.parent.mkdir()
    path.write_bytes(b"old")
    item = row(path)
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256"):
        build_cold_archive_manifest([item], evidence_root=tmp_path, retain_symbols=set(), before=date(2026, 6, 1))


def test_manifest_excludes_non_pdf_disclosures(tmp_path):
    path = tmp_path / "000001" / "notice.html"
    path.parent.mkdir()
    path.write_bytes(b"notice")
    result = build_cold_archive_manifest([row(path)], evidence_root=tmp_path,
                                         retain_symbols=set(), before=date(2026, 6, 1))
    assert result["candidates"] == []
    assert result["excluded"][0]["reason"] == "not_a_pdf"


def test_manifest_excludes_pdf_outside_server_evidence_root(tmp_path):
    root = tmp_path / "evidence"
    root.mkdir()
    path = tmp_path / "other" / "outside.pdf"
    path.parent.mkdir()
    path.write_bytes(b"outside")
    result = build_cold_archive_manifest([row(path)], evidence_root=root,
                                         retain_symbols=set(), before=date(2026, 6, 1))
    assert result["candidates"] == []
    assert result["excluded"][0]["reason"] == "not_server_resident"


def test_known_container_evidence_path_is_rebased_and_hash_checked(tmp_path):
    root = tmp_path / "evidence"
    path = root / "000001" / "old.pdf"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"old")
    item = row(path)
    item["local_path"] = "/app/evidence/000001/old.pdf"
    assert resolve_server_evidence_path(item["local_path"], root) == path
    result = build_cold_archive_manifest([item], evidence_root=root,
                                         retain_symbols=set(), before=date(2026, 6, 1))
    assert result["candidate_count"] == 1
