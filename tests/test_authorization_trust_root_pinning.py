"""Fail-closed trust-root pinning for M5 ACTUAL and M6 operational control.

A signature is not authorization.  These tests prove that a validly signed
authorization whose trust root is absent from the pinned registry is rejected,
and that a later unpinning invalidates previously issued capabilities on read.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from authorization_trust_registry_fixture import (
    pin_test_trust_root,
    pinned_test_registry_fingerprints,
)
from m5_actual_authorization_fixture import REVIEWED_AT, synthetic_actual_receipt
from value_investment_agent.m6_operational_control import (
    MODE_STAGING,
    OperationalAuthorizationProof,
)
from value_investment_agent.m6_shadow_receipts import (
    verify_shadow_authorization_for_control,
)
from value_investment_agent.operations.authorization.m5_actual_approval_receipt import (
    verify_m5_actual_approval_receipt,
)
from value_investment_agent.operations.authorization.trust_root_registry import (
    TRUST_REGISTRY_ENV,
    TRUST_REGISTRY_VERSION,
    TrustRootNotPinnedError,
    trust_root_fingerprint,
)


def _empty_registry(tmp_path: Path) -> Path:
    path = tmp_path / "empty-trust-roots.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": TRUST_REGISTRY_VERSION,
                "note": "deliberately empty for negative testing",
                "pinned_trust_root_sha256": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def _m6_staging_bundle() -> tuple[dict, dict]:
    from test_m6_shadow_receipts import _fixture

    candidate, trust_root, _, _, _, _ = _fixture(
        target_mode=MODE_STAGING,
        operator_id="operator",
        authorization_id="auth-staging-unpinned",
    )
    bundle = {
        "authorization": candidate["authorization"],
        "authorization_artifacts": candidate["authorization_artifacts"],
    }
    root = {
        "authorization_public_key": trust_root["authorization_public_key"],
        "approved_authorization_sha256": trust_root["approved_authorization_sha256"],
    }
    return bundle, root


def test_m5_actual_receipt_is_rejected_when_its_trust_root_is_not_pinned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = synthetic_actual_receipt()
    monkeypatch.setenv(TRUST_REGISTRY_ENV, str(_empty_registry(tmp_path)))

    with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
        verify_m5_actual_approval_receipt(
            fixture["bundle"],
            fixture["trust_root"],
            expected_subject=fixture["subject"],
            at=REVIEWED_AT,
        )


def test_m5_actual_receipt_verifies_only_while_the_root_stays_pinned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = synthetic_actual_receipt()
    assert trust_root_fingerprint(fixture["trust_root"]) in pinned_test_registry_fingerprints()
    capability = verify_m5_actual_approval_receipt(
        fixture["bundle"],
        fixture["trust_root"],
        expected_subject=fixture["subject"],
        at=REVIEWED_AT,
    )
    assert capability.action == "no_order"

    monkeypatch.setenv(TRUST_REGISTRY_ENV, str(_empty_registry(tmp_path)))
    with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
        capability.verify()


def test_m6_fresh_keypair_cannot_advance_an_operational_mode() -> None:
    bundle, root = _m6_staging_bundle()
    assert trust_root_fingerprint(root) not in pinned_test_registry_fingerprints()

    with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
        verify_shadow_authorization_for_control(
            bundle,
            root,
            target_mode=MODE_STAGING,
            operator_id="operator",
            at=datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc),
        )


def test_m6_operational_proof_fails_every_read_after_unpinning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from test_m6_operational_control import _proof

    proof = _proof(MODE_STAGING)
    payload = proof.as_dict(at=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc))
    pin_test_trust_root(proof.trust_root)

    monkeypatch.setenv(TRUST_REGISTRY_ENV, str(_empty_registry(tmp_path)))
    with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
        OperationalAuthorizationProof.from_dict(
            payload,
            at=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc),
        )
