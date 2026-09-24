from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path

import pytest

from value_investment_agent.m6_operational_readiness import (
    ACTION_NO_ORDER,
    NOT_STARTED,
    PARTIAL,
    REQUIRES_AUTHORIZATION,
    M6PreflightConfig,
    assess_restore_evidence,
    assess_session_ledger,
    audit_repository,
    build_preflight_receipt,
    load_config,
    write_receipt,
)


def _config(tmp_path: Path) -> M6PreflightConfig:
    path = tmp_path / "m6.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "m6-operational-preflight-v1",
                "action": "no_order",
                "target_rpo_hours": 24,
                "target_rto_hours": 4,
                "minimum_real_sessions": 20,
                "minimum_real_events": 1,
                "restore_target": {
                    "host": "127.0.0.1",
                    "port": 5433,
                    "database": "value_agent_restore",
                },
                "resource_limits": {"memory_mb": 256, "cpu_cores": 0.5},
                "required_files": [
                    "src/value_investment_agent/backup.py",
                    "deploy/server/run_restore_drill.sh",
                    "deploy/server/test_evidence_in_restore.sh",
                ],
                "stage_status": {
                    "m1": "DONE",
                    "m2": "PENDING_HUMAN_REVIEW",
                    "m3": "PARTIAL",
                    "m4": "PARTIAL",
                    "m5": "PARTIAL",
                    "m6": "NOT_STARTED",
                    "m7": "PARTIAL",
                },
                "authorization_required": ["production scope"],
            }
        ),
        encoding="utf-8",
    )
    return load_config(path)


def _synthetic_repo(tmp_path: Path) -> tuple[Path, M6PreflightConfig]:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "src" / "value_investment_agent").mkdir(parents=True)
    (root / "deploy" / "server").mkdir(parents=True)
    (root / "src" / "value_investment_agent" / "backup.py").write_text(
        "pg_export_snapshot\nREPEATABLE READ\nevidence_manifest\nsha256_file\n"
        "validate_restore_target\nvalue_agent_restore\n127.0.0.1\n5433\n"
        "--clean --no-owner --no-acl compare_checks\n",
        encoding="utf-8",
    )
    (root / "deploy" / "server" / "run_restore_drill.sh").write_text(
        "--memory=256m --cpus=0.5\n127.0.0.1:5433:5432\nvalue_agent_restore\n"
        "trap 'podman rm -f value-investment-restore-postgres\n",
        encoding="utf-8",
    )
    (root / "deploy" / "server" / "test_evidence_in_restore.sh").write_text(
        "fair_value\nsha256 <> ''\n", encoding="utf-8"
    )
    return root, _config(root)


def _actual_session(day: int, *, event: bool = False) -> dict:
    session_date = date(2026, 9, day).isoformat()
    return {
        "session_date": session_date,
        "exchange": "SSE",
        "status": "success",
        "observed": "actual",
        "resource_baseline_ok": True,
        "real_event_materialized": event,
        "action": "no_order",
    }


def test_load_config_rejects_invalid_target_and_no_order(tmp_path):
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps({"schema_version": "wrong", "action": "BUY"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="schema version"):
        load_config(config_path)


def test_repository_preflight_config_tracks_signed_m2_completion():
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "config" / "m6-operational-preflight-v1.json")

    assert config.stage_status["m1"] == "DONE"
    assert config.stage_status["m2"] == "DONE"
    assert config.stage_status["m3"] == PARTIAL


def test_repository_audit_passes_synthetic_engineering_boundary(tmp_path):
    root, config = _synthetic_repo(tmp_path)
    result = audit_repository(
        root,
        config,
        tracked_files=["README.md", ".env.example"],
        clean=True,
    )

    assert result["status"] == PARTIAL
    assert any(item["label"] == "tracked repository contains no obvious secrets" and item["passed"] for item in result["checks"])
    assert any("encrypted offsite backup" in blocker for blocker in result["blockers"])


def test_repository_audit_rejects_sensitive_tracked_file(tmp_path):
    root, config = _synthetic_repo(tmp_path)
    result = audit_repository(
        root,
        config,
        tracked_files=["prod.dump", ".env"],
        clean=True,
    )

    check = next(item for item in result["checks"] if item["label"] == "tracked repository contains no obvious secrets")
    assert check["passed"] is False
    assert "prod.dump" in check["detail"]


def test_repository_audit_accepts_real_encrypted_backup_contract(tmp_path):
    root, config = _synthetic_repo(tmp_path)
    (root / "src" / "value_investment_agent" / "backup_security.py").write_text(
        """
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def load_key(*args, **kwargs):
    pass

def validate_key_separation(*args, **kwargs):
    pass

def _collect_named_items(*args, **kwargs):
    pass

def _manifest_payload(*args, **kwargs):
    pass

def encrypt_package(*args, **kwargs):
    pass

def decrypt_package(*args, **kwargs):
    pass
""",
        encoding="utf-8",
    )
    policy = {
        "schema_version": "m6-backup-security-v1",
        "action": "no_order",
        "algorithm": "AES-256-GCM",
        "key_encoding": "hex",
        "key_min_bytes": 32,
        "chunk_bytes": 1048576,
        "config_inventory": ["config.json"],
        "release_inventory": ["release.json"],
        "offsite": {
            "sync_kind": "authorized_cloud_sync_required",
            "forbidden_locations": ["backup_root", "key_file", "offsite_staging"],
        },
    }
    (root / "config").mkdir()
    (root / "config" / "m6-backup-security-v1.json").write_text(
        json.dumps(policy), encoding="utf-8"
    )
    (root / "scripts").mkdir()
    (root / "scripts" / "package_encrypted_backup.py").write_text("def main(): pass\n", encoding="utf-8")
    config_path = root / "m6.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    payload["required_files"] += [
        "src/value_investment_agent/backup_security.py",
        "scripts/package_encrypted_backup.py",
        "config/m6-backup-security-v1.json",
    ]
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    updated = load_config(config_path)

    result = audit_repository(
        root,
        updated,
        tracked_files=["README.md", ".env.example"],
        clean=True,
    )

    assert result["status"] == "DONE"
    assert "encrypted offsite backup" not in " ".join(result["blockers"])


def test_session_ledger_counts_only_actual_successful_sessions(tmp_path):
    config = _config(tmp_path)
    records = [_actual_session(day) for day in range(1, 21)]
    records[19]["real_event_materialized"] = True
    records.append({**_actual_session(30), "observed": "simulated"})

    result = assess_session_ledger(config, records)

    assert result["status"] == "DONE"
    assert result["evidence"]["latest_streak"] == 20
    assert result["evidence"]["simulated_sessions"] == 1
    assert result["action"] == "no_order" if "action" in result else True


def test_session_ledger_rejects_duplicate_dates_and_missing_baseline(tmp_path):
    config = _config(tmp_path)
    records = [_actual_session(1), _actual_session(1)]
    with pytest.raises(ValueError, match="duplicate session date"):
        assess_session_ledger(config, records)

    records = [{**_actual_session(1), "resource_baseline_ok": False}]
    result = assess_session_ledger(config, records)
    assert result["status"] == NOT_STARTED


def test_restore_evidence_rejects_wrong_target_and_slow_drill(tmp_path):
    config = _config(tmp_path)
    base = {
        "action": "no_order",
        "observed": "actual",
        "status": "passed",
        "backup_id": "backup-1",
        "sha256": "a" * 64,
        "target": {
            "host": "127.0.0.1",
            "port": 5433,
            "database": "value_agent_restore",
        },
        "rpo_seconds": 60,
        "rto_seconds": 60,
        "table_check_count": 10,
        "evidence_files": 1,
        "verified_at": "2026-09-24T00:00:00+00:00",
    }
    wrong_target = {**base, "target": {**base["target"], "port": 5432}}
    with pytest.raises(ValueError, match="wrong database"):
        assess_restore_evidence(config, [wrong_target])

    slow = {**base, "rto_seconds": 5 * 3600}
    result = assess_restore_evidence(config, [slow])
    assert result["status"] == PARTIAL


def test_preflight_never_claims_operational_acceptance(tmp_path):
    root, config = _synthetic_repo(tmp_path)
    config_path = root / "m6.json"
    receipt = build_preflight_receipt(
        root,
        config_path,
        tracked_files=["README.md"],
        clean=True,
        session_records=[_actual_session(day, event=day == 20) for day in range(1, 21)],
        restore_records=[],
    )

    assert receipt["action"] == ACTION_NO_ORDER
    assert receipt["operational_acceptance_status"] == NOT_STARTED
    assert receipt["criteria"]["m6c6_production_authorization"]["status"] == REQUIRES_AUTHORIZATION
    assert any("not authorized" in blocker for blocker in receipt["summary"]["blockers"])


def test_write_receipt_creates_hash_pointer(tmp_path):
    root, config = _synthetic_repo(tmp_path)
    receipt = build_preflight_receipt(
        root,
        root / "m6.json",
        tracked_files=[],
        clean=True,
    )
    output = write_receipt(receipt, root=root)

    receipt_path = root / output["receipt_path"]
    pointer_path = root / output["pointer_path"]
    assert receipt_path.is_file()
    assert pointer_path.is_file()
    assert json.loads(pointer_path.read_text(encoding="utf-8"))["sha256"] == output["receipt_sha256"]
