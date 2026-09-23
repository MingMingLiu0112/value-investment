from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import uuid

import pytest

from value_investment_agent.m1_postgres_cold_replay import (
    LOOPBACK_HOST,
    PostgresBinaryUnavailable,
    PostgresClusterManager,
    resolve_postgres_bin_dir,
    run_m1_postgres_cold_replay,
)


ROOT = Path(__file__).resolve().parents[1]

try:
    BIN_DIR = resolve_postgres_bin_dir()
except PostgresBinaryUnavailable:
    pytest.skip(
        "postgresql-binaries is not installed in this test environment",
        allow_module_level=True,
    )


def test_cluster_manager_uses_loopback_only(tmp_path: Path) -> None:
    manager = PostgresClusterManager(
        bin_dir=BIN_DIR,
        data_dir=tmp_path / "data",
        log_path=tmp_path / "postgres.log",
        port=55439,
    )
    assert LOOPBACK_HOST in manager.dsn
    assert f"@{LOOPBACK_HOST}:" in manager.dsn
    assert "47.100.97.88" not in manager.dsn


def test_m1_postgres_cold_replay_semantic_equality() -> None:
    work_dir = ROOT / "runtime" / f"m1-postgres-cold-replay-test-{uuid.uuid4().hex}"
    try:
        receipt = run_m1_postgres_cold_replay(
            root=ROOT,
            work_dir=work_dir,
            postgres_bin_dir=BIN_DIR,
            keep_data=False,
        )
        assert receipt["status"] == "PASSED"
        assert receipt["action"] == "no_order"
        assert receipt["host"] == LOOPBACK_HOST
        assert receipt["first_run"]["artifact_count"] >= 20
        assert receipt["cold_restart"]["semantic_equality"] is True
        assert (
            receipt["cold_restart"]["verified_artifact_count"]
            == receipt["first_run"]["artifact_count"]
        )
        assert {
            item["symbol"] for item in receipt["first_run"]["outcomes"]
        } == {"000651", "600741", "600887"}
        assert all(
            item["action"] in (None, "no_order")
            for item in receipt["first_run"]["outcomes"]
        )

        receipt_path = ROOT / receipt["receipt_path"]
        manifest_path = ROOT / receipt["manifest_path"]
        assert hashlib.sha256(receipt_path.read_bytes()).hexdigest() == receipt[
            "receipt_sha256"
        ]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "PASSED"
        assert manifest["receipt_sha256"] == receipt["receipt_sha256"]
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
