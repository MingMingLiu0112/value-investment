from pathlib import Path

from value_investment_agent.backup import evidence_manifest
from value_investment_agent.backup import sha256_file
from value_investment_agent.backup import snapshot_evidence
import pytest


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


def test_snapshot_retains_original_after_live_source_disappears(tmp_path: Path) -> None:
    live = tmp_path / 'live' / '600519'
    live.mkdir(parents=True)
    original = live / 'annual.pdf'
    original.write_bytes(b'official filing')
    backup_root = tmp_path / 'backup'
    backup_root.mkdir()

    records = snapshot_evidence(live.parent, backup_root)
    original.unlink()

    assert records[0]['original_path'] == '600519/annual.pdf'
    assert (backup_root / records[0]['path']).read_bytes() == b'official filing'
    assert sha256_file(backup_root / records[0]['path']) == records[0]['sha256']


def test_snapshot_rejects_missing_or_escaping_source(tmp_path: Path) -> None:
    backup_root = tmp_path / 'backup'
    backup_root.mkdir()
    with pytest.raises(RuntimeError, match='unavailable'):
        snapshot_evidence(tmp_path / 'missing', backup_root)
    live = tmp_path / 'live'
    live.mkdir()
    outside = tmp_path / 'outside.pdf'
    outside.write_bytes(b'outside')
    try:
        (live / 'linked.pdf').symlink_to(outside)
    except OSError:
        pytest.skip('Symlinks unavailable on this host')
    with pytest.raises(RuntimeError, match='escapes'):
        snapshot_evidence(live, backup_root)


def test_recovery_rejects_original_path_escape(tmp_path: Path) -> None:
    from value_investment_agent.backup import verify_recovered_originals

    evidence = tmp_path / 'object.pdf'
    evidence.write_bytes(b'original')
    with pytest.raises(RuntimeError, match='escapes'):
        verify_recovered_originals(tmp_path / 'backup.manifest.json', [{
            'path': evidence.name, 'original_path': '../outside.pdf',
            'sha256': sha256_file(evidence), 'size_bytes': evidence.stat().st_size,
        }])
    assert not (tmp_path.parent / 'outside.pdf').exists()
