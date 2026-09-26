from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from value_investment_agent.domain.portfolio.confirmation_receipt import (
    USER_CONFIRMED_RECONCILIATION,
    build_portfolio_confirmation_receipt,
    portfolio_confirmation_receipt_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = ROOT / "scripts" / "setup_private_portfolio.py"


def _run(*arguments: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SETUP_SCRIPT), *(str(item) for item in arguments)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def _report_payload() -> dict[str, object]:
    return {
        "schema_version": "m4-portfolio-reconciliation-v1",
        "report_id": "synthetic-report-v1",
        "generated_at": "2026-09-25T09:00:00+08:00",
        "reported_snapshot_id": "synthetic-reported-v1",
        "confirmed_snapshot_id": "synthetic-confirmed-v1",
        "account_scope": "SYNTHETIC_ACCOUNT_SCOPE",
        "as_of": "2026-09-25",
        "status": "MATCH_PENDING_HUMAN_CONFIRMATION",
        "differences": [],
        "requires_human_confirmation": True,
        "sensitivity": "PRIVATE_USER_CONFIRMED",
        "action": "no_order",
    }


def _receipt():
    report = _report_payload()
    report_bytes = (json.dumps(report, sort_keys=True) + "\n").encode("utf-8")
    return report_bytes, build_portfolio_confirmation_receipt(
        reconciliation_bytes=report_bytes,
        reconciliation_payload=report,
        user_confirmation=USER_CONFIRMED_RECONCILIATION,
        confirmed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        confirmation_id="synthetic-human-confirmation",
    )


def test_receipt_is_byte_bound_and_public_fingerprint_excludes_private_fields():
    report_bytes, receipt = _receipt()

    assert receipt.reconciliation_sha256 == hashlib.sha256(report_bytes).hexdigest()
    assert receipt.receipt_sha256 == hashlib.sha256(receipt.canonical_bytes()).hexdigest()
    assert receipt.account_scope == "SYNTHETIC_ACCOUNT_SCOPE"
    assert receipt.snapshot_date.isoformat() == "2026-09-25"
    assert receipt.user_confirmation == USER_CONFIRMED_RECONCILIATION
    assert receipt.as_private_policy() == portfolio_confirmation_receipt_from_payload(
        receipt.as_private_policy()
    ).as_private_policy()

    fingerprint = receipt.as_public_fingerprint()
    assert set(fingerprint) == {
        "schema_version",
        "action",
        "receipt_schema_version",
        "receipt_sha256",
        "sensitivity",
        "authentication_basis",
        "acceptance_authority",
    }
    assert fingerprint["receipt_sha256"] == receipt.receipt_sha256
    assert fingerprint["sensitivity"] == "PUBLIC_FINGERPRINT_ONLY"
    assert fingerprint["authentication_basis"] == "UNSIGNED_HUMAN_ASSERTION"
    assert fingerprint["acceptance_authority"] == "NONE"
    assert fingerprint["action"] == "no_order"
    assert {
        "reconciliation_sha256",
        "account_scope",
        "snapshot_date",
        "user_confirmation",
        "confirmed_at",
        "confirmation_id",
    }.isdisjoint(fingerprint)


def test_byte_change_changes_reconciliation_and_receipt_hashes():
    report = _report_payload()
    compact = json.dumps(report, sort_keys=True, separators=(",", ":")).encode("utf-8")
    pretty = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode("utf-8")
    first = build_portfolio_confirmation_receipt(
        reconciliation_bytes=compact,
        reconciliation_payload=report,
        user_confirmation=USER_CONFIRMED_RECONCILIATION,
        confirmed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        confirmation_id="synthetic-human-confirmation",
    )
    second = build_portfolio_confirmation_receipt(
        reconciliation_bytes=pretty,
        reconciliation_payload=report,
        user_confirmation=USER_CONFIRMED_RECONCILIATION,
        confirmed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
        confirmation_id="synthetic-human-confirmation",
    )

    assert first.reconciliation_sha256 != second.reconciliation_sha256
    assert first.receipt_sha256 != second.receipt_sha256


def test_receipt_fails_closed_without_match_explicit_confirmation_or_valid_hash():
    report = _report_payload()
    report_bytes = b"{\"report\":\"synthetic\"}\n"
    with pytest.raises(ValueError, match="matching reconciliation"):
        build_portfolio_confirmation_receipt(
            reconciliation_bytes=report_bytes,
            reconciliation_payload={**report, "status": "MISMATCH"},
            user_confirmation=USER_CONFIRMED_RECONCILIATION,
            confirmed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
            confirmation_id="synthetic-human-confirmation",
        )
    with pytest.raises(ValueError, match="explicitly confirm"):
        build_portfolio_confirmation_receipt(
            reconciliation_bytes=report_bytes,
            reconciliation_payload=report,
            user_confirmation="NO",
            confirmed_at=datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc),
            confirmation_id="synthetic-human-confirmation",
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        build_portfolio_confirmation_receipt(
            reconciliation_bytes=report_bytes,
            reconciliation_payload=report,
            user_confirmation=USER_CONFIRMED_RECONCILIATION,
            confirmed_at=datetime(2026, 9, 25, 10, 0),
            confirmation_id="synthetic-human-confirmation",
        )
    _, receipt = _receipt()
    with pytest.raises(ValueError, match="hash mismatch"):
        replace(receipt, receipt_sha256="0" * 64)


def test_private_confirmation_cli_writes_a_replayable_private_receipt():
    base = Path.home() / ".codex" / "private-input-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="m4-receipt-", dir=base) as directory:
        root = Path(directory)
        private_root = root / "private"
        private_root.mkdir()
        key = root / "keys" / "portfolio.key"
        assert _run("keygen", "--key-file", key, "--private-root", private_root).returncode == 0

        payload = json.loads(
            (ROOT / "config" / "m4-private-portfolio-synthetic-example.json").read_text(
                encoding="utf-8"
            )
        )
        payload["snapshot"]["namespace"] = "ACTUAL"
        payload["snapshot"]["reconciliation_status"] = "PENDING_RECONCILIATION"
        payload["snapshot"]["reconciled_at"] = None
        source = private_root / "reported.json"
        source.write_text(json.dumps(payload), encoding="utf-8")
        encrypted = private_root / "reported.viportfolio"
        confirmed = private_root / "confirmed.viportfolio"
        report = private_root / "reconciliation.json"
        final = private_root / "final.viportfolio"
        receipt_path = private_root / "confirmation.json"

        assert _run(
            "encrypt", "--input", source, "--encrypted", encrypted,
            "--key-file", key, "--private-root", private_root,
        ).returncode == 0
        assert _run(
            "encrypt", "--input", source, "--encrypted", confirmed,
            "--key-file", key, "--private-root", private_root,
        ).returncode == 0
        assert _run(
            "reconcile", "--reported", encrypted, "--confirmed", confirmed,
            "--private-report", report, "--report-id", "synthetic-report-v1",
            "--key-file", key, "--private-root", private_root,
        ).returncode == 0
        original_report = report.read_bytes()
        mismatched_report = json.loads(original_report)
        mismatched_report["report"]["account_scope"] = "OTHER_ACCOUNT_SCOPE"
        report.write_text(json.dumps(mismatched_report), encoding="utf-8")
        mismatch = _run(
            "confirm-reconciliation", "--source", encrypted,
            "--private-report", report, "--encrypted", private_root / "blocked.viportfolio",
            "--confirmation-id", "synthetic-human-confirmation",
            "--confirmed-at", "2026-09-25T10:00:00+08:00",
            "--key-file", key, "--private-root", private_root,
        )
        assert mismatch.returncode != 0
        assert "account scope" in mismatch.stderr
        report.write_bytes(original_report)
        completed = _run(
            "confirm-reconciliation", "--source", encrypted,
            "--private-report", report, "--encrypted", final,
            "--confirmation-id", "synthetic-human-confirmation",
            "--confirmed-at", "2026-09-25T10:00:00+08:00",
            "--confirmation-receipt", receipt_path,
            "--key-file", key, "--private-root", private_root,
        )

        assert completed.returncode == 0, completed.stderr
        private_receipt = portfolio_confirmation_receipt_from_payload(
            json.loads(receipt_path.read_text(encoding="utf-8"))
        )
        assert private_receipt.reconciliation_sha256 == hashlib.sha256(
            report.read_bytes()
        ).hexdigest()
        assert private_receipt.receipt_sha256 in completed.stdout
        assert private_receipt.account_scope not in completed.stdout
