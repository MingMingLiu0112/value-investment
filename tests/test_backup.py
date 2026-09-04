from pathlib import Path

from value_investment_agent.backup import evidence_manifest
from value_investment_agent.backup import sha256_file


def test_evidence_manifest_tracks_original_files_and_hashes(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "600519"
    evidence.mkdir(parents=True)
    original = evidence / "2025-12-31-annual.pdf"
    original.write_bytes(b"official filing")

    records = evidence_manifest(tmp_path / "evidence")

    assert records == [{
        "path": "evidence/600519/2025-12-31-annual.pdf",
        "size_bytes": len(b"official filing"),
        "sha256": "dbbafc02cb99a0493fc957233d7b6e4b88c2b12aa89c2828dc3b5c758cdafd37",
    }]


def test_evidence_manifest_uses_portable_relative_paths(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence" / "600519"
    evidence.mkdir(parents=True)
    original = evidence / "annual.pdf"
    original.write_bytes(b"x")

    assert evidence_manifest(tmp_path / "evidence")[0]["path"] == "evidence/600519/annual.pdf"
    assert evidence_manifest(tmp_path / "evidence")[0]["sha256"] == sha256_file(original)
