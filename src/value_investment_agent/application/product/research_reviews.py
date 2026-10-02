"""Attach existing typed research reviews to the exact shared descriptor inputs."""
from dataclasses import replace
import json
from pathlib import Path

from ...human_research_approval import human_research_approval_from_payload
from ...event_materiality import event_materiality_review_from_payload
from .common import require_inside, load_json_object, sha256_file, sha256_bytes


def attach_research_reviews(*, root: Path, spec, descriptor, path: Path,
                            expected_sha256: str, event_sha256: str | None):
    path = require_inside(root, path, 'research review packet')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research review packet hash mismatch')
    packet = load_json_object(path, 'research review packet')
    if (packet.get('schema_version') != 'shared-research-review-inputs-v1'
            or packet.get('action') != 'no_order' or packet.get('symbol') != spec.symbol):
        raise ValueError('research review packet scope mismatch')
    refs = packet['bindings']
    if not refs or set(refs) - {'human_approval', 'event_materiality'}:
        raise ValueError('research reviews require registered typed bindings')
    loaded = {}
    for role, binding in refs.items():
        source = require_inside(root, root / binding['path'], role)
        if sha256_file(source) != binding['sha256']:
            raise ValueError('research review artifact hash mismatch')
        loaded[role] = load_json_object(source, role)
    canonical = descriptor.as_policy()
    changes = dict(research_case_payload=canonical['research_case'],
        facts_payload=canonical['facts'], assumptions_payload=canonical['assumptions'])
    if 'human_approval' in loaded:
        approval = human_research_approval_from_payload(loaded['human_approval'])
        if approval.symbol != spec.symbol:
            raise ValueError('human review issuer mismatch')
        changes['human_research_approval'] = approval
    if 'event_materiality' in loaded:
        review = event_materiality_review_from_payload(loaded['event_materiality'])
        if review.symbol != spec.symbol or not event_sha256 or review.scan_sha256 != event_sha256:
            raise ValueError('materiality review must bind the exact acquired event scan')
        validity = spec.model_validity_input
        if validity is None or validity.events:
            raise ValueError('materiality review requires a declared non-conflicting validity input')
        changes['event_materiality_review'] = review
        changes['model_validity_input'] = replace(validity, event_scan=None)
    changes['input_descriptor_sha256'] = sha256_bytes(json.dumps(dict(
        descriptor=spec.input_descriptor_sha256, review_packet=expected_sha256),
        sort_keys=True).encode('utf-8'))
    for role, binding in refs.items():
        if sha256_file(root / binding['path']) != binding['sha256']:
            raise ValueError('research review changed during attachment')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research review packet changed during attachment')
    return replace(spec, **changes)
