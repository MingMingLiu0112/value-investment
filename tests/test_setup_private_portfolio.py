from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "setup_private_portfolio.py"


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(item) for item in arguments)],
        cwd=ROOT, capture_output=True, text=True,
    )


def test_private_setup_creates_and_validates_redacted_draft():
    base = Path.home() / ".codex" / "private-input-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m4-package-", dir=base) as directory:
        private_root = Path(directory) / "private"
        private_root.mkdir()
        draft = private_root / "portfolio-input.json"

        initialized = _run("init", "--output", draft, "--private-root", private_root)
        validated = _run("validate", "--input", draft, "--private-root", private_root)

        assert initialized.returncode == 0, initialized.stderr
        assert json.loads(initialized.stdout)["status"] == "DRAFT_CREATED"
        result = json.loads(validated.stdout)
        assert result["status"] == "NEEDS_INPUT"
        assert "policy.investable_assets_cny" in result["blockers"]
        assert "holdings" not in validated.stdout
        assert "600519" not in validated.stdout


def test_private_setup_keygen_rejects_private_root_and_overwrite():
    base = Path.home() / ".codex" / "private-input-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m4-key-", dir=base) as directory:
        root = Path(directory)
        private_root = root / "private"
        private_root.mkdir()
        bad = _run("keygen", "--key-file", private_root / "key", "--private-root", private_root)
        key = root / "keys" / "portfolio.key"
        good = _run("keygen", "--key-file", key, "--private-root", private_root)
        overwrite = _run("keygen", "--key-file", key, "--private-root", private_root)

        assert bad.returncode != 0
        assert good.returncode == 0, good.stderr
        assert len(key.read_text(encoding="utf-8").strip()) == 64
        assert overwrite.returncode != 0


def test_private_setup_synthetic_encrypted_reconciliation_lifecycle():
    base = Path.home() / ".codex" / "private-input-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m4-e2e-", dir=base) as directory:
        root = Path(directory)
        private_root = root / "private"
        private_root.mkdir()
        key = root / "keys" / "portfolio.key"
        assert _run("keygen", "--key-file", key, "--private-root", private_root).returncode == 0

        payload = json.loads((ROOT / "config/m4-private-portfolio-synthetic-example.json").read_text(encoding="utf-8"))
        payload["snapshot"]["namespace"] = "ACTUAL"
        payload["snapshot"]["reconciliation_status"] = "PENDING_RECONCILIATION"
        payload["snapshot"]["reconciled_at"] = None
        reported_json = private_root / "reported.json"
        confirmed_json = private_root / "confirmed.json"
        reported_json.write_text(json.dumps(payload), encoding="utf-8")
        confirmed_json.write_text(json.dumps(payload), encoding="utf-8")
        reported = private_root / "reported.viportfolio"
        confirmed = private_root / "confirmed.viportfolio"
        final = private_root / "final.viportfolio"
        report = private_root / "reconciliation.json"

        for source, encrypted in ((reported_json, reported), (confirmed_json, confirmed)):
            result = _run(
                "encrypt", "--input", source, "--encrypted", encrypted,
                "--key-file", key, "--private-root", private_root,
            )
            assert result.returncode == 0, result.stderr
            assert json.loads(result.stdout)["guidance_input_status"] == "PRIVATE_ACTUAL_PENDING_REVIEW"
        reconciled = _run(
            "reconcile", "--reported", reported, "--confirmed", confirmed,
            "--private-report", report, "--report-id", "synthetic-report-v1",
            "--key-file", key, "--private-root", private_root,
        )
        assert reconciled.returncode == 0, reconciled.stderr
        assert json.loads(reconciled.stdout)["status"] == "MATCH_PENDING_HUMAN_CONFIRMATION"
        completed = _run(
            "confirm-reconciliation", "--source", reported, "--private-report", report,
            "--encrypted", final, "--confirmation-id", "synthetic-human-confirmation",
            "--confirmed-at", "2026-09-25T10:00:00+08:00",
            "--key-file", key, "--private-root", private_root,
        )
        assert completed.returncode == 0, completed.stderr
        assert json.loads(completed.stdout)["guidance_input_status"] == "PRIVATE_ACTUAL_HUMAN_CONFIRMED"
        verified = _run(
            "verify", "--encrypted", final, "--key-file", key,
            "--private-root", private_root,
        )
        assert verified.returncode == 0, verified.stderr
        assert json.loads(verified.stdout)["blockers"] == []
