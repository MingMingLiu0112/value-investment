"""Explicit TEST_ONLY signatures for older shared-service integration fixtures."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from value_investment_agent.application.product.common import sha256_file, write_new_json
from value_investment_agent.application.product.research_materiality_reviews import (
    MATERIALITY_RESPONSE_PURPOSE, prepare_materiality_review_handoff, consume_materiality_review_response,
)
from value_investment_agent.infrastructure.evidence import trust_root_registry as registry
from value_investment_agent.research_run_contract import canonical_contract_payload


@pytest.fixture
def authenticated_materiality_packet(tmp_path, monkeypatch):
    """Sign each explicit fixture through production transport; no auth bypass."""
    serial = 0
    def create(package_path, review, *, extra_packet=None):
        nonlocal serial
        serial += 1
        root = tmp_path
        folder = root / 'runtime' / ('TEST_ONLY-materiality-' + str(serial))
        folder.mkdir(parents=True)
        package = json.loads(package_path.read_text(encoding='utf-8'))
        scan_ref = package['model_validity_input']['event_scan_ref']
        handoff = prepare_materiality_review_handoff(root=root, package_path=package_path,
            package_sha256=sha256_file(package_path), scan_path=root / scan_ref['path'],
            scan_sha256=scan_ref['sha256'])
        reviewer = 'TEST_ONLY-EXTERNAL-MATERIALITY'
        reviewed = review.reviewed_at
        signed_review = replace(review, reviewer_id=reviewer,
            decisions=tuple(replace(item, reviewer_id=reviewer, reviewed_at=reviewed)
                            for item in review.decisions))
        typed = dict(signed_review.as_policy(), model_context=handoff['model_context'])
        response = dict(handoff['unsigned_response'], reviewer_id=reviewer,
                        reviewed_at=reviewed.isoformat(), event_materiality=typed)
        key = Ed25519PrivateKey.generate()
        trust = dict(schema_version='research-review-transport-trust-root-v1', reviewer_id=reviewer,
            public_key=key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
            scopes=['human_event_materiality'], symbols=[review.symbol],
            valid_from=(reviewed-timedelta(days=1)).isoformat(),
            valid_until=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat())
        pins = registry.pinned_trust_root_fingerprints() | {registry.trust_root_fingerprint(trust)}
        registry_path = folder / 'TEST_ONLY-registry.json'
        write_new_json(registry_path, dict(schema_version='authorization-trust-root-registry-v1',
            pinned_trust_root_sha256=sorted(pins)))
        monkeypatch.setattr(registry, '_TEST_REGISTRY_PATH', registry_path)
        originals = dict(handoff=handoff, trust=trust, response=dict(payload=response,
            signature=key.sign(MATERIALITY_RESPONSE_PURPOSE +
                canonical_contract_payload(response).encode('utf-8')).hex()))
        for role, payload in originals.items():
            write_new_json(folder / (role+'.json'), payload)
        receipt = consume_materiality_review_response(root=root,
            handoff_path=folder/'handoff.json', handoff_sha256=sha256_file(folder/'handoff.json'),
            response_path=folder/'response.json', response_sha256=sha256_file(folder/'response.json'),
            trust_root_path=folder/'trust.json', trust_root_sha256=sha256_file(folder/'trust.json'),
            output_dir=folder/'consumed')
        path = root / receipt['review_packet_binding']['path']
        packet = json.loads(path.read_text(encoding='utf-8'))
        if extra_packet is not None:
            extra = json.loads(extra_packet.read_text(encoding='utf-8'))
            for name in ('authenticated_response_binding', 'reviewed_candidate_binding'):
                if name in extra:
                    packet[name] = extra[name]
            if 'human_approval' in extra['bindings']:
                packet['bindings']['human_approval'] = extra['bindings']['human_approval']
            path = folder/'combined-packet.json'
            write_new_json(path, packet)
        artifact = root / packet['bindings']['event_materiality']['path']
        return path, sha256_file(path), signed_review, artifact, sha256_file(artifact)
    return create
