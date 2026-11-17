import json
import zipfile
from pathlib import Path
import pytest
from value_investment_agent.application.research import first_input_delivery_v1 as module


def setup_delivery(tmp_path, monkeypatch):
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "runtime").mkdir()
    with zipfile.ZipFile(stage / "runtime/source.zip", "w") as archive:
        archive.writestr("src/example.py", "# TEST_ONLY\n")
    expected = {key: None for key in module.KEYS}
    expected.update(status="SOURCE_BOUND_FIRST_INPUT_COMPILED", action="no_order")
    bundle = dict(schema_version="first-input-public-delivery-v1", action="no_order",
                  source_zip=dict(path="runtime/source.zip", sha256="a" * 64), configs={},
                  evaluated_at="2026-11-17T12:00:00+00:00", expected={"600519": expected})
    packet = dict(bundle=dict(path="runtime/bundle.json"),
                  items=[dict(original_path="runtime/source.zip", sha256="a" * 64)])
    def restore(**kwargs):
        (stage / "runtime/bundle.json").write_text(json.dumps(bundle))
        kwargs["validate"](stage, packet)
        return packet
    monkeypatch.setattr(module, "restore_archive", restore)
    monkeypatch.setattr(module, "read_first_research_input", lambda **kwargs: expected.copy())
    return bundle


def run(tmp_path):
    return module.restore_first_input_delivery(archive_root=tmp_path, manifest_sha256="a" * 64,
                                               destination=tmp_path / "destination")


def test_restore_recalculates_and_requires_matching_result(tmp_path, monkeypatch):
    setup_delivery(tmp_path, monkeypatch)
    assert run(tmp_path)["status"] == "ISOLATED_RESTORE_REPLAY_PASSED"
    monkeypatch.setattr(module, "read_first_research_input", lambda **kwargs: {"status": "UNASSESSABLE"})
    with pytest.raises(ValueError, match="RESTORED_RESULT_MISMATCH"):
        run(tmp_path)


def test_config_escape_and_empty_results_rejected(tmp_path, monkeypatch):
    bundle = setup_delivery(tmp_path, monkeypatch)
    bundle["configs"] = {"config/../../outside.json": {}}
    with pytest.raises(ValueError, match="CONFIG_PATH_INVALID"):
        run(tmp_path)
    bundle["expected"] = {}
    with pytest.raises(ValueError, match="SUCCESSFUL_PUBLIC_RESULTS_REQUIRED"):
        run(tmp_path)


def test_checked_in_public_delivery_replays_real_sources(tmp_path):
    root = Path(__file__).resolve().parents[1]
    result = module.restore_first_input_delivery(
        archive_root=root / "artifacts/current/first-input-delivery-20261117",
        manifest_sha256="e79dbe10d20d22ce432b491fc9d6ef1efbf5d0f4853d48a3792c74917399d66d",
        destination=tmp_path / "restored")
    assert result["status"] == "ISOLATED_RESTORE_REPLAY_PASSED"
    assert result["action"] == "no_order"
