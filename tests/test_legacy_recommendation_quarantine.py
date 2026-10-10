"""The legacy score report cannot be mistaken for a current product decision."""
from pathlib import Path
import subprocess
import sys


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "diagnostics"
    / "report_recommendations.py"
)


def test_legacy_report_requires_explicit_diagnostic_flag():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--legacy-diagnostic-only is required" in result.stderr
    assert "paper_entry" not in result.stdout
