from __future__ import annotations

from hashlib import sha256
import importlib.util
import json
from pathlib import Path

import pytest

from value_investment_agent.application.architecture import (
    ARTIFACT_RELOCATION_SCHEMA,
    build_artifact_relocation_inventory,
)
from value_investment_agent.application.architecture.artifact_relocation import (
    CANONICAL_WORKBOOK,
)


ROOT = Path(__file__).resolve().parents[1]


def _load_audit_cli_module():
    spec = importlib.util.spec_from_file_location(
        "audit_artifact_relocation",
        ROOT / "scripts" / "audit_artifact_relocation.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_registry_builder_module():
    spec = importlib.util.spec_from_file_location(
        "build_current_artifact_registry",
        ROOT / "scripts" / "diagnostics" / "build_current_artifact_registry.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inventory_keeps_canonical_and_current_pointer_artifacts(tmp_path: Path):
    canonical = tmp_path / CANONICAL_WORKBOOK
    canonical.write_bytes(b"canonical")
    candidate = tmp_path / "candidate.xlsx"
    candidate.write_bytes(b"candidate")
    pointer = tmp_path / "config" / "current-trial-workbook.json"
    pointer.parent.mkdir()
    pointer.write_text(
        json.dumps({"workbook": "candidate.xlsx"}),
        encoding="utf-8",
    )

    inventory = build_artifact_relocation_inventory(
        tmp_path,
        tracked_paths={canonical.name, candidate.name},
    ).as_dict()
    by_name = {item["path"]: item for item in inventory["artifacts"]}

    assert inventory["schema_version"] == ARTIFACT_RELOCATION_SCHEMA
    assert inventory["action"] == "no_order"
    assert by_name[canonical.name]["classification"] == "CANONICAL_WORKBOOK"
    assert by_name[candidate.name]["classification"] == "CURRENT_POINTER"
    assert by_name[candidate.name]["recommended_action"] == "KEEP_CURRENT"
    assert by_name[candidate.name]["sha256"] == sha256(b"candidate").hexdigest()
    assert by_name[candidate.name]["tracked"] is True


def test_inventory_marks_code_and_document_consumers_conservatively(tmp_path: Path):
    code_consumer = tmp_path / "scripts" / "use_candidate.py"
    code_consumer.parent.mkdir()
    code_consumer.write_text(
        "print('code-candidate.xlsx')\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "history.md").write_text(
        "doc-candidate.xlsx\n",
        encoding="utf-8",
    )
    (tmp_path / "code-candidate.xlsx").write_bytes(b"code")
    (tmp_path / "doc-candidate.xlsx").write_bytes(b"doc")
    (tmp_path / "orphan.xlsx").write_bytes(b"orphan")

    inventory = build_artifact_relocation_inventory(tmp_path).as_dict()
    by_name = {item["path"]: item for item in inventory["artifacts"]}

    assert by_name["code-candidate.xlsx"]["classification"] == "STATIC_CONSUMER"
    assert (
        by_name["code-candidate.xlsx"]["recommended_action"]
        == "KEEP_UNTIL_CONSUMERS_MIGRATE"
    )
    assert by_name["doc-candidate.xlsx"]["classification"] == "HISTORICAL_REFERENCE"
    assert (
        by_name["doc-candidate.xlsx"]["recommended_action"]
        == "ARCHIVE_AFTER_DOC_UPDATE"
    )
    assert by_name["orphan.xlsx"]["classification"] == "UNREFERENCED"
    assert (
        by_name["orphan.xlsx"]["recommended_action"]
        == "REVIEW_FOR_ARCHIVE_OR_DELETE"
    )


def test_inventory_does_not_modify_root_artifacts(tmp_path: Path):
    artifact = tmp_path / "candidate.xlsx"
    artifact.write_bytes(b"bytes")
    before = artifact.read_bytes()

    build_artifact_relocation_inventory(tmp_path)

    assert artifact.read_bytes() == before


def test_inventory_ignores_generated_registries_as_consumers(tmp_path: Path):
    artifact = tmp_path / "candidate.xlsx"
    artifact.write_bytes(b"candidate")
    current = tmp_path / "artifacts" / "current"
    current.mkdir(parents=True)
    for version in ("v1", "v2"):
        (current / f"artifact-registry-{version}.json").write_text(
            json.dumps({"path": artifact.name}),
            encoding="utf-8",
        )

    inventory = build_artifact_relocation_inventory(tmp_path).as_dict()
    record = next(item for item in inventory["artifacts"] if item["path"] == artifact.name)

    assert record["classification"] == "UNREFERENCED"
    assert record["references"] == []


def test_inventory_treats_sibling_manifest_as_hash_binding(tmp_path: Path):
    artifact = tmp_path / "candidate.xlsx"
    artifact.write_bytes(b"candidate")
    manifest = tmp_path / "candidate.daily-manifest.json"
    manifest.write_text(
        json.dumps({"workbook_path": "candidate.xlsx"}),
        encoding="utf-8",
    )

    inventory = build_artifact_relocation_inventory(tmp_path).as_dict()
    by_name = {item["path"]: item for item in inventory["artifacts"]}

    assert (
        by_name["candidate.xlsx"]["classification"]
        == "POSSIBLE_HASH_OR_RECEIPT_BINDING"
    )
    assert (
        by_name["candidate.xlsx"]["recommended_action"]
        == "KEEP_UNTIL_RELOCATION_VERIFIER"
    )
    assert (
        by_name["candidate.daily-manifest.json"]["classification"]
        == "PROVENANCE_ARTIFACT"
    )
    assert (
        by_name["candidate.daily-manifest.json"]["recommended_action"]
        == "KEEP_PROVENANCE"
    )


def test_tracked_paths_is_optional_outside_a_git_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_audit_cli_module()

    def fail(*args, **kwargs):
        raise module.subprocess.CalledProcessError(128, args[0])

    monkeypatch.setattr(module.subprocess, "run", fail)
    assert module._tracked_paths(tmp_path) == ()


def test_registry_v2_distinguishes_external_canonical_from_repo_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_registry_builder_module()
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "artifacts" / "current").mkdir(parents=True)
    root_workbook = root / CANONICAL_WORKBOOK
    root_workbook.write_bytes(b"repository reference")
    external_workbook = tmp_path / "wps" / CANONICAL_WORKBOOK
    external_workbook.parent.mkdir()
    external_workbook.write_bytes(b"configured canonical")
    external_hash = sha256(external_workbook.read_bytes()).hexdigest()
    (root / "config" / "current-trial-workbook.json").write_text(
        json.dumps({"canonical_workbook_sha256": external_hash}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKBOOK_PATH", str(external_workbook))

    inventory = build_artifact_relocation_inventory(
        root, tracked_paths={CANONICAL_WORKBOOK}
    ).as_dict()
    payload = module._registry_payload(root, inventory, external_workbook)
    records = {item["path"]: item for item in payload["records"]}

    assert payload["schema_version"] == "current-artifact-registry-v2"
    assert records[CANONICAL_WORKBOOK]["status"] == "REPOSITORY_REFERENCE_SNAPSHOT"
    assert records[CANONICAL_WORKBOOK]["current_or_historical"] == "HISTORICAL_OR_REFERENCE"
    external = records["WORKBOOK_PATH (local path redacted)"]
    assert external["status"] == "CANONICAL_WORKBOOK"
    assert external["sha256"] == external_hash
    assert external["verified_against_pointer"] is True
    assert str(external_workbook) not in json.dumps(payload)


def test_registry_v2_fails_closed_when_external_workbook_hash_disagrees(
    tmp_path: Path,
):
    module = _load_registry_builder_module()
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "current-trial-workbook.json").write_text(
        json.dumps({"canonical_workbook_sha256": "0" * 64}),
        encoding="utf-8",
    )
    workbook = tmp_path / "workbook.xlsx"
    workbook.write_bytes(b"actual workbook")

    with pytest.raises(ValueError, match="does not match"):
        module._registry_payload(root, {"artifacts": []}, workbook)


def test_registry_builder_rejects_overwriting_v1_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _load_registry_builder_module()
    output = tmp_path / "artifact-registry-v1.json"
    output.write_bytes(b"preserved v1")
    monkeypatch.setattr(
        module.argparse.ArgumentParser,
        "parse_args",
        lambda self: module.argparse.Namespace(root=tmp_path, output=output),
    )
    monkeypatch.setattr(
        module,
        "_tracked_paths",
        lambda _root: (),
    )
    (tmp_path / "config").mkdir()
    workbook = tmp_path / "workbook.xlsx"
    workbook.write_bytes(b"workbook")
    (tmp_path / "config" / "current-trial-workbook.json").write_text(
        json.dumps({"canonical_workbook_sha256": sha256(b"workbook").hexdigest()}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WORKBOOK_PATH", str(workbook))

    with pytest.raises(ValueError, match="preserved historical snapshot"):
        module.main()
    assert output.read_bytes() == b"preserved v1"
