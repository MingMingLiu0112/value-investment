from __future__ import annotations

from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "current" / "build_simulated_product_user_trial.py"


def test_simulated_product_preview_requires_explicit_acknowledgement(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(tmp_path / "preview.xlsx")],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "--simulated-user-trial" in (completed.stderr + completed.stdout)
    assert not (tmp_path / "preview.xlsx").exists()


def test_simulated_product_preview_refuses_output_outside_runtime() -> None:
    output = ROOT.parent / "simulated-product-preview-outside-runtime.xlsx"
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--simulated-user-trial",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "must remain under runtime" in (completed.stderr + completed.stdout)
    assert not output.exists()
