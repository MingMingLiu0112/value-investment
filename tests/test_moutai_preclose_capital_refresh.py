import importlib.util
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "moutai_preclose_capital_refresh", ROOT / "scripts" / "prepare_moutai_preclose_capital_refresh.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHANGHAI = timezone(timedelta(hours=8))


def test_preclose_receipt_rejects_after_close_and_wrong_day():
    with pytest.raises(ValueError, match="too late"):
        MODULE.require_preclose(datetime(2026, 9, 21, 15, 0, tzinfo=SHANGHAI), date(2026, 9, 21))
    with pytest.raises(ValueError, match="equal"):
        MODULE.require_preclose(datetime(2026, 9, 21, 14, 45, tzinfo=SHANGHAI), date(2026, 9, 22))


def test_preclose_receipt_accepts_weekday_before_close():
    MODULE.require_preclose(datetime(2026, 9, 21, 14, 45, tzinfo=SHANGHAI), date(2026, 9, 21))


def test_nested_collection_process_keeps_windows_environment(monkeypatch):
    captured = {}
    monkeypatch.setenv("SystemRoot", "C:\\Windows")

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="{}\n", stderr="")

    monkeypatch.setattr(MODULE.subprocess, "run", fake_run)
    assert MODULE.run("scripts/fake.py") == {}
    inherited = {key.upper(): value for key, value in captured["env"].items()}
    assert inherited["SYSTEMROOT"] == "C:\\Windows"
    assert captured["env"]["PYTHONUTF8"] == "1"


def test_filing_index_result_requires_its_explicit_directory_contract(tmp_path):
    assert MODULE.index_directory({"directory": str(tmp_path)}) == tmp_path.resolve()
    with pytest.raises(ValueError, match="directory"):
        MODULE.index_directory({"output": str(tmp_path)})
