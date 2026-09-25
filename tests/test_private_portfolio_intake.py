from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import pytest

from value_investment_agent.portfolio_contracts import (
    CONFIRMATION_HUMAN,
    NAMESPACE_ACTUAL,
    QUANTITY_HUMAN_CONFIRMED,
    RECONCILIATION_RECONCILED,
    RISK_BALANCED,
    InvestorPolicyStatement,
    PortfolioHolding,
    PortfolioInputBundle,
    PortfolioSnapshot,
)
from value_investment_agent.private_portfolio_intake import (
    encrypt_private_portfolio_bundle,
    encrypt_private_portfolio_payload,
    load_private_portfolio_bundle,
)


def _bundle() -> PortfolioInputBundle:
    confirmed_at = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)
    policy = InvestorPolicyStatement(
        policy_id="synthetic-policy-v1",
        policy_version="v1",
        as_of=date(2026, 9, 24),
        confirmation_status=CONFIRMATION_HUMAN,
        confirmed_at=confirmed_at,
        account_scope="synthetic-private-account",
        investable_assets_cny=Decimal("100000"),
        minimum_cash_cny=Decimal("10000"),
        emergency_cash_cny=Decimal("10000"),
        liquidity_needs_cny=Decimal("5000"),
        time_horizon_years=Decimal("10"),
        max_single_security_pct=Decimal("15"),
        max_single_industry_pct=Decimal("30"),
        max_cyclical_exposure_pct=Decimal("25"),
        dividend_income_goal_cny=Decimal("3000"),
        risk_tolerance=RISK_BALANCED,
        concentration_allowed=False,
        tax_regime="synthetic",
        restrictions=("no_order",),
        evidence_refs=({"id": "synthetic-user-confirmation"},),
    )
    holding = PortfolioHolding(
        symbol="600519",
        exchange="SSE",
        quantity=Decimal("10"),
        cost_basis_cny=Decimal("15000"),
        market_value_cny=Decimal("16000"),
        quantity_source=QUANTITY_HUMAN_CONFIRMED,
        corporate_action_adjusted=True,
        evidence_refs=({"id": "synthetic-statement"},),
    )
    snapshot = PortfolioSnapshot(
        snapshot_id="synthetic-snapshot-v1",
        snapshot_version="v1",
        as_of=date(2026, 9, 24),
        available_at=confirmed_at,
        account_scope="synthetic-private-account",
        namespace=NAMESPACE_ACTUAL,
        cash_cny=Decimal("50000"),
        holdings=(holding,),
        reconciliation_status=RECONCILIATION_RECONCILED,
        reconciled_at=confirmed_at,
        evidence_refs=({"id": "synthetic-reconciliation"},),
    )
    return PortfolioInputBundle(policy=policy, snapshot=snapshot)


def _paths(tmp_path):
    repository = tmp_path / "repository"
    private_root = tmp_path / "private"
    key_path = tmp_path / "keys" / "portfolio.key"
    repository.mkdir()
    private_root.mkdir()
    key_path.parent.mkdir()
    key_path.write_text("a" * 64, encoding="ascii")
    return repository, private_root, key_path


@pytest.fixture
def private_tmp_path():
    """Use a disposable path outside the checkout for private-input tests."""
    base = Path.home() / ".codex" / "private-input-test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="value-investment-private-", dir=base) as directory:
        yield Path(directory)


def test_private_bundle_round_trip_returns_only_non_sensitive_receipt(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "inputs" / "portfolio-20260924.viportfolio"

    written = encrypt_private_portfolio_bundle(
        _bundle(), encrypted, key_path, private_root=private_root, repository_root=repository
    )
    loaded, receipt = load_private_portfolio_bundle(
        encrypted, key_path, private_root=private_root, repository_root=repository
    )

    assert loaded == _bundle()
    assert written == receipt
    assert receipt.action == "no_order"
    assert receipt.guidance_input_status == "PRIVATE_ACTUAL_HUMAN_CONFIRMED"
    assert "cash_cny" not in receipt.as_policy()
    assert "holdings" not in encrypted.read_text(encoding="utf-8")


def test_private_payload_is_validated_before_encryption(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "from-payload.viportfolio"
    receipt = encrypt_private_portfolio_payload(
        _bundle().as_policy(),
        encrypted,
        key_path,
        private_root=private_root,
        repository_root=repository,
    )

    loaded, _ = load_private_portfolio_bundle(
        encrypted, key_path, private_root=private_root, repository_root=repository
    )
    assert loaded == _bundle()
    assert receipt.action == "no_order"
    with pytest.raises(ValueError, match="payload must be an object"):
        encrypt_private_portfolio_payload(
            [], encrypted.with_name("bad.viportfolio"), key_path,
            private_root=private_root, repository_root=repository,
        )


def test_pending_actual_bundle_can_be_encrypted_but_cannot_support_guidance(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "pending.viportfolio"
    pending = replace(
        _bundle(),
        snapshot=replace(
            _bundle().snapshot,
            reconciliation_status="PENDING_RECONCILIATION",
            reconciled_at=None,
        ),
    )

    receipt = encrypt_private_portfolio_bundle(
        pending, encrypted, key_path,
        private_root=private_root, repository_root=repository,
    )
    loaded, verified = load_private_portfolio_bundle(
        encrypted, key_path,
        private_root=private_root, repository_root=repository,
    )

    assert receipt.guidance_input_status == "PRIVATE_ACTUAL_PENDING_REVIEW"
    assert verified == receipt
    assert loaded.can_support_guidance() is False
    assert "snapshot.reconciliation" in loaded.missing_guidance_inputs()


def test_private_input_rejects_repo_sync_roots_and_key_colocation(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    with pytest.raises(ValueError, match="separate from the repository"):
        encrypt_private_portfolio_bundle(
            _bundle(), repository / "portfolio.viportfolio", key_path,
            private_root=repository, repository_root=repository,
        )
    repository_key = repository / "portfolio.key"
    repository_key.write_text("a" * 64, encoding="ascii")
    with pytest.raises(ValueError, match="outside the repository"):
        encrypt_private_portfolio_bundle(
            _bundle(), private_root / "portfolio.viportfolio", repository_key,
            private_root=private_root, repository_root=repository,
        )
    with pytest.raises(ValueError, match="sync root"):
        encrypt_private_portfolio_bundle(
            _bundle(), private_root / "portfolio.viportfolio", key_path,
            private_root=private_root, repository_root=repository,
            forbidden_sync_roots=(private_tmp_path,),
        )
    wps_root = private_tmp_path / "WPSDrive" / "private"
    wps_root.mkdir(parents=True)
    with pytest.raises(ValueError, match="WPSDrive"):
        encrypt_private_portfolio_bundle(
            _bundle(), wps_root / "portfolio.viportfolio", key_path,
            private_root=wps_root, repository_root=repository,
        )
    with pytest.raises(ValueError, match="outside private_root"):
        encrypt_private_portfolio_bundle(
            _bundle(), private_root / "portfolio.viportfolio", private_root / "key",
            private_root=private_root, repository_root=repository,
        )


def test_private_input_detects_tampering_wrong_key_and_overwrite(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "portfolio.viportfolio"
    encrypt_private_portfolio_bundle(
        _bundle(), encrypted, key_path, private_root=private_root, repository_root=repository
    )
    with pytest.raises(FileExistsError):
        encrypt_private_portfolio_bundle(
            _bundle(), encrypted, key_path, private_root=private_root, repository_root=repository
        )
    wrong_key = private_tmp_path / "keys" / "wrong.key"
    wrong_key.write_text("b" * 64, encoding="ascii")
    with pytest.raises(ValueError, match="invalid or authentication failed"):
        load_private_portfolio_bundle(
            encrypted, wrong_key, private_root=private_root, repository_root=repository
        )
    envelope = json.loads(encrypted.read_text(encoding="utf-8"))
    envelope["ciphertext"] = envelope["ciphertext"][:-4] + "AAAA"
    encrypted.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid or authentication failed"):
        load_private_portfolio_bundle(
            encrypted, key_path, private_root=private_root, repository_root=repository
        )


def test_private_input_cli_rejects_private_root_inside_repository(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "portfolio.viportfolio"
    encrypt_private_portfolio_bundle(
        _bundle(), encrypted, key_path, private_root=private_root, repository_root=repository
    )
    # This models a private folder accidentally created inside a Git worktree.
    # The verifier must detect the actual marker on every platform.
    (private_root / ".git").mkdir()
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_private_portfolio_input.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--encrypted",
            str(encrypted),
            "--key-file",
            str(key_path),
            "--private-root",
            str(private_root),
        ],
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "private_root must be separate from every git repository" in completed.stderr
    assert "cash_cny" not in completed.stderr
    assert "holdings" not in completed.stderr


def test_private_input_rejects_linked_worktree_git_file(private_tmp_path):
    repository, private_root, key_path = _paths(private_tmp_path)
    encrypted = private_root / "portfolio.viportfolio"
    encrypt_private_portfolio_bundle(
        _bundle(), encrypted, key_path, private_root=private_root, repository_root=repository
    )
    (private_root / ".git").write_text("gitdir: /private/worktree", encoding="utf-8")

    with pytest.raises(ValueError, match="separate from every git repository"):
        load_private_portfolio_bundle(
            encrypted, key_path, private_root=private_root, repository_root=repository
        )
