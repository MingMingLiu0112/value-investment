import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("moutai_publish", ROOT / "scripts" / "publish_moutai_case_workbook.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_wait_for_complete_file_rejects_missing_file(tmp_path):
    with pytest.raises(TimeoutError):
        MODULE.wait_for_complete_file(tmp_path / "missing.xlsx", attempts=1, delay_seconds=0)


def test_wait_for_complete_file_accepts_written_file(tmp_path):
    path = tmp_path / "ready.xlsx"
    path.write_bytes(b"workbook")
    MODULE.wait_for_complete_file(path, attempts=2, delay_seconds=0)
