from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]


CANONICAL_NAME = "A股价值投资_Agent前端智能跟踪模板.xlsx"


def _script_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "scripts").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "scripts" / "open_current_trial_workbook.py").write_text(
        (ROOT / "scripts" / "open_current_trial_workbook.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "config" / "current-trial-workbook.json").write_text(
        (ROOT / "config" / "current-trial-workbook.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return root


def _run(root: Path, workbook_path: Path | None) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key != "WORKBOOK_PATH"}
    if workbook_path is not None:
        environment["WORKBOOK_PATH"] = str(workbook_path)
    return subprocess.run(
        [sys.executable, str(root / "scripts" / "open_current_trial_workbook.py")],
        cwd=root, capture_output=True, text=True, env=environment,
    )


def test_current_trial_pointer_resolves_only_temp_canonical_workbook(tmp_path: Path):
    pointer = json.loads((ROOT / "config/current-trial-workbook.json").read_text(encoding="utf-8"))
    assert pointer["workbook_source"] == "WORKBOOK_PATH"
    assert "workbook" not in pointer
    assert "candidate" not in json.dumps(pointer, ensure_ascii=False).lower()
    canonical = tmp_path / CANONICAL_NAME
    Workbook().save(canonical)
    completed = _run(_script_root(tmp_path), canonical)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["workbook"] == str(canonical.resolve())
    assert result["status"] == "CANONICAL_READONLY_TRIAL_READY"
    assert result["m6_operational_status"] == "NOT_STARTED"
    assert result["initial_assisted_use"] == "NOT_REACHED"
    assert result["action"] == "no_order"


def test_current_trial_pointer_fails_closed_without_or_with_wrong_workbook_path(tmp_path: Path):
    root = _script_root(tmp_path)
    missing = _run(root, None)
    wrong = _run(root, tmp_path / "other.xlsx")
    assert missing.returncode != 0
    assert wrong.returncode != 0
    assert "CANONICAL_WORKBOOK_NOT_RESOLVED" in missing.stderr
    assert "CANONICAL_WORKBOOK_NOT_RESOLVED" in wrong.stderr
