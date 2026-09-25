from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_current_trial_pointer_verifies_one_no_order_workbook():
    pointer = json.loads((ROOT / "config/current-trial-workbook.json").read_text(encoding="utf-8"))
    if not (ROOT / pointer["workbook"]).is_file():
        pytest.skip("Current trial workbook is a local runtime artifact")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/open_current_trial_workbook.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "READONLY_USER_TRIAL_READY"
    assert result["m6_operational_status"] == "NOT_STARTED"
    assert result["initial_assisted_use"] == "NOT_REACHED"
    assert result["action"] == "no_order"
