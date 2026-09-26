"""Fail-closed trust-root pinning for M5 ACTUAL and M6 operational control.

A signature is not authorization.  These tests prove that a validly signed
authorization whose trust root is absent from the pinned registry is rejected,
and that a later unpinning invalidates previously issued capabilities on read.
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from authorization_trust_registry_fixture import (
    pin_test_trust_root,
    pinned_test_registry_fingerprints,
    use_test_trust_registry,
)
from m5_actual_authorization_fixture import REVIEWED_AT, synthetic_actual_receipt
from value_investment_agent.m6_operational_control import (
    MODE_STAGING,
    OperationalAuthorizationProof,
)
from value_investment_agent.m6_shadow_receipts import (
    _verify_shadow_bundle_contents,
    verify_shadow_bundle,
    verify_shadow_authorization_for_control,
)
from value_investment_agent.m6_shadow_admission import (
    verify_operational_shadow_bundle,
)
from value_investment_agent.operations.authorization.m5_actual_approval_receipt import (
    verify_m5_actual_approval_receipt,
)
from value_investment_agent.operations.authorization.trust_root_registry import (
    DEFAULT_TRUST_REGISTRY_PATH,
    TRUST_REGISTRY_VERSION,
    TrustRootNotPinnedError,
    _set_test_trust_registry,
    pinned_trust_root_fingerprints,
    trust_registry_path,
    trust_root_fingerprint,
)


def _empty_registry() -> Path:
    path = Path(tempfile.mkdtemp(prefix="via-empty-trust-registry-")) / "empty-trust-roots.json"
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


def test_m5_actual_receipt_is_rejected_when_its_trust_root_is_not_pinned() -> None:
    fixture = synthetic_actual_receipt()
    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            verify_m5_actual_approval_receipt(
                fixture["bundle"],
                fixture["trust_root"],
                expected_subject=fixture["subject"],
                at=REVIEWED_AT,
            )


def test_m5_actual_receipt_verifies_only_while_the_root_stays_pinned() -> None:
    fixture = synthetic_actual_receipt()
    assert trust_root_fingerprint(fixture["trust_root"]) in pinned_test_registry_fingerprints()
    capability = verify_m5_actual_approval_receipt(
        fixture["bundle"],
        fixture["trust_root"],
        expected_subject=fixture["subject"],
        at=REVIEWED_AT,
    )
    assert capability.action == "no_order"

    with use_test_trust_registry(_empty_registry()):
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


def test_m6_operational_proof_fails_every_read_after_unpinning() -> None:
    from test_m6_operational_control import _proof

    proof = _proof(MODE_STAGING)
    payload = proof.as_dict(at=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc))
    pin_test_trust_root(proof.trust_root)

    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            OperationalAuthorizationProof.from_dict(
                payload,
                at=datetime(2026, 9, 24, 9, 30, tzinfo=timezone.utc),
            )


def test_m6_self_consistent_shadow_bundle_is_rejected_when_root_is_unpinned() -> None:
    from test_m6_shadow_receipts import _fixture

    bundle, trust_root, calendar, schedule, _, _ = _fixture()
    cutoff = datetime.fromisoformat(str(calendar["observation_cutoff"]))
    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            verify_shadow_bundle(bundle, trust_root, schedule, cutoff)


def test_m6_self_consistent_operational_admission_is_rejected_when_unpinned() -> None:
    from test_m6_shadow_admission import _admitted

    bundle, root, schedule, cutoff, _ = _admitted()
    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            verify_operational_shadow_bundle(
                bundle,
                root,
                schedule,
                cutoff,
                required_sessions=2,
                required_events=1,
            )


def test_m6_operational_admission_accepts_candidate_root_bound_to_pinned_outer_root(
) -> None:
    from test_m6_shadow_admission import _admitted

    bundle, root, schedule, cutoff, _ = _admitted()
    registry = _empty_registry()
    registry.write_text(
        json.dumps(
            {
                "schema_version": TRUST_REGISTRY_VERSION,
                "pinned_trust_root_sha256": [trust_root_fingerprint(root)],
            }
        ),
        encoding="utf-8",
    )
    with use_test_trust_registry(registry):
        candidate_fingerprint = trust_root_fingerprint(root["candidate_trust_root"])
        assert candidate_fingerprint not in pinned_trust_root_fingerprints()

        verified = verify_operational_shadow_bundle(
            bundle,
            root,
            schedule,
            cutoff,
            required_sessions=2,
            required_events=1,
        )
        assert len(verified) == 2


def test_environment_cannot_redirect_trust_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = trust_registry_path()
    monkeypatch.setenv(
        "VIA_AUTHORIZATION_TRUST_REGISTRY", str(_empty_registry())
    )
    assert trust_registry_path() == before


def test_environment_spoof_cannot_pin_a_self_consistent_shadow_bundle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from test_m6_shadow_receipts import _fixture

    bundle, trust_root, calendar, schedule, _, _ = _fixture()
    attacker_registry = _empty_registry()
    attacker_registry.write_text(
        json.dumps(
            {
                "schema_version": TRUST_REGISTRY_VERSION,
                "pinned_trust_root_sha256": [trust_root_fingerprint(trust_root)],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTEST_VERSION", "spoofed")
    monkeypatch.setenv(
        "VIA_AUTHORIZATION_TRUST_REGISTRY", str(attacker_registry)
    )
    cutoff = datetime.fromisoformat(str(calendar["observation_cutoff"]))

    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            verify_shadow_bundle(bundle, trust_root, schedule, cutoff)


def test_private_shadow_byte_verifier_has_no_unpinned_mode() -> None:
    from test_m6_shadow_receipts import _fixture

    bundle, trust_root, calendar, schedule, _, _ = _fixture()
    cutoff = datetime.fromisoformat(str(calendar["observation_cutoff"]))

    with use_test_trust_registry(_empty_registry()):
        with pytest.raises(TrustRootNotPinnedError, match="not pinned"):
            _verify_shadow_bundle_contents(bundle, trust_root, schedule, cutoff)


def test_test_registry_hook_rejects_paths_outside_the_temp_dir() -> None:
    with pytest.raises(ValueError, match="temporary"):
        _set_test_trust_registry(DEFAULT_TRUST_REGISTRY_PATH)
