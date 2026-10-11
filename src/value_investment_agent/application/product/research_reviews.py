"""Attach existing typed research reviews to the exact shared descriptor inputs."""
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from ...human_research_approval import human_research_approval_from_payload
from ...event_materiality import event_materiality_review_from_payload
from ...event_scan import COVERAGE_COMPLETE
from ...research_artifact_codecs import artifact_payload
from ...research_input import build_research_run_spec, descriptor_sha256, facts_to_payload
from ...research_run_contract import canonical_contract_payload
from .common import require_inside, load_json_object, sha256_file, sha256_bytes

REVIEW_RESPONSE_PURPOSE = b'value-investment/pending-research-response/v1\x00'
# No production legacy records exist. Compatibility requires reviewed exact bytes,
# never a version or missing field supplied by the journal itself.
_PINNED_LEGACY_REVIEW_RECORD_SHA256 = frozenset()


def run_pending_review_command(*, root, args):
    """Optional review mode on the existing company CLI; not a research rerun."""
    resolve = lambda value: None if value is None else root / value
    review_args = (args.pending_review_candidate, args.pending_review_candidate_sha256,
        args.signed_review_response, args.signed_review_response_sha256,
        args.review_trust_root, args.review_trust_root_sha256,
        args.previous_review_response, args.previous_review_response_sha256)
    if not args.prepare_review_response and all(value is None for value in review_args):
        return None
    if (args.pending_review_candidate is None or args.pending_review_candidate_sha256 is None
            or args.output is None or args.prepare_review_response == (args.signed_review_response is not None)):
        raise ValueError('review mode needs candidate/hash/output and exactly prepare or signed response')
    ordinary = (args.package, args.existing_manifest, args.existing_manifest_sha256,
        args.arithmetic_input, args.arithmetic_input_sha256, args.quote, args.quote_sha256,
        args.event, args.event_sha256, args.research_reviews, args.research_reviews_sha256,
        args.schedule_request, args.recommendation_schema_version)
    if any(value is not None for value in ordinary):
        raise ValueError('review response mode excludes ordinary research/market inputs')
    candidate = resolve(args.pending_review_candidate)
    template = prepare_pending_review_response(root=root, candidate_path=candidate,
        candidate_sha256=args.pending_review_candidate_sha256)
    if template['symbol'] != args.symbol:
        raise ValueError('review candidate issuer mismatch')
    if args.prepare_review_response:
        if any(value is not None for value in review_args[2:]):
            raise ValueError('prepare mode excludes signed response and trust inputs')
        from .common import write_new_json
        output = require_inside(root / 'runtime', resolve(args.output), 'review response form')
        write_new_json(output, template)
        return dict(status='EDITABLE_RESPONSE_PREPARED_NOT_APPROVED', action='no_order',
            path=str(output), sha256=sha256_file(output), group_count=len(template['groups']))
    if any(value is None for value in review_args[2:6]):
        raise ValueError('signed response requires complete response and trust-root hashes')
    return consume_pending_review_response(root=root, candidate_path=candidate,
        candidate_sha256=args.pending_review_candidate_sha256,
        response_path=resolve(args.signed_review_response), response_sha256=args.signed_review_response_sha256,
        trust_root_path=resolve(args.review_trust_root), trust_root_sha256=args.review_trust_root_sha256,
        output_dir=resolve(args.output), previous_response_path=resolve(args.previous_review_response),
        previous_response_sha256=args.previous_review_response_sha256,
        resume_incomplete=getattr(args, 'resume_incomplete', False),
        incomplete_consumption_sha256=getattr(args, 'incomplete_consumption_sha256', None))


def prepare_pending_review_response(*, root: Path, candidate_path: Path,
                                    candidate_sha256: str) -> dict:
    """Create editable input, separate from immutable generated intake/receipts."""
    intake = prepare_pending_review_intake(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    return dict(schema_version='pending-research-review-response-v1', action='no_order',
        symbol=intake['symbol'], candidate_binding=intake['candidate_binding'],
        model_context=intake['model_context'],
        valuation_artifact_sha256=intake['valuation_artifact_sha256'],
        reviewer_id=None, reviewed_at=None, whole_model_approval=None,
        supersedes_response_sha256=None,
        groups=[dict(id=g['id'], field_paths=g['field_paths'], response=None,
                     response_reason=None, confirmed_scope=None) for g in intake['groups']])


def _review_time(value, label):
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f'{label} requires a timezone timestamp') from error
    if parsed.utcoffset() is None:
        raise ValueError(f'{label} requires a timezone timestamp')
    return parsed


def _strict_review_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate review JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite review JSON constant: ' + value)
    value = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs,
                       parse_constant=constant)
    if not isinstance(value, dict):
        raise ValueError('review input must be an object')
    return value


def _review_json_bytes(payload):
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf-8')


def _append_review_json(path, payload):
    """Publish complete bytes without overwriting; retain failed staging for audit."""
    raw = _review_json_bytes(payload)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('incomplete review artifact drift: ' + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.with_name(path.name + '.' + uuid4().hex[:12] + '.part')
    with staging.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(staging, path)
    staging.unlink()


def _verify_review_completion(root, record, payload):
    binding = record['completion_receipt_binding']
    receipt_path = require_inside(root, root / binding['path'], 'review completion')
    if not receipt_path.is_file() or sha256_file(receipt_path) != binding['sha256']:
        raise ValueError('review consumption incomplete or completion receipt drift')
    receipt = _strict_review_json(receipt_path)
    if (receipt.get('schema_version') != 'pending-research-review-consumption-v1'
            or receipt.get('action') != 'no_order'
            or receipt.get('candidate_binding') != record['candidate_binding']
            or receipt.get('response_binding') != record['response_binding']
            or receipt.get('trust_root_binding') != record['trust_root_binding']
            or receipt.get('authenticated_reviewer') != payload['reviewer_id']):
        raise ValueError('review completion identity mismatch')
    packet_binding = receipt.get('review_packet_binding')
    if payload['whole_model_approval'] is not None:
        if not isinstance(packet_binding, dict):
            raise ValueError('review completion packet missing')
        packet_path = require_inside(root, root / packet_binding['path'], 'completed review packet')
        if sha256_file(packet_path) != packet_binding['sha256']:
            raise ValueError('review completion packet drift')
        packet = _strict_review_json(packet_path)
        approval_binding = packet['bindings']['human_approval']
        approval_path = require_inside(root, root / approval_binding['path'], 'completed human approval')
        if (sha256_file(approval_path) != approval_binding['sha256']
                or _strict_review_json(approval_path) != human_research_approval_from_payload(
                    payload['whole_model_approval']).as_policy()):
            raise ValueError('review completion approval drift')


def _authenticated_review_history(root, candidate_sha256, *, incomplete_record=None):
    """Resolve an append-only response head from signed originals, not claims."""
    history = require_inside(root / 'runtime', root / 'runtime/research-review-responses' /
                             candidate_sha256[:24], 'review history')
    entries = []
    for record_path in history.glob('*.json'):
        record = _strict_review_json(record_path)
        loaded = {}
        for role in ('response', 'trust_root'):
            binding = record[role + '_binding']
            original = require_inside(root, root / binding['path'], 'review history original')
            if sha256_file(original) != binding['sha256']:
                raise ValueError('authenticated review history original drift')
            loaded[role] = _strict_review_json(original)
        envelope, trust = loaded['response'], loaded['trust_root']
        candidate_binding = record['candidate_binding']
        if candidate_binding['sha256'] != candidate_sha256:
            raise ValueError('authenticated review history candidate mismatch')
        payload, _, _, _ = _validate_pending_review_response(root=root,
            candidate_path=require_inside(root, root / candidate_binding['path'], 'history candidate'),
            candidate_sha256=candidate_sha256, envelope=envelope, trust=trust, historical=True)
        reviewed = _review_time(payload['reviewed_at'], 'history reviewed_at')
        if (record_path.stem != record['response_binding']['sha256'][:24]
                or record.get('candidate_binding') != payload['candidate_binding']):
            raise ValueError('authenticated review history identity mismatch')
        if 'completion_receipt_binding' in record:
            binding = record['completion_receipt_binding']
            completion = require_inside(root, root / binding['path'], 'review completion')
            if record == incomplete_record and not completion.exists():
                continue
            _verify_review_completion(root, record, payload)
        elif sha256_file(record_path) not in _PINNED_LEGACY_REVIEW_RECORD_SHA256:
            raise ValueError('review history missing completion binding and not pinned legacy')
        entries.append((reviewed, record, payload))
    entries.sort(key=lambda entry: entry[0])
    previous = None
    for _, record, payload in entries:
        expected = None if previous is None else previous[1]['response_binding']['sha256']
        if payload['supersedes_response_sha256'] != expected:
            raise ValueError('authenticated review history conflict or missing predecessor')
        if previous is not None and (payload['reviewer_id'] != previous[2]['reviewer_id']
                or payload['candidate_binding'] != previous[2]['candidate_binding']
                or _review_time(payload['reviewed_at'], 'history time') <= previous[0]):
            raise ValueError('authenticated review history reviewer or time conflict')
        previous = (_, record, payload)
    return history, previous


def _validate_pending_review_response(*, root, candidate_path, candidate_sha256, envelope, trust, historical=False):
    """One complete no-write validator shared by intake and historical loading."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from ...infrastructure.evidence.trust_root_registry import require_pinned_trust_root
    from ...human_research_approval import resolve_human_research_approval
    from .decision_surface import verify_current_decision_workbench

    root = root.resolve()
    candidate_path = require_inside(root, candidate_path, 'review candidate')
    intake = prepare_pending_review_intake(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    if intake['valuation_artifact_sha256'] is None:
        raise ValueError('review requires an actually consumed valuation')
    require_pinned_trust_root(trust)
    if (set(envelope) != {'payload', 'signature'}
            or set(trust) != {'schema_version', 'reviewer_id', 'public_key',
                             'scopes', 'symbols', 'valid_from', 'valid_until'}
            or trust['schema_version'] != 'research-review-transport-trust-root-v1'):
        raise ValueError('review signature envelope or trust scope mismatch')
    if (not isinstance(trust['scopes'], list) or not trust['scopes']
            or set(trust['scopes']) - {'human_group_research', 'human_whole_model'}
            or not isinstance(trust['symbols'], list) or not trust['symbols']
            or any(not isinstance(s, str) or len(s) != 6 or not s.isdigit() for s in trust['symbols'])):
        raise ValueError('review trust privileges must be explicit')
    payload = envelope['payload']
    template = prepare_pending_review_response(root=root, candidate_path=candidate_path,
        candidate_sha256=candidate_sha256)
    if not isinstance(payload, dict) or set(payload) != set(template):
        raise ValueError('review response fields incomplete or unknown')
    for key in ('schema_version', 'action', 'symbol', 'candidate_binding',
                'model_context', 'valuation_artifact_sha256'):
        if payload[key] != template[key]:
            raise ValueError('review exact candidate context mismatch: ' + key)
    if (not isinstance(payload['reviewer_id'], str) or not payload['reviewer_id'].strip()
            or payload['reviewer_id'] != trust['reviewer_id']
            or payload['symbol'] not in trust['symbols']
            or 'human_group_research' not in trust['scopes']):
        raise ValueError('reviewer identity or authorization scope mismatch')
    reviewed = _review_time(payload['reviewed_at'], 'reviewed_at')
    now = datetime.now(timezone.utc)
    start, end = (_review_time(trust[k], k) for k in ('valid_from', 'valid_until'))
    workbench = load_json_object(candidate_path.parent / 'workbench.json', 'candidate workbench')
    if (not (start <= reviewed <= end and reviewed <= now) or (not historical and now > end)
            or reviewed < _review_time(workbench['generated_at'], 'candidate time')):
        raise ValueError('review timestamp or authorization validity mismatch')
    try:
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust['public_key']))
        public.verify(bytes.fromhex(envelope['signature']), REVIEW_RESPONSE_PURPOSE +
                      canonical_contract_payload(payload).encode('utf-8'))
    except (InvalidSignature, TypeError, ValueError) as error:
        raise ValueError('review response signature invalid') from error
    groups = payload['groups']
    if not isinstance(groups, list) or len(groups) != len(template['groups']):
        raise ValueError('review group coverage mismatch')
    blockers = []
    for actual, expected in zip(groups, template['groups']):
        if (not isinstance(actual, dict) or set(actual) != set(expected)
                or actual['id'] != expected['id'] or actual['field_paths'] != expected['field_paths']):
            raise ValueError('review group identity or field scope mismatch')
        state = actual['response']
        if state not in (None, 'VERIFIED', 'REJECTED', 'INSUFFICIENT'):
            raise ValueError('unknown review group response')
        if state is not None and any(not isinstance(actual[key], str) or not actual[key].strip()
                for key in ('response_reason', 'confirmed_scope')):
            raise ValueError('review response requires reason and confirmed scope')
        if state != 'VERIFIED':
            blockers.append(f"{actual['id']}:{state or 'PENDING'}")
    approval_payload = payload['whole_model_approval']
    approval = None
    if approval_payload is not None:
        if 'human_whole_model' not in trust['scopes']:
            raise ValueError('reviewer has no whole-model authorization')
        approval = human_research_approval_from_payload(approval_payload)
        if (approval.reviewer_type != 'human_research_lead'
                or approval.reviewer_id != payload['reviewer_id'] or approval.reviewed_at != reviewed
                or approval.symbol != payload['symbol'] or approval.security_id != payload['symbol']
                or approval.profile_id != intake['model_context']['profile_id']
                or type(approval_payload.get('price_assessment_eligible')) is not bool):
            raise ValueError('whole-model reviewer provenance mismatch')
        restored = verify_current_decision_workbench(workbench)
        decision = resolve_human_research_approval(approval, restored.dependency_objects['valuation'],
            model_id=intake['model_context']['model_id'],
            research_case_payload=restored.dependencies['research_case'].envelope.payload_object(),
            facts_payload=restored.dependencies['financial_facts'].envelope.payload_object(),
            assumptions_payload=restored.dependencies['valuation_assumptions'].envelope.payload_object())
        if not decision.valuation_bound or not decision.dependencies_bound:
            raise ValueError('whole-model approval superseded by exact inputs')
        if decision.approved and blockers:
            raise ValueError('partial or negative group review cannot approve the whole model')
        blockers.extend(decision.blockers)
    else:
        blockers.append('whole_model_review_missing')
    return payload, intake, approval, blockers


def consume_pending_review_response(*, root: Path, candidate_path: Path,
        candidate_sha256: str, response_path: Path, response_sha256: str,
        trust_root_path: Path, trust_root_sha256: str, output_dir: Path,
        previous_response_path: Path | None = None,
        previous_response_sha256: str | None = None, resume_incomplete: bool = False,
        incomplete_consumption_sha256: str | None = None) -> dict:
    """Authenticate transport and reuse typed G3; never admit price or events."""
    root = root.resolve()
    candidate_path = require_inside(root, candidate_path, 'review candidate')
    response_path = require_inside(root, response_path, 'review response')
    trust_root_path = require_inside(root, trust_root_path, 'review trust root')
    output_dir = require_inside(root / 'runtime', output_dir, 'review output')
    checkpoint_path = output_dir / 'incomplete-consumption.json'
    checkpoint = None
    if resume_incomplete:
        if (not incomplete_consumption_sha256 or not checkpoint_path.is_file()
                or sha256_file(checkpoint_path) != incomplete_consumption_sha256):
            raise ValueError('resume requires exact pinned incomplete consumption manifest')
        checkpoint = _strict_review_json(checkpoint_path)
        if (output_dir / 'receipt.json').exists():
            raise ValueError('completed review replay rejected; receipt already exists')
    elif incomplete_consumption_sha256 is not None:
        raise ValueError('incomplete manifest hash requires explicit resume')
    elif output_dir.exists():
        raise ValueError('review output must be new and append-only')
    def pinned_file(path, digest):
        if sha256_file(path) != digest:
            raise ValueError('review input hash mismatch')
        return _strict_review_json(path)
    envelope = pinned_file(response_path, response_sha256)
    trust = pinned_file(trust_root_path, trust_root_sha256)
    payload, intake, approval, blockers = _validate_pending_review_response(root=root,
        candidate_path=candidate_path, candidate_sha256=candidate_sha256, envelope=envelope, trust=trust)
    if (previous_response_path is None) != (previous_response_sha256 is None):
        raise ValueError('previous review requires both path and hash')
    history, head = _authenticated_review_history(root, candidate_sha256,
        incomplete_record=None if checkpoint is None else checkpoint.get('journal_record'))
    if head is not None and (previous_response_sha256 != head[1]['response_binding']['sha256']
            or response_sha256 == head[1]['response_binding']['sha256']):
        raise ValueError('review requires authenticated latest predecessor; replay rejected')
    if head is None and previous_response_path is not None:
        raise ValueError('previous review has not been authenticated and consumed')
    if previous_response_path is None:
        if payload['supersedes_response_sha256'] is not None:
            raise ValueError('review cannot supersede an unavailable response')
    else:
        previous_response_path = require_inside(root, previous_response_path, 'previous review')
        previous = pinned_file(previous_response_path, previous_response_sha256)['payload']
        if (payload['supersedes_response_sha256'] != previous_response_sha256
                or previous['candidate_binding'] != payload['candidate_binding']
                or previous['reviewer_id'] != payload['reviewer_id']
                or _review_time(previous['reviewed_at'], 'previous reviewed_at') >=
                    _review_time(payload['reviewed_at'], 'reviewed_at')):
            raise ValueError('review conflict or supersession mismatch')
    groups = payload['groups']
    for path, digest in ((response_path, response_sha256), (trust_root_path, trust_root_sha256)):
        if sha256_file(path) != digest:
            raise ValueError('review input changed during verification')
    prepare_pending_review_intake(root=root, candidate_path=candidate_path, candidate_sha256=candidate_sha256)
    result = dict(schema_version='pending-research-review-consumption-v1', symbol=payload['symbol'],
        action='no_order', candidate_binding=payload['candidate_binding'],
        response_binding=dict(path=response_path.relative_to(root).as_posix(), sha256=response_sha256),
        trust_root_binding=dict(path=trust_root_path.relative_to(root).as_posix(), sha256=trust_root_sha256),
        authenticated_reviewer=payload['reviewer_id'], groups=groups,
        whole_model_review_present=approval is not None, blockers=list(dict.fromkeys(blockers)),
        research_admitted=False, event_materiality_approved=False, price_admitted=False,
        position_guidance=None, registered_current_case_changed=False)
    files = {}
    if approval is not None:
        approval_path = output_dir / 'human-approval.json'
        files['human-approval.json'] = approval.as_policy()
        packet = dict(schema_version='shared-research-review-inputs-v1', symbol=payload['symbol'],
            authenticated_response_binding=result['response_binding'],
            reviewed_candidate_binding=payload['candidate_binding'],
            action='no_order', bindings={'human_approval': dict(
                path=approval_path.relative_to(root).as_posix(),
                sha256=sha256_bytes(_review_json_bytes(files['human-approval.json'])))})
        files['research-reviews.json'] = packet
        result['review_packet_binding'] = dict(path=(output_dir / 'research-reviews.json').relative_to(root).as_posix(),
                                               sha256=sha256_bytes(_review_json_bytes(packet)))
    journal_record = dict(candidate_binding=payload['candidate_binding'],
        response_binding=result['response_binding'], trust_root_binding=result['trust_root_binding'],
        completion_receipt_binding=dict(path=(output_dir/'receipt.json').relative_to(root).as_posix(),
            sha256=sha256_bytes(_review_json_bytes(result))))
    plan = dict(action='no_order', candidate_binding=payload['candidate_binding'],
        response_binding=result['response_binding'], trust_root_binding=result['trust_root_binding'],
        previous_response_sha256=previous_response_sha256,
        output_dir=output_dir.relative_to(root).as_posix(), files=files,
        journal_record=journal_record, completion_receipt=result)
    if checkpoint is not None and checkpoint != plan:
        raise ValueError('incomplete review manifest differs from authenticated inputs')
    _append_review_json(checkpoint_path, plan)
    for name, value in files.items():
        _append_review_json(output_dir / name, value)
    journal_path = history / (response_sha256[:24] + '.json')
    _append_review_json(journal_path, journal_record)
    # Recheck the predecessor and staged bytes before exposing the success receipt.
    _, current_head = _authenticated_review_history(root, candidate_sha256, incomplete_record=journal_record)
    if current_head != head:
        raise ValueError('review head changed during consumption')
    for name, value in files.items():
        if (output_dir / name).read_bytes() != _review_json_bytes(value):
            raise ValueError('incomplete review artifact changed before completion')
    for path, digest in ((response_path, response_sha256), (trust_root_path, trust_root_sha256)):
        if sha256_file(path) != digest:
            raise ValueError('review input changed before completion')
    prepare_pending_review_intake(root=root, candidate_path=candidate_path, candidate_sha256=candidate_sha256)
    _append_review_json(output_dir / 'receipt.json', result)
    _verify_review_completion(root, journal_record, payload)
    return result


def prepare_pending_review_intake(*, root: Path, candidate_path: Path,
                                  candidate_sha256: str) -> dict:
    """Expose stable response scopes without creating a human approval receipt."""
    from .pending_research_candidate import verify_pending_research_candidate
    from .decision_surface import verify_current_decision_workbench
    from ...research_run_contract import valuation_result_sha256

    candidate_path = require_inside(root, candidate_path, 'pending review candidate')
    candidate = verify_pending_research_candidate(root=root, path=candidate_path,
        expected_sha256=candidate_sha256)
    groups = candidate.get('review_groups') or []
    ids = [group['id'] for group in groups]
    if len(ids) != len(set(ids)):
        raise ValueError('pending review group ids must be unique')
    valuation_hash = None
    if candidate['model_context_scope'] == 'ACTUALLY_CONSUMED':
        workbench = load_json_object(candidate_path.parent / 'workbench.json', 'candidate workbench')
        objects = verify_current_decision_workbench(workbench).dependency_objects
        if objects.get('valuation') is not None:
            valuation_hash = valuation_result_sha256(objects['valuation'])
    return {
        'schema_version': 'pending-research-review-intake-v1',
        'symbol': candidate['symbol'], 'action': 'no_order',
        'status': 'AWAITING_HUMAN_RESPONSES' if groups else 'GROUPED_REVIEW_UNAVAILABLE',
        'candidate_binding': {'path': candidate_path.relative_to(root.resolve()).as_posix(),
                              'sha256': candidate_sha256},
        'model_context': candidate['model_context'],
        'valuation_artifact_sha256': valuation_hash,
        'groups': [{**group, 'response': None, 'response_reason': None} for group in groups],
        'permitted_group_responses': ['VERIFIED', 'REJECTED', 'INSUFFICIENT'],
        'whole_model_decision': None, 'reviewer': None,
        'scope': 'GROUP_RESPONSES_ARE_NOT_WHOLE_MODEL_OR_EVENT_APPROVAL',
        'required_before_approval': ['Authentic reviewer provenance and exact whole-model decision.',
                                     'Separate complete model-bound announcement materiality review.'],
        'approval_changed': False, 'research_admitted': False, 'price_admitted': False,
        'position_guidance': None, 'canonical_written': False,
    }


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
    refs = packet['bindings']
    if not refs or set(refs) - {'human_approval', 'event_materiality'}:
        raise ValueError('research reviews require registered typed bindings')
    authenticated_g3_only = (
        set(refs) == {'human_approval'}
        and packet.get('authenticated_response_binding') is not None
        and packet.get('reviewed_candidate_binding') is not None
    )
    if (require_model_binding and schema != 'shared-research-review-inputs-v2'
            and not authenticated_g3_only):
        raise ValueError('materiality model binding requires a v2 research review packet')
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
        journal = require_inside(root / 'runtime', root / 'runtime/research-review-responses', 'review journal')
        has_journal = any(journal.glob('*/*.json'))
        live_context = (build_research_review_model_context(descriptor=descriptor, spec=spec)
                        if has_journal else None)
        context_heads = []
        for directory in journal.glob('*'):
            if directory.is_dir():
                records = list(directory.glob('*.json'))
                if not records:
                    continue
                from .pending_research_candidate import verify_pending_research_candidate
                relevant = set()
                for record_path in records:
                    binding = _strict_review_json(record_path)['candidate_binding']
                    candidate = verify_pending_research_candidate(root=root,
                        path=require_inside(root, root / binding['path'], 'history candidate'),
                        expected_sha256=binding['sha256'])
                    if directory.name != binding['sha256'][:24]:
                        raise ValueError('review history candidate directory mismatch')
                    if candidate['model_context'] == live_context:
                        relevant.add(binding['sha256'])
                if not relevant:
                    continue
                if len(relevant) != 1:
                    raise ValueError('review history candidate collision')
                digest = next(iter(relevant))
                _, existing_head = _authenticated_review_history(root, digest)
                if existing_head is not None and existing_head[2]['model_context'] == live_context:
                    context_heads.append(existing_head)
        if len(context_heads) > 1:
            raise ValueError('authenticated review has conflicting candidate heads for the same model context')
        if context_heads and packet.get('authenticated_response_binding') is None:
            raise ValueError('authenticated review provenance cannot be stripped from a current packet')
        if packet.get('authenticated_response_binding') is not None:
            candidate_binding = packet['reviewed_candidate_binding']
            from .pending_research_candidate import verify_pending_research_candidate
            candidate = verify_pending_research_candidate(root=root, path=root / candidate_binding['path'],
                expected_sha256=candidate_binding['sha256'])
            if candidate['model_context'] != build_research_review_model_context(descriptor=descriptor, spec=spec):
                raise ValueError('authenticated review packet candidate differs from live inputs')
            _, head = _authenticated_review_history(root, candidate_binding['sha256'])
            if (head is None or packet['authenticated_response_binding'] != head[1]['response_binding']
                    or head[2]['whole_model_approval'] is None
                    or human_research_approval_from_payload(head[2]['whole_model_approval']).as_policy() != loaded['human_approval']):
                raise ValueError('authenticated review packet superseded or conflicting')
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
