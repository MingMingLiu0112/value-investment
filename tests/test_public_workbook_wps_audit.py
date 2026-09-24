from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/audit_public_workbook_wps_copies.ps1"


def test_public_workbook_audit_is_read_only_and_handles_unicode_git_paths():
    source = SCRIPT.read_text(encoding="utf-8")

    assert "core.quotepath=false" in source
    assert "Get-FileHash" in source
    for destructive in ("Copy-Item", "Move-Item", "Remove-Item"):
        assert destructive not in source
