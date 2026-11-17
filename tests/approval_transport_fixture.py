"""TEST_ONLY capability minting for synthetic, non-production decisions."""
from dataclasses import replace
import hashlib

from value_investment_agent.domain.research.human_research_approval import (
    AUTHENTICATED_TRANSPORT_BINDING_SCHEMA,
    mint_verified_human_research_approval_transport,
)


def fixture_transport_binding(label: str) -> dict:
    digest = hashlib.sha256(f"TEST_ONLY:{label}".encode("utf-8")).hexdigest()
    return {
        "schema_version": AUTHENTICATED_TRANSPORT_BINDING_SCHEMA,
        "transport": "SIGNED_PENDING_REVIEW_RESPONSE",
        "response_binding": {"path": f"runtime/TEST_ONLY-{label}-response.json", "sha256": digest},
        "candidate_binding": {"path": f"runtime/TEST_ONLY-{label}-candidate.json", "sha256": digest},
        "trust_root_binding": {"path": f"runtime/TEST_ONLY-{label}-trust.json", "sha256": digest},
    }


def mint_fixture_approval(approval):
    """Mint an in-process test capability after the fixture already passed its typed checks."""
    if approval is None:
        return None
    unbound = replace(approval, authenticated_transport_binding=None, verified_transport=None)
    return mint_verified_human_research_approval_transport(
        unbound, fixture_transport_binding(approval.approval_id)
    )
