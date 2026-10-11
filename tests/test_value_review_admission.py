"""Reuse synthetic signed transport fixtures without registering real identities."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from test_pending_review_response import signed, consume
from value_investment_agent.operations.authorization.trust_root_registry import trust_root_fingerprint


@pytest.mark.parametrize("fault", ["issuer_permission", "expired_root"])
def test_signed_transport_rejects_explicit_issuer_or_expiry_violation(signed, fault):
    if fault == "issuer_permission":
        signed["trust"]["symbols"] = ["000001"]
    else:
        now = datetime.now(timezone.utc)
        signed["trust"]["valid_from"] = (now - timedelta(days=2)).isoformat()
        signed["trust"]["valid_until"] = (now - timedelta(days=1)).isoformat()
    # Re-pin only this process-local fixture so rejection tests the actual
    # permission/time contract rather than merely an unknown fingerprint.
    signed["registry"].write_text(json.dumps({
        "schema_version": "authorization-trust-root-registry-v1",
        "pinned_trust_root_sha256": [trust_root_fingerprint(signed["trust"])],
    }), encoding="utf-8")
    with pytest.raises(ValueError):
        consume(signed)
    assert not (signed["root"] / "runtime/response-consumed/receipt.json").exists()


def test_exact_signed_response_cannot_be_replayed_into_a_new_consumption(signed):
    first = consume(signed)
    assert first["research_admitted"] is first["price_admitted"] is False
    with pytest.raises(ValueError, match="predecessor|replay"):
        consume(signed, suffix="-replay")
    assert not (signed["root"] / "runtime/response-consumed-replay/receipt.json").exists()
