"""Atomic immutable-output persistence regressions."""
import json
import os

import pytest

from value_investment_agent.application.product import common


def test_write_new_json_publishes_complete_bytes_without_overwrite(tmp_path):
    target = tmp_path / "receipt.json"
    common.write_new_json(target, {"action": "no_order", "version": 1})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "action": "no_order",
        "version": 1,
    }

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        common.write_new_json(target, {"action": "no_order", "version": 2})
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == 1


def test_failed_fsync_leaves_no_partial_target_and_can_retry(tmp_path, monkeypatch):
    target = tmp_path / "packet.json"

    def fail_fsync(descriptor):
        raise OSError("forced fsync failure")

    monkeypatch.setattr(common.os, "fsync", fail_fsync)
    with pytest.raises(OSError, match="forced fsync failure"):
        common.write_new_json(target, {"action": "no_order"})

    assert not target.exists()
    assert list(tmp_path.glob(".packet.json.*.part")) == []

    monkeypatch.undo()
    common.write_new_json(target, {"action": "no_order"})
    assert json.loads(target.read_text(encoding="utf-8"))["action"] == "no_order"


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length path regression")
def test_windows_long_path_publishes_without_partial_output(tmp_path):
    target = (tmp_path / ("d" * 60) / ("e" * 60) / ("x" * 80)
              / ("a" * 120) / "result.json")
    assert len(str(target)) > 260

    common.write_new_json(target, {"action": "no_order", "status": "COMPLETE"})

    native = common._native_path(target)
    with open(native, encoding="utf-8") as stream:
        assert json.load(stream)["status"] == "COMPLETE"
    assert not [name for name in os.listdir(common._native_path(target.parent))
                if name.startswith(".result.json.") and name.endswith(".part")]
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        common.write_new_json(target, {"action": "no_order", "status": "CHANGED"})
