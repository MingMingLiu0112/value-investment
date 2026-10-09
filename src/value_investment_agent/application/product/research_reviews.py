"""Attach existing typed research reviews to the exact shared descriptor inputs."""
from dataclasses import replace
import json
from pathlib import Path

from ...human_research_approval import human_research_approval_from_payload
from ...event_materiality import event_materiality_review_from_payload
from ...event_scan import COVERAGE_COMPLETE
from ...research_artifact_codecs import artifact_payload
from ...research_input import build_research_run_spec, descriptor_sha256, facts_to_payload
from ...research_run_contract import canonical_contract_payload
from .common import require_inside, load_json_object, sha256_file, sha256_bytes


def _payload_sha256(payload):
    return sha256_bytes(canonical_contract_payload(payload).encode('utf-8'))


def build_research_review_model_context(*, descriptor, spec) -> dict[str, str]:
    """Prepare context for independent review; never stamp a reviewed artifact.

    Require the actual run inputs to agree with the descriptor before exposing
    its binding. The returned context must be included in the reviewed original.
    """
    digest = descriptor_sha256(descriptor)
    if descriptor.input_sha256 != digest or spec.input_descriptor_sha256 != digest:
        raise ValueError('materiality model context descriptor hash mismatch')
    expected_spec = build_research_run_spec(descriptor)
    if spec.assumptions is None:
        raise ValueError('materiality model context requires an assumption payload')
    for field in (
        'symbol', 'profile_id', 'requested_model', 'as_of', 'available_at',
        'report_period', 'valuation_date', 'computed_at', 'input_sources',
        'assumption_bindings', 'rule_version', 'model_version', 'parser_version',
        'scan_watermark', 'quote', 'model_validity_input', 'valuation_approval',
        'distribution_result',
    ):
        if getattr(spec, field) != getattr(expected_spec, field):
            raise ValueError(f'materiality model context spec mismatch: {field}')
    canonical = descriptor.as_policy()
    actual = {
        'research_case': artifact_payload(spec.research_case)[1],
        'facts': facts_to_payload(spec.facts),
        'assumptions': artifact_payload(spec.assumptions)[1],
    }
    for role, payload in actual.items():
        if _payload_sha256(payload) != _payload_sha256(canonical[role]):
            raise ValueError(f'materiality model context spec mismatch: {role}')
        declared = getattr(spec, role + '_payload')
        if declared is not None and _payload_sha256(declared) != _payload_sha256(payload):
            raise ValueError(f'materiality model context spec payload mismatch: {role}')
    return {
        'input_descriptor_sha256': digest,
        'research_case_sha256': _payload_sha256(actual['research_case']),
        'facts_sha256': _payload_sha256(actual['facts']),
        'assumptions_sha256': _payload_sha256(actual['assumptions']),
        'model_id': descriptor.dependencies.model_id,
        'model_version': spec.model_version,
        'profile_id': spec.profile_id,
        'research_as_of': spec.as_of.isoformat(),
    }


def attach_research_reviews(*, root: Path, spec, descriptor, path: Path,
                            expected_sha256: str, event_sha256: str | None,
                            require_model_binding: bool = False):
    path = require_inside(root, path, 'research review packet')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research review packet hash mismatch')
    packet = load_json_object(path, 'research review packet')
    schema = packet.get('schema_version')
    if (schema not in {'shared-research-review-inputs-v1', 'shared-research-review-inputs-v2'}
            or packet.get('action') != 'no_order' or packet.get('symbol') != spec.symbol):
        raise ValueError('research review packet scope mismatch')
    if require_model_binding and schema != 'shared-research-review-inputs-v2':
        raise ValueError('materiality model binding requires a v2 research review packet')
    refs = packet['bindings']
    if not refs or set(refs) - {'human_approval', 'event_materiality'}:
        raise ValueError('research reviews require registered typed bindings')
    loaded = {}
    for role, binding in refs.items():
        source = require_inside(root, root / binding['path'], role)
        if sha256_file(source) != binding['sha256']:
            raise ValueError('research review artifact hash mismatch')
        loaded[role] = load_json_object(source, role)
    model_context = None
    if schema == 'shared-research-review-inputs-v2':
        if 'event_materiality' not in loaded:
            raise ValueError('v2 research reviews require model-bound event materiality')
        model_context = build_research_review_model_context(descriptor=descriptor, spec=spec)
        declared = loaded['event_materiality'].get('model_context')
        if (not isinstance(declared, dict) or set(declared) != set(model_context)
                or any(type(value) is not str for value in declared.values())
                or declared != model_context):
            raise ValueError('materiality artifact model context missing, unknown or mismatched')
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
        scan = validity.event_scan
        if scan is None or scan.symbol != spec.symbol or scan.coverage_status != COVERAGE_COMPLETE:
            raise ValueError('materiality review requires the complete acquired scan')
        if (review.scan_from != scan.scan_from or review.scan_to != scan.scan_to
                or scan.validity_from != validity.valid_from
                or review.reviewed_at < scan.retrieved_at):
            raise ValueError('materiality review scan window or observation mismatch')
        announcements = {item.announcement_id: item for item in scan.announcements}
        if set(announcements) != {item.announcement_id for item in review.decisions}:
            raise ValueError('materiality review must cover every acquired announcement exactly')
        for decision in review.decisions:
            announcement = announcements[decision.announcement_id]
            if (decision.published_at != announcement.published_at
                    or not any(ref.get('sha256') == decision.source_sha256
                        and (ref.get('id') == decision.source_ref.get('id')
                             or (ref.get('path') is not None
                                 and ref.get('path') == decision.source_ref.get('path')))
                        for ref in announcement.evidence_refs)):
                raise ValueError('materiality review announcement source mismatch')
        changes['event_materiality_review'] = review
        changes['model_validity_input'] = replace(validity, event_scan=None,
            blockers=tuple(dict.fromkeys((*validity.blockers, *scan.blockers))),
            event_scan_evidence_refs=tuple((*validity.event_scan_evidence_refs, *scan.evidence_refs)))
    dependencies = dict(descriptor=spec.input_descriptor_sha256, review_packet=expected_sha256)
    if model_context is not None:
        dependencies['model_context'] = model_context
    changes['input_descriptor_sha256'] = sha256_bytes(json.dumps(dependencies,
        sort_keys=True).encode('utf-8'))
    for role, binding in refs.items():
        if sha256_file(root / binding['path']) != binding['sha256']:
            raise ValueError('research review changed during attachment')
    if sha256_file(path) != expected_sha256:
        raise ValueError('research review packet changed during attachment')
    return replace(spec, **changes)
