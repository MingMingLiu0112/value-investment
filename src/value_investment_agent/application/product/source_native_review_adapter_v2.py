"""Versioned unsigned intake; frozen v1 authentication stays byte-for-byte intact.

This adapter does not consume signatures or approve native candidates. It uses
the existing response/intake contracts for review preparation, not a second
approval transport. Native authenticated consumption remains an explicit gap.
"""
from pathlib import Path

from .common import load_json_object, require_inside, sha256_file
from . import research_reviews as frozen
from .source_native_candidate_v2 import SCHEMA, verify_source_native_candidate


def _native_or_legacy(*, root: Path, candidate_path: Path, candidate_sha256: str):
    root = root.resolve()
    path = require_inside(root / 'runtime', candidate_path, 'versioned unsigned review')
    if sha256_file(path) != candidate_sha256:
        raise ValueError('Versioned unsigned review candidate hash mismatch')
    schema = load_json_object(path, 'versioned unsigned candidate').get('schema_version')
    if schema == 'pending-research-candidate-v1':
        return None
    if schema != SCHEMA:
        raise ValueError('Unsupported unsigned review candidate schema')
    return verify_source_native_candidate(root=root, path=path, expected_sha256=candidate_sha256)


def prepare_pending_review_intake(*, root: Path, candidate_path: Path, candidate_sha256: str) -> dict:
    candidate = _native_or_legacy(root=root, candidate_path=candidate_path, candidate_sha256=candidate_sha256)
    if candidate is None:
        return frozen.prepare_pending_review_intake(root=root, candidate_path=candidate_path,
            candidate_sha256=candidate_sha256)
    from .decision_surface import verify_current_decision_workbench
    from ...research_run_contract import valuation_result_sha256

    path = require_inside(root.resolve() / 'runtime', candidate_path, 'native unsigned review')
    workbench = load_json_object(path.parent / 'workbench.json', 'native consumed workbench')
    objects = verify_current_decision_workbench(workbench).dependency_objects
    if objects.get('valuation') is None:
        raise ValueError('Native unsigned intake requires consumed valuation')
    groups = candidate['review_groups']
    if len({group['id'] for group in groups}) != len(groups):
        raise ValueError('Native unsigned review group collision')
    result = dict(schema_version='pending-research-review-intake-v1', symbol=candidate['symbol'], action='no_order',
        status='AWAITING_HUMAN_RESPONSES', candidate_binding=dict(path=path.relative_to(root.resolve()).as_posix(),
        sha256=candidate_sha256), model_context=candidate['model_context'],
        valuation_artifact_sha256=valuation_result_sha256(objects['valuation']),
        groups=[dict(group, response=None, response_reason=None) for group in groups],
        permitted_group_responses=['VERIFIED', 'REJECTED', 'INSUFFICIENT'], whole_model_decision=None, reviewer=None,
        scope='GROUP_RESPONSES_ARE_NOT_WHOLE_MODEL_OR_EVENT_APPROVAL',
        required_before_approval=['AUTHENTICATED_NATIVE_CANDIDATE_CONSUMPTION_NOT_IMPLEMENTED',
            'Authentic reviewer provenance and exact whole-model decision.',
            'Separate complete model-bound announcement materiality review.'],
        native_authenticated_consumption_supported=False, approval_changed=False,
        research_admitted=False, price_admitted=False, position_guidance=None, canonical_written=False)
    if verify_source_native_candidate(root=root, path=path, expected_sha256=candidate_sha256) != candidate:
        raise ValueError('Native candidate changed during unsigned review preparation')
    return result


def prepare_pending_review_response(*, root: Path, candidate_path: Path, candidate_sha256: str) -> dict:
    candidate = _native_or_legacy(root=root, candidate_path=candidate_path, candidate_sha256=candidate_sha256)
    if candidate is None:
        return frozen.prepare_pending_review_response(root=root, candidate_path=candidate_path,
            candidate_sha256=candidate_sha256)
    intake = prepare_pending_review_intake(root=root, candidate_path=candidate_path, candidate_sha256=candidate_sha256)
    return dict(schema_version='pending-research-review-response-v1', action='no_order',
        symbol=intake['symbol'], candidate_binding=intake['candidate_binding'], model_context=intake['model_context'],
        valuation_artifact_sha256=intake['valuation_artifact_sha256'], reviewer_id=None, reviewed_at=None,
        whole_model_approval=None, supersedes_response_sha256=None,
        groups=[dict(id=g['id'], field_paths=g['field_paths'], response=None,
            response_reason=None, confirmed_scope=None) for g in intake['groups']])
