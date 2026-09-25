"""Content and target binding for isolated restore receipts (no database required)."""

import hashlib
import json
from contextlib import nullcontext
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from value_investment_agent import backup
from value_investment_agent import m6_operational_readiness as m6
from value_investment_agent.m6_operational_readiness import (
    DONE,
    PARTIAL,
    M6PreflightConfig,
    RestoreTarget,
    assess_restore_evidence,
)


SOURCE = "postgresql://localhost/source"
TARGET = "postgresql://127.0.0.1:5433/value_agent_restore"


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _seal(receipt):
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = hashlib.sha256(backup._canonical_bytes(receipt)).hexdigest()


@pytest.fixture
def bundle(tmp_path):
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"database dump")
    evidence = tmp_path / "evidence.pdf"
    evidence.write_bytes(b"original evidence")
    checks = {"data_points": {"rows": 2, "fingerprint": "abc"}}
    manifest = {
        "backup_id": "backup-1", "database_dump": dump.name,
        "sha256": backup.sha256_file(dump),
        "evidence_files": [{"path": evidence.name, "sha256": backup.sha256_file(evidence)}],
        "table_check_version": 1, "table_checks": checks, "schema_version": "001_init",
        "snapshot_at": "2026-01-01T00:00:00+00:00",
    }
    manifest_path = tmp_path / "backup.manifest.json"
    _write_json(manifest_path, manifest)
    receipt = {
        "schema_version": backup.RESTORE_VERIFIER_VERSION,
        "verifier_version": backup.RESTORE_VERIFIER_VERSION,
        "action": "no_order", "observed": "actual", "status": "passed",
        "restore_command_result": "exit_0", "database_verifier_result": "table_checks_equal",
        "source_database_identity": backup._database_identity(SOURCE),
        "restore_target_identity": backup._database_identity(TARGET),
        "backup_manifest": manifest_path.name,
        "backup_manifest_sha256": backup.sha256_file(manifest_path),
        "database_dump_sha256": backup.sha256_file(dump),
        "backup_id": manifest["backup_id"],
        "evidence_file_sha256": [backup.sha256_file(evidence)],
        "table_check_version": 1, "table_checks": checks,
        "schema_migration_version": "001_init", "backup_age_seconds": 100,
        "evidence_files": 1, "verified_tables": 1,
        "rto_seconds": 30,
        "restore_started_at": "2026-01-01T00:01:10+00:00",
        "restore_completed_at": "2026-01-01T00:01:40+00:00",
        "snapshot_at": "2026-01-01T00:00:00+00:00",
    }
    _seal(receipt)
    receipt_path = tmp_path / "restore.json"
    _write_json(receipt_path, receipt)
    return receipt_path, manifest_path, dump, evidence, receipt


@pytest.fixture
def live_checks(bundle):
    manifest = json.loads(bundle[1].read_text(encoding="utf-8"))
    source = MagicMock()
    source.execute.return_value.fetchone.return_value = {
        "sha256": manifest["sha256"], "manifest": manifest, "restore_status": "passed",
        "rto_seconds": 30, "rpo_seconds": 100,
    }
    restored = MagicMock()
    def connection(url):
        return nullcontext(source if url == SOURCE else restored)

    with patch.object(backup, "connect", side_effect=connection), patch.object(
        backup, "table_checks", return_value=deepcopy(bundle[4]["table_checks"])
    ) as checks:
        yield checks


def _verify(path):
    return backup.verify_restore_receipt(SOURCE, TARGET, path)


def test_valid_receipt_rechecks_live_tables_and_supplies_m6_evidence(bundle, live_checks):
    verified = _verify(bundle[0])
    live_checks.assert_called_once()
    assert verified["receipt_file_sha256"] == backup.sha256_file(bundle[0])
    assert assess_restore_evidence(
        _config(), [], receipt_path=bundle[0], source_database_url=SOURCE,
        restore_database_url=TARGET,
    )["status"] == DONE
    assert live_checks.call_count == 2


@pytest.mark.parametrize("field,value", [
    ("status", "failed"), ("backup_age_seconds", 999999),
])
def test_receipt_tamper_is_rejected(bundle, live_checks, field, value):
    receipt = deepcopy(bundle[4])
    receipt[field] = value
    _write_json(bundle[0], receipt)
    with pytest.raises(RuntimeError, match="receipt hash mismatch"):
        _verify(bundle[0])
    live_checks.assert_not_called()


def test_manifest_tamper_is_rejected(bundle, live_checks):
    manifest = json.loads(bundle[1].read_text(encoding="utf-8"))
    manifest["backup_id"] = "other"
    _write_json(bundle[1], manifest)
    with pytest.raises(RuntimeError, match="manifest hash mismatch"):
        _verify(bundle[0])
    live_checks.assert_not_called()


@pytest.mark.parametrize("artifact", ["dump", "evidence"])
def test_artifact_tamper_is_rejected(bundle, live_checks, artifact):
    path = bundle[2] if artifact == "dump" else bundle[3]
    path.write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="hash mismatch|identity mismatch"):
        _verify(bundle[0])
    live_checks.assert_not_called()


@pytest.mark.parametrize('artifact', ['dump', 'evidence'])
def test_missing_restore_artifact_is_rejected(bundle, live_checks, artifact):
    path = bundle[2] if artifact == 'dump' else bundle[3]
    path.unlink()
    with pytest.raises(RuntimeError, match='missing|outside'):
        _verify(bundle[0])
    live_checks.assert_not_called()


def test_wrong_target_identity_is_rejected_even_with_valid_receipt_hash(bundle, live_checks):
    receipt = deepcopy(bundle[4])
    receipt["restore_target_identity"]["dbname"] = "wrong"
    _seal(receipt)
    _write_json(bundle[0], receipt)
    with pytest.raises(RuntimeError, match="database identity mismatch"):
        _verify(bundle[0])
    live_checks.assert_not_called()


def test_wrong_verifier_version_is_rejected_even_with_valid_receipt_hash(bundle, live_checks):
    receipt = deepcopy(bundle[4])
    receipt["verifier_version"] = "obsolete"
    _seal(receipt)
    _write_json(bundle[0], receipt)
    with pytest.raises(RuntimeError, match="not an accepted verifier result"):
        _verify(bundle[0])
    live_checks.assert_not_called()


def test_live_table_fingerprint_mismatch_is_rejected(bundle):
    changed = {"data_points": {"rows": 2, "fingerprint": "changed"}}
    with live_checks_context(bundle, changed):
        with pytest.raises(RuntimeError, match="table count or content hash differs"):
            _verify(bundle[0])


def live_checks_context(bundle, checks):
    manifest = json.loads(bundle[1].read_text(encoding="utf-8"))
    source = MagicMock()
    source.execute.return_value.fetchone.return_value = {
        "sha256": manifest["sha256"], "manifest": manifest, "restore_status": "passed",
        "rto_seconds": 30, "rpo_seconds": 100,
    }
    restored = MagicMock()
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch.object(backup, "connect", side_effect=lambda url: nullcontext(
        source if url == SOURCE else restored)))
    stack.enter_context(patch.object(backup, "table_checks", return_value=checks))
    return stack


def _config():
    return M6PreflightConfig(
        target_rpo_hours=1, target_rto_hours=1, minimum_real_sessions=1,
        minimum_real_events=1, restore_target=RestoreTarget("127.0.0.1", 5433, "value_agent_restore"),
        resource_limits={}, required_files=(), stage_status={}, authorization_required=(),
    )


@pytest.mark.parametrize("field", ["backup_age_seconds", "rto_seconds"])
def test_verified_receipt_exceeding_rpo_or_rto_is_partial(bundle, live_checks, field):
    verified = _verify(bundle[0])
    verified[field] = 3601
    with patch.object(backup, "verify_restore_receipt", return_value=verified) as verifier:
        result = assess_restore_evidence(
            _config(), [], receipt_path=bundle[0], source_database_url=SOURCE,
            restore_database_url=TARGET,
        )
    verifier.assert_called_once_with(SOURCE, TARGET, bundle[0])
    assert result["status"] == PARTIAL
    assert result["blockers"]


def test_m6_rejects_wrong_verified_target(bundle, live_checks):
    verified = _verify(bundle[0])
    verified["restore_target_identity"]["dbname"] = "other"
    with patch.object(backup, "verify_restore_receipt", return_value=verified):
        with pytest.raises(ValueError, match="wrong database"):
            assess_restore_evidence(
                _config(), [], receipt_path=bundle[0], source_database_url=SOURCE,
                restore_database_url=TARGET,
            )


def test_m6_path_requires_both_database_urls(bundle):
    with pytest.raises(ValueError, match="both database URLs"):
        assess_restore_evidence(_config(), [], receipt_path=bundle[0], source_database_url=SOURCE)


def test_build_preflight_receipt_uses_path_based_restore_verification(bundle, live_checks):
    config = _config()
    config = M6PreflightConfig(
        **{**config.__dict__, "stage_status": {key: DONE for key in ("m1", "m2", "m3", "m4", "m5")}}
    )
    with patch.object(m6, "load_config", return_value=config), patch.object(
        m6, "audit_repository", return_value={"status": DONE}
    ), patch.object(m6, "assess_session_ledger", return_value={"status": PARTIAL}):
        result = m6.build_preflight_receipt(
            bundle[0].parent, bundle[0], restore_receipt_path=bundle[0],
            source_database_url=SOURCE, restore_database_url=TARGET,
        )
    assert result["criteria"]["m6c4_real_restore_rpo_rto"]["status"] == DONE
    live_checks.assert_called_once()


def test_manual_restore_summary_cannot_reach_done():
    summary = {
        "action": "no_order", "observed": "actual", "status": "passed",
        "backup_id": "backup-1", "sha256": "a" * 64,
        "target": {"host": "127.0.0.1", "port": 5433, "database": "value_agent_restore"},
        "rpo_seconds": 100, "rto_seconds": 30,
        "table_check_count": 1, "evidence_files": 1,
        "verified_at": "2026-01-01T00:00:00Z",
    }
    result = assess_restore_evidence(_config(), [summary])
    assert result["status"] == PARTIAL
    assert any("not bound" in blocker for blocker in result["blockers"])


def test_restore_writes_content_addressed_receipt_and_reverifies_it(bundle, monkeypatch):
    _, manifest_path, _, _, _ = bundle
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = MagicMock()
    source.execute.return_value.fetchone.return_value = {
        "sha256": manifest["sha256"], "manifest": manifest,
        "restore_status": "passed", "rto_seconds": 0, "rpo_seconds": 0,
    }
    source.execute.return_value.rowcount = 1
    restored = MagicMock()
    monkeypatch.setattr(backup, "connect", lambda url: nullcontext(
        source if url == SOURCE else restored))
    monkeypatch.setattr(backup, "table_checks", lambda _: manifest["table_checks"])
    monkeypatch.setattr(backup.shutil, "which", lambda _: "/bin/pg_restore")
    monkeypatch.setattr(backup.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=0, stderr=""))
    result = backup.verify_restore(
        SOURCE, TARGET, manifest_path,
        attempt_started_at=datetime.now(timezone.utc) - timedelta(seconds=60))
    written_path = Path(result["receipt_path"])
    written = json.loads(written_path.read_text(encoding="utf-8"))
    assert written["receipt_sha256"] == result["receipt_sha256"]
    assert written["restore_command_result"] == "exit_0"
    assert written["table_checks"] == manifest["table_checks"]
    assert result['rto_seconds'] >= 60
    assert result['restore_duration_seconds'] < result['rto_seconds']
    assert written_path.name == f"restore-{result['receipt_sha256']}.json"
    source.execute.return_value.fetchone.return_value.update({
        'rto_seconds': result['rto_seconds'],
        'rpo_seconds': result['backup_age_seconds'],
    })
    assert backup.verify_restore_receipt(SOURCE, TARGET, written_path)['receipt_sha256'] == result['receipt_sha256']
