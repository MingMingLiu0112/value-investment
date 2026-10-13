"""Backup/restore contract for the private portfolio journal (WEB-D2 P0.3)."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from value_investment_agent.application.portfolio.private_backup import (
    BACKUP_SCHEMA,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from value_investment_agent.application.portfolio.private_portfolio_service import (
    PrivateJournal,
)
from value_investment_agent.domain.portfolio.dual_sleeve_records import canonical_bytes

UTC = timezone.utc


def _append(path: Path, index: int) -> dict:
    return PrivateJournal(path).append(
        kind="FILL_PREPARED",
        body={"note": f"record-{index}"},
        response={"status": "FILL_PREPARED", "sequence": index},
        idempotency_key=f"backup-test-{index}",
        request_sha256=hashlib.sha256(f"backup-test-{index}".encode("utf-8")).hexdigest(),
        recorded_at=datetime(2026, 10, 13, 4, 0, index, tzinfo=UTC),
        changes_holdings=False,
    )


def _journal(tmp_path: Path, records: int = 2) -> Path:
    path = tmp_path / "portfolio" / "journal.jsonl"
    for index in range(records):
        _append(path, index)
    return path


def _break_first_record(path: Path) -> bytes:
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["body"]["note"] = "tampered"
    lines[0] = json.dumps(record, ensure_ascii=False)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path.read_bytes()


def test_create_verify_roundtrip_is_verbatim_and_verified(tmp_path):
    journal = _journal(tmp_path)
    source_bytes = journal.read_bytes()
    records = PrivateJournal(journal).read()
    created = create_backup(journal, created_at=datetime(2026, 10, 13, 6, 0, tzinfo=UTC))
    assert created["status"] == "CREATED"
    assert created["action"] == "no_order"
    assert created["source_status"] == "VALID"
    assert created["record_count"] == 2
    assert created["head_record_sha256"] == records[-1]["record_sha256"]
    assert created["source_sha256"] == hashlib.sha256(source_bytes).hexdigest()
    assert created["created_at"] == "2026-10-13T06:00:00+00:00"
    bundle = Path(created["path"])
    assert bundle.parent == journal.parent / "backups"
    assert bundle.name == created["backup_id"]
    assert bundle.name.startswith("backup-")
    assert (bundle / "journal.jsonl").read_bytes() == source_bytes
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == BACKUP_SCHEMA
    assert manifest["action"] == "no_order"
    assert manifest["backup_id"] == created["backup_id"]
    assert manifest["created_at"] == created["created_at"]
    assert manifest["source_journal_path"] == str(journal)
    assert manifest["source_sha256"] == manifest["copied_sha256"] == created["source_sha256"]
    assert manifest["record_count"] == 2
    assert manifest["head_record_sha256"] == records[-1]["record_sha256"]
    assert manifest["source_status"] == "VALID"
    assert manifest["source_invalid_reason"] is None
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    assert manifest["manifest_sha256"] == hashlib.sha256(canonical_bytes(payload)).hexdigest()
    verified = verify_backup(bundle)
    assert verified["status"] == "VERIFIED"
    assert verified["action"] == "no_order"
    assert verified["backup_id"] == created["backup_id"]
    assert verified["record_count"] == 2
    assert verified["head_record_sha256"] == created["head_record_sha256"]
    assert verified["source_status"] == "VALID"


def test_tampered_journal_byte_fails_verification(tmp_path):
    bundle = Path(create_backup(_journal(tmp_path))["path"])
    data = bytearray((bundle / "journal.jsonl").read_bytes())
    index = data.index(b"no_order")
    data[index] = data[index] ^ 0x01
    (bundle / "journal.jsonl").write_bytes(bytes(data))
    result = verify_backup(bundle)
    assert result["status"] == "INVALID"
    assert result["reason"]
    assert result["action"] == "no_order"


def test_tampered_manifest_fails_verification(tmp_path):
    bundle = Path(create_backup(_journal(tmp_path))["path"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    manifest["record_count"] = 99
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    result = verify_backup(bundle)
    assert result["status"] == "INVALID"
    assert "摘要" in result["reason"]
    payload = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(canonical_bytes(payload)).hexdigest()
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    recount = verify_backup(bundle)
    assert recount["status"] == "INVALID"
    assert "记录数" in recount["reason"]


def test_restore_requires_explicit_confirmation(tmp_path):
    journal = _journal(tmp_path)
    created = create_backup(journal)
    bundle = Path(created["path"])
    current = journal.read_bytes()
    with pytest.raises(ValueError, match="明确用户确认"):
        restore_backup(bundle, journal)
    with pytest.raises(ValueError, match="明确用户确认"):
        restore_backup(bundle, journal, confirm=False)
    assert journal.read_bytes() == current
    assert [item["backup_id"] for item in list_backups(journal.parent / "backups")] == [
        created["backup_id"]
    ]


def test_restore_replaces_target_and_keeps_pre_restore_safety_bundle(tmp_path):
    journal = _journal(tmp_path)
    backup_bytes = journal.read_bytes()
    created = create_backup(journal, created_at=datetime(2026, 10, 13, 6, 0, tzinfo=UTC))
    bundle = Path(created["path"])
    _append(journal, 2)
    current = journal.read_bytes()
    assert current != backup_bytes
    result = restore_backup(bundle, journal, confirm=True)
    assert result["status"] == "RESTORED"
    assert result["action"] == "no_order"
    assert result["backup_id"] == created["backup_id"]
    assert result["restored_record_count"] == 2
    assert result["head_record_sha256"] == PrivateJournal(journal).read()[-1]["record_sha256"]
    assert journal.read_bytes() == backup_bytes == (bundle / "journal.jsonl").read_bytes()
    safety_id = result["safety_backup_id"]
    assert safety_id and safety_id.startswith("pre-restore-")
    safety = journal.parent / "backups" / safety_id
    assert (safety / "journal.jsonl").read_bytes() == current
    manifest = json.loads((safety / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_status"] == "VALID"
    assert verify_backup(safety)["status"] == "VERIFIED"


def test_restore_refuses_invalid_bundle_and_leaves_target_untouched(tmp_path):
    journal = _journal(tmp_path)
    created = create_backup(journal)
    bundle = Path(created["path"])
    data = bytearray((bundle / "journal.jsonl").read_bytes())
    index = data.index(b"record-0")
    data[index] = data[index] ^ 0x01
    (bundle / "journal.jsonl").write_bytes(bytes(data))
    before = journal.read_bytes()
    with pytest.raises(ValueError) as error:
        restore_backup(bundle, journal, confirm=True)
    assert "拒绝恢复" in str(error.value)
    assert journal.read_bytes() == before
    assert [item["backup_id"] for item in list_backups(journal.parent / "backups")] == [
        created["backup_id"]
    ]


def test_list_backups_is_newest_first_and_tolerates_partial_bundles(tmp_path):
    journal = _journal(tmp_path)
    older = create_backup(journal, created_at=datetime(2020, 1, 1, tzinfo=UTC))
    newer = create_backup(journal, created_at=datetime(2020, 1, 2, tzinfo=UTC))
    backup_root = journal.parent / "backups"
    partial = backup_root / "backup-20200103T000000Z-00000000"
    partial.mkdir()
    (partial / "journal.jsonl").write_bytes(journal.read_bytes())
    past = datetime(2019, 1, 1, tzinfo=UTC).timestamp()
    os.utime(partial, (past, past))
    listing = list_backups(backup_root)
    assert [item["backup_id"] for item in listing] == [
        newer["backup_id"],
        older["backup_id"],
        partial.name,
    ]
    assert [item["status"] for item in listing] == ["VERIFIED", "VERIFIED", "INVALID"]
    assert listing[2]["reason"]
    assert listing[0]["created_at"].startswith("2020-01-02")
    assert listing[0]["action"] == "no_order"
    assert list_backups(tmp_path / "absent") == []


def test_create_marks_broken_source_invalid_and_keeps_bytes(tmp_path):
    journal = _journal(tmp_path)
    broken = _break_first_record(journal)
    created = create_backup(journal)
    assert created["status"] == "CREATED"
    assert created["source_status"] == "INVALID"
    bundle = Path(created["path"])
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_status"] == "INVALID"
    assert manifest["source_invalid_reason"]
    assert manifest["copied_sha256"] == hashlib.sha256(broken).hexdigest()
    assert (bundle / "journal.jsonl").read_bytes() == broken
    assert verify_backup(bundle)["status"] == "INVALID"


def test_explicit_backup_root_outside_journal_directory_is_rejected(tmp_path):
    journal = _journal(tmp_path)
    outside = tmp_path / "outside"
    with pytest.raises(ValueError):
        create_backup(journal, backup_root=outside)
    assert not outside.exists()


def test_explicit_backup_root_inside_journal_directory_is_allowed(tmp_path):
    journal = _journal(tmp_path)
    custom = journal.parent / "custom-backups"
    created = create_backup(journal, backup_root=custom)
    bundle = Path(created["path"])
    assert bundle.parent == custom
    assert verify_backup(bundle)["status"] == "VERIFIED"


def test_verify_reports_missing_bundle(tmp_path):
    result = verify_backup(tmp_path / "absent")
    assert result["status"] == "MISSING"
    assert result["reason"]
    assert result["record_count"] is None
    assert result["head_record_sha256"] is None
    assert result["action"] == "no_order"


def test_restore_replaces_unreadable_journal_via_explicit_confirm_route(tmp_path):
    journal = _journal(tmp_path)
    backup_bytes = journal.read_bytes()
    created = create_backup(journal)
    bundle = Path(created["path"])
    lines = journal.read_text(encoding="utf-8").splitlines()
    journal.write_text(lines[1] + "\n", encoding="utf-8")
    broken = journal.read_bytes()
    with pytest.raises(ValueError):
        restore_backup(bundle, journal)
    assert journal.read_bytes() == broken
    result = restore_backup(bundle, journal, confirm=True)
    assert result["status"] == "RESTORED"
    assert journal.read_bytes() == backup_bytes
    safety_id = result["safety_backup_id"]
    assert safety_id and safety_id.startswith("pre-restore-")
    safety = journal.parent / "backups" / safety_id
    assert (safety / "journal.jsonl").read_bytes() == broken
    manifest = json.loads((safety / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_status"] == "INVALID"
    assert manifest["source_invalid_reason"]


def test_restore_into_missing_journal_requires_confirm_and_writes_bytes(tmp_path):
    source = _journal(tmp_path, records=1)
    bundle = Path(create_backup(source)["path"])
    target = tmp_path / "restored" / "journal.jsonl"
    with pytest.raises(ValueError, match="明确用户确认"):
        restore_backup(bundle, target, confirm=False)
    assert not target.exists()
    result = restore_backup(bundle, target, confirm=True)
    assert result["status"] == "RESTORED"
    assert result["safety_backup_id"] is None
    assert target.read_bytes() == (bundle / "journal.jsonl").read_bytes()
    assert len(PrivateJournal(target).read()) == 1
