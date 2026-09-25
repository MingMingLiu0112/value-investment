from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from value_investment_agent.application.architecture import (
    ARTIFACT_RELOCATION_SCHEMA,
    build_artifact_relocation_inventory,
)
from value_investment_agent.application.architecture.artifact_relocation import (
    CANONICAL_WORKBOOK,
)


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
