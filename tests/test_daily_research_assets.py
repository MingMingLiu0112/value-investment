"""Isolated synthetic asset recovery, never an investment-admission fixture."""
import json
from pathlib import Path

import pytest

from value_investment_agent.application.product.common import sha256_file
from value_investment_agent.application.product.daily_assets import (
    inspect_daily_case_assets, recover_daily_case_assets,
)
from value_investment_agent.application.product.daily_trade_assistant import run_daily_trade_assistant
from value_investment_agent.presentation.daily_trade_assistant import _render_report


def _case(root: Path):
    request = root / "request.json"
    request.write_text("{}", encoding="utf-8")
    return {"package": "package.json", "package_sha256": "a" * 64,
            "schedule_request": "request.json", "schedule_request_sha256": sha256_file(request)}


def test_scoped_retained_original_does_not_overwrite_conflicting_file(tmp_path):
    case = _case(tmp_path)
    original, retained = tmp_path / "conflict.txt", tmp_path / "retained.txt"
    original.write_text("conflicting serialized bytes", encoding="utf-8")
    retained.write_text("synthetic original bytes", encoding="utf-8")
    digest = sha256_file(retained)
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"symbol": "600887", "source": {
        "path": "conflict.txt", "sha256": digest}}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    manifest = tmp_path / "recovery.json"
    manifest.write_text(json.dumps({"schema_version": "daily-original-recovery-v1",
        "symbol": "600887", "action": "no_order", "research_approval": False,
        "package_sha256": case["package_sha256"], "recovered_originals": [{
            "original_path": "conflict.txt", "recovered_path": "retained.txt", "expected_sha256": digest}]}), encoding="utf-8")
    case.update(recovery_manifest="recovery.json", recovery_manifest_sha256=sha256_file(manifest))
    index = inspect_daily_case_assets(root=tmp_path, case=case)
    assert not index["blockers"]
    assert index["verified_original_recoveries"][0]["original_actual_sha256"] == sha256_file(original)
    assert original.read_text(encoding="utf-8") == "conflicting serialized bytes"
    retained.write_text("drift", encoding="utf-8")
    with pytest.raises(ValueError, match="retained original hash mismatch"):
        inspect_daily_case_assets(root=tmp_path, case=case)
    retained.unlink()
    missing = inspect_daily_case_assets(root=tmp_path, case=case)
    assert any(row['path']=='retained.txt' and row['status']=='MISSING' for row in missing['blockers'])
    assert missing['verified_original_recoveries'][0]['status']=='RETAINED_ORIGINAL_MISSING'
    manifest.unlink()
    assert any(row['path']=='recovery.json' for row in inspect_daily_case_assets(root=tmp_path,case=case)['blockers'])


def test_missing_case_produces_truthful_report_without_research_or_private_input(tmp_path):
    result = run_daily_trade_assistant(root=tmp_path, symbol="600519", case=_case(tmp_path),
        output_dir=tmp_path / "runtime/run", agent_mode="none", report_renderer=_render_report)
    assert result["status"] == "BLOCKED_RESEARCH_ASSETS"
    assert "workbench" not in result["outputs"]
    assert result["position_guidance"] is None
    assert result["action"] == "no_order"
    index = json.loads((tmp_path / result["outputs"]["asset_index"]["path"]).read_text(encoding="utf-8"))
    assert index["dependency_inventory_complete"] is False
    assert index["blockers"][0]["path"] == "package.json"


def test_transitive_original_is_indexed_and_hash_conflict_never_silenced(tmp_path):
    case = _case(tmp_path)
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"source": {"location": "runtime/original.pdf", "sha256": "b" * 64}}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    index = inspect_daily_case_assets(root=tmp_path, case=case)
    assert index["blockers"][0]["path"] == "runtime/original.pdf"
    package.write_text(json.dumps({"sources": [{"path": "same.pdf", "sha256": "b" * 64},
                                              {"path": "same.pdf", "sha256": "c" * 64}]}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    with pytest.raises(ValueError, match="conflicting asset"):
        inspect_daily_case_assets(root=tmp_path, case=case)


def test_recovery_restores_original_and_newly_discovered_dependencies(tmp_path):
    case = _case(tmp_path)
    recovery = tmp_path / "runtime/recovery"
    original = recovery / "runtime/original.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"synthetic original, not real financial evidence")
    package = recovery / "package.json"
    package.write_text(json.dumps({"source": {"path": "runtime/original.pdf", "sha256": sha256_file(original)}}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    index = recover_daily_case_assets(root=tmp_path, case=case, source_root=recovery)
    assert index["status"] == "FILE_INTEGRITY_VERIFIED_NOT_RESEARCH_APPROVAL"
    assert set(index["restored_paths"]) == {"package.json", "runtime/original.pdf"}
    assert (tmp_path / "runtime/original.pdf").read_bytes() == original.read_bytes()
    assert recover_daily_case_assets(root=tmp_path, case=case, source_root=recovery)["restored_paths"] == []


def test_recovery_never_overwrites_wrong_existing_bytes(tmp_path):
    case = _case(tmp_path)
    package = tmp_path / "package.json"
    package.write_text("user edits", encoding="utf-8")
    recovery = tmp_path / "runtime/recovery"
    recovery.mkdir(parents=True)
    (recovery / "package.json").write_text("{}", encoding="utf-8")
    case["package_sha256"] = sha256_file(recovery / "package.json")
    index = recover_daily_case_assets(root=tmp_path, case=case, source_root=recovery)
    assert index["status"] == "BLOCKED_RESEARCH_ASSETS"
    assert package.read_text(encoding="utf-8") == "user edits"


def test_asset_path_escape_is_rejected(tmp_path):
    case = _case(tmp_path)
    case["package"] = "../external.json"
    with pytest.raises(ValueError, match="project root"):
        inspect_daily_case_assets(root=tmp_path, case=case)


def test_pinned_publication_recovery_reuses_identical_original_without_overwriting(tmp_path):
    case = _case(tmp_path)
    original = tmp_path / "original.json"
    original.write_text("user changed original", encoding="utf-8")
    recovered = tmp_path / "recovered.json"
    recovered.write_text("{}", encoding="utf-8")
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"source": {"path": "original.json", "sha256": sha256_file(recovered)}}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    publication = tmp_path / "publication.json"
    publication.write_text(json.dumps({"verified_source_recoveries": [{
        "original_path": "original.json", "expected_sha256": sha256_file(recovered),
        "recovered_path": "recovered.json"}]}), encoding="utf-8")
    case.update(publication_input="publication.json", publication_input_sha256=sha256_file(publication))
    index = inspect_daily_case_assets(root=tmp_path, case=case)
    assert index["blockers"] == []
    assert original.read_text(encoding="utf-8") == "user changed original"


def test_application_has_no_presentation_import():
    import ast
    import inspect
    from value_investment_agent.application.product import daily_trade_assistant
    tree = ast.parse(inspect.getsource(daily_trade_assistant))
    assert not any(isinstance(node, ast.ImportFrom) and "presentation" in (node.module or "")
                   for node in ast.walk(tree))


def test_optional_publication_loss_does_not_stop_security_research(tmp_path, monkeypatch):
    from value_investment_agent.application.product import daily_trade_assistant as app
    case = _case(tmp_path)
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"symbol": "600519", "point_in_time": {"research_as_of": "2026-10-08"}}), encoding="utf-8")
    case["package_sha256"] = sha256_file(package)
    request = tmp_path / "request.json"
    request.write_text(json.dumps({"symbol": "600519"}), encoding="utf-8")
    case["schedule_request_sha256"] = sha256_file(request)
    case.update(publication_input="lost-publication.json", publication_input_sha256="b" * 64)
    called = []
    def build(**kwargs):
        called.append(kwargs)
        value = {"symbol": "600519", "suggested_state": "NO_ACTION", "decision_recommendation": None}
        kwargs["output_path"].write_text(json.dumps(value), encoding="utf-8")
        return {"result": value}
    monkeypatch.setattr(app, "build_current_workbench_for_symbol", build)
    result = app.run_daily_trade_assistant(root=tmp_path, symbol="600519", case=case,
        output_dir=tmp_path / "runtime/run", agent_mode="none", report_renderer=_render_report)
    assert len(called) == 1
    assert result["status"] == "RESEARCH_RUN_COMPLETED_WITH_ADMISSION_STATUS"
    assert result["optional_asset_blockers"][0]["required_for_research"] is False


def test_failed_exclusive_recovery_cleans_only_its_partial_file(tmp_path, monkeypatch):
    from value_investment_agent.application.product import daily_assets
    case = _case(tmp_path)
    recovery = tmp_path / "runtime/recovery"
    recovery.mkdir(parents=True)
    original = recovery / "package.json"
    original.write_text("{}", encoding="utf-8")
    case["package_sha256"] = sha256_file(original)
    def interrupted(incoming, outgoing):
        outgoing.write(b"partial")
        raise OSError("interrupted copy")
    monkeypatch.setattr(daily_assets.shutil, "copyfileobj", interrupted)
    with pytest.raises(OSError, match="interrupted"):
        recover_daily_case_assets(root=tmp_path, case=case, source_root=recovery)
    assert not (tmp_path / "package.json").exists()
    assert original.read_text(encoding="utf-8") == "{}"
