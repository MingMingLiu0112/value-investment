"""Versioned research-only native transport; never registers or grants price authority.

The atomic journal record is the completion point. Orphan output is not approval;
automatic incomplete-transaction recovery is deliberately unsupported here.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .common import require_inside, sha256_file, write_new_json
from .company_research import _serialize_outcome
from .decision_surface import verify_current_decision_workbench, current_recommendation_type
from .research_reviews import _strict_review_json, _review_time
from .source_native_candidate_v2 import verify_source_native_candidate
from ..portfolio.private_journal_lock import InterProcessLock
from ...infrastructure.evidence.trust_root_registry import require_pinned_trust_root
from ...human_research_approval import (
    human_research_approval_from_payload, mint_verified_human_research_approval_transport,
    resolve_human_research_approval,
)
from ...research_run_contract import canonical_contract_payload, valuation_result_sha256
from ...m1_valuation_package_builder import build_descriptor
from ...research_input import build_research_run_spec
from ...research_application import ResearchApplicationService

SCHEMA = 'source-native-research-review-response-v2'
PURPOSE = b'value-investment/source-native-research-response/v2\x00'
RECEIPT_SCHEMA = 'source-native-research-review-consumption-v2'
JOURNAL_SCHEMA = 'source-native-research-review-completion-v2'
NAMESPACE = 'runtime/source-native-review-responses-v2'
CONSUMPTIONS = 'runtime/source-native-review-consumptions-v2'
# The executed dependency bytes are part of the signed model-review contract.
IMPLEMENTATIONS = (
    'application/product/source_native_signed_review_v2.py',
    'application/product/source_native_candidate_v2.py',
    'domain/valuation/source_native_cash_v1.py',
    'application/product/common.py', 'application/product/research_reviews.py',
    'application/product/pending_research_candidate.py',
    'application/product/pending_candidate_replay.py',
    'application/product/pending_replay_publication.py',
    'application/product/workbench.py', 'application/product/source_bound_inputs.py',
    'application/product/research_review_packet.py',
    'application/product/company_research.py', 'application/product/decision_surface.py',
    'application/decision/restore_decision_recommendation.py',
    'application/portfolio/private_journal_lock.py',
    'infrastructure/evidence/trust_root_registry.py',
    'domain/research/human_research_approval.py', 'domain/research/human_review_integrity.py',
    'domain/research/research_run_contract.py',
    'domain/research/issuer_identity.py', 'domain/research/issuer_identity_registry.json',
    'research_application.py', 'research_input.py', 'm1_valuation_package_builder.py',
    'valuation_router.py', 'valuation_models/residual_income.py',
)
RECEIPT_FIELDS = {'schema_version', 'action', 'scope', 'candidate_binding', 'response_binding',
    'trust_root_binding', 'sequence', 'previous_response_binding', 'consumed_at', 'source_bindings'}


def _clock(now):
    value = now if now is not None else datetime.now(timezone.utc)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('Native review requires a trusted aware clock')
    return value


def _binding(root, path):
    path = require_inside(root, path, 'native review file')
    return dict(path=path.relative_to(root).as_posix(), sha256=sha256_file(path))


def _read(root, ref):
    if not isinstance(ref, dict) or set(ref) != {'path', 'sha256'}:
        raise ValueError('Native review requires an exact path/hash binding')
    if not isinstance(ref['path'], str) or not isinstance(ref['sha256'], str):
        raise ValueError('Native review binding types invalid')
    path = require_inside(root, root / ref['path'], 'native review bound file')
    if _binding(root, path) != ref:
        raise ValueError('Native review canonical path/hash drift')
    payload = _strict_review_json(path)
    if _binding(root, path) != ref:
        raise ValueError('Native review file changed during read')
    return payload


def _closure(root, refs):
    result = {}
    for ref in refs:
        if ref['path'] in result and result[ref['path']] != ref:
            raise ValueError('Native review conflicting source identities')
        # Sources may be PDFs, so do not JSON-decode the closure.
        if _binding(root, root / ref['path']) != ref:
            raise ValueError('Native review source drift')
        result[ref['path']] = deepcopy(ref)
    return list(result.values())


def _implementation_bindings(root):
    code_root = Path(__file__).resolve().parents[2]
    refs = []
    for name in IMPLEMENTATIONS:
        ref = _binding(root, root / 'src/value_investment_agent' / name)
        if sha256_file(code_root / name) != ref['sha256']:
            raise ValueError('Native review implementation differs from executing code')
        refs.append(ref)
    return refs


def _intake(root, candidate_binding, now):
    candidate = _read(root, candidate_binding)
    path = require_inside(root / 'runtime', root / candidate_binding['path'], 'native candidate')
    verified = verify_source_native_candidate(root=root, path=path,
        expected_sha256=candidate_binding['sha256'], now=now)
    if candidate != verified:
        raise ValueError('Native review candidate changed')
    wb_ref = _binding(root, path.parent / 'workbench.json')
    wb = _read(root, wb_ref)
    restored = verify_current_decision_workbench(wb)
    valuation = restored.dependency_objects['valuation']
    if wb['valuation']['confidence'] != '\u4f4e':
        raise ValueError('Native review supports conditional LOW only')
    refs = _closure(root, [candidate_binding, wb_ref, *candidate['source_bindings'],
        *_implementation_bindings(root)])
    template = dict(schema_version=SCHEMA, action='no_order', scope='NATIVE_RESEARCH_ONLY',
        symbol=candidate['symbol'], candidate_binding=deepcopy(candidate_binding),
        model_context=deepcopy(candidate['model_context']),
        valuation_artifact_sha256=valuation_result_sha256(valuation), source_bindings=refs,
        reviewer_id=None, reviewed_at=None, whole_model_approval=None, trust_root_binding=None,
        sequence=None, previous_response_binding=None,
        groups=[dict(id=g['id'], field_paths=g['field_paths'], response=None,
            response_reason=None, confirmed_scope=None) for g in candidate['review_groups']])
    return template, restored, candidate


def prepare_native_signed_review_response(*, root: Path, candidate_path: Path,
                                        candidate_sha256: str, now=None) -> dict:
    """Unsigned v2 template, with no identity, approval, sequence or capability."""
    root = root.resolve()
    ref = dict(path=require_inside(root, candidate_path, 'native candidate').relative_to(root).as_posix(),
        sha256=candidate_sha256)
    template, _, _ = _intake(root, ref, _clock(now))
    _closure(root, template['source_bindings'])
    return template


def _validate_response(root, response_ref, trust_ref, now, *, historical=False):
    envelope, trust = _read(root, response_ref), _read(root, trust_ref)
    if not isinstance(envelope, dict) or set(envelope) != {'payload', 'signature'}:
        raise ValueError('Native review signature envelope invalid')
    payload = envelope['payload']
    if not isinstance(payload, dict) or payload.get('schema_version') != SCHEMA:
        raise ValueError('Unsupported native signed review schema')
    template, restored, candidate = _intake(root, payload.get('candidate_binding'), now)
    if set(payload) != set(template):
        raise ValueError('Native signed review fields incomplete or unknown')
    for name in ('schema_version', 'action', 'scope', 'symbol', 'candidate_binding',
                 'model_context', 'valuation_artifact_sha256', 'source_bindings'):
        if payload[name] != template[name]:
            raise ValueError('Native review exact context mismatch: ' + name)
    if (not isinstance(trust, dict) or set(trust) != {'schema_version', 'reviewer_id', 'public_key',
            'scopes', 'symbols', 'valid_from', 'valid_until'}
            or trust['schema_version'] != 'research-review-transport-trust-root-v1'):
        raise ValueError('Native review trust root contract invalid')
    require_pinned_trust_root(trust)
    if payload['trust_root_binding'] != trust_ref:
        raise ValueError('Native signed trust root path/hash mismatch')
    if (not isinstance(trust['scopes'], list) or not isinstance(trust['symbols'], list)
            or any(not isinstance(s, str) or len(s) != 6 or not s.isdigit() for s in trust['symbols'])
            or set(trust['scopes']) - {'human_group_research', 'human_whole_model', 'human_event_materiality'}
            or not {'human_group_research', 'human_whole_model'} <= set(trust['scopes'])
            or payload['symbol'] not in trust['symbols']
            or not isinstance(payload['reviewer_id'], str) or not payload['reviewer_id'].strip()
            or payload['reviewer_id'] != trust['reviewer_id']):
        raise ValueError('Native reviewer identity or authorization scope mismatch')
    reviewed = _review_time(payload['reviewed_at'], 'native reviewed_at')
    start, end = (_review_time(trust[k], k) for k in ('valid_from', 'valid_until'))
    if (not start <= reviewed <= end or reviewed > now or (not historical and now > end)
            or reviewed < _review_time(candidate['generated_at'], 'candidate generated_at')):
        raise ValueError('Native review timestamp or authorization interval invalid')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust['public_key'])).verify(
            bytes.fromhex(envelope['signature']), PURPOSE + canonical_contract_payload(payload).encode('utf-8'))
    except (InvalidSignature, TypeError, ValueError) as error:
        raise ValueError('Native review signature invalid') from error
    if type(payload['sequence']) is not int or payload['sequence'] < 1:
        raise ValueError('Native review sequence must be a positive integer')
    if not isinstance(payload['groups'], list) or len(payload['groups']) != len(template['groups']):
        raise ValueError('Native whole-model group coverage incomplete')
    for actual, expected in zip(payload['groups'], template['groups']):
        if (not isinstance(actual, dict) or set(actual) != set(expected)
                or actual['id'] != expected['id'] or actual['field_paths'] != expected['field_paths']
                or actual['response'] != 'VERIFIED'
                or any(not isinstance(actual[k], str) or not actual[k].strip()
                       for k in ('response_reason', 'confirmed_scope'))):
            raise ValueError('Native whole-model groups must be exactly verified')
    raw = payload['whole_model_approval']
    if (not isinstance(raw, dict) or raw.get('price_assessment_eligible') is not False
            or raw.get('authenticated_transport_binding') is not None):
        raise ValueError('Native whole-model requires unbound research-only approval')
    approval = human_research_approval_from_payload(raw)
    if (approval.as_policy() != raw or approval.reviewer_type != 'human_research_lead'
            or approval.reviewer_id != payload['reviewer_id'] or approval.reviewed_at != reviewed
            or approval.created_at is not None and approval.created_at > now
            or approval.symbol != payload['symbol'] or approval.security_id != payload['symbol']
            or approval.profile_id != payload['model_context']['profile_id']
            or approval.review_as_of.isoformat() < payload['model_context']['research_as_of']
            or approval.decision not in {'APPROVED_RESEARCH_ONLY', 'APPROVED_CONDITIONAL_LOW_CONFIDENCE'}):
        raise ValueError('Native whole-model reviewer or research scope invalid')
    package = _read(root, candidate['source_package_binding'])
    for ref in approval.evidence_refs:
        matches = [row for row in package['sources'] if row['id'] == ref.get('id')
            and row.get('local_path') == ref.get('path') and row['sha256'] == ref.get('sha256')]
        if len(matches) != 1:
            raise ValueError('Native approval evidence must bind an existing package source')
        if dict(path=ref['path'], sha256=ref['sha256']) not in template['source_bindings']:
            raise ValueError('Native approval evidence is outside the consumed closure')
    for role, field in (('valuation', 'valuation_artifact_id'), ('research_case', 'research_case_id'),
                       ('financial_facts', 'facts_artifact_id'), ('valuation_assumptions', 'assumption_set_id')):
        if getattr(approval, field) != restored.dependencies[role].artifact_id:
            raise ValueError('Native whole-model artifact identity mismatch')
    decision = resolve_human_research_approval(approval, restored.dependency_objects['valuation'],
        model_id=payload['model_context']['model_id'],
        research_case_payload=restored.dependencies['research_case'].envelope.payload_object(),
        facts_payload=restored.dependencies['financial_facts'].envelope.payload_object(),
        assumptions_payload=restored.dependencies['valuation_assumptions'].envelope.payload_object())
    if not decision.approved or not decision.valuation_bound or not decision.dependencies_bound:
        raise ValueError('Native whole-model approval does not bind actual model')
    _closure(root, [response_ref, trust_ref, *template['source_bindings']])
    require_pinned_trust_root(_read(root, trust_ref))
    return payload, approval


def _journal_dir(root, candidate_ref):
    # Full SHA, not a truncated collision domain; path identity is checked in each record.
    if (not isinstance(candidate_ref, dict) or set(candidate_ref) != {'path', 'sha256'}
            or not isinstance(candidate_ref['path'], str)
            or not isinstance(candidate_ref['sha256'], str) or len(candidate_ref['sha256']) != 64
            or any(c not in '0123456789abcdef' for c in candidate_ref['sha256'])):
        raise ValueError('Native journal requires a canonical candidate SHA-256')
    path = require_inside(root / 'runtime', root / candidate_ref['path'], 'native candidate')
    if path.relative_to(root).as_posix() != candidate_ref['path']:
        raise ValueError('Native journal candidate path must be canonical')
    expected = f"{NAMESPACE}/{candidate_ref['sha256']}"
    directory = require_inside(root, root / expected, 'native journal')
    if directory.relative_to(root).as_posix() != expected:
        raise ValueError('Native journal namespace must not be redirected')
    return directory


def _history(root, candidate_ref, now):
    directory = _journal_dir(root, candidate_ref)
    previous, reviewed, reviewer = None, None, None
    records = []
    for path in sorted(directory.glob('*.json')):
        record_ref = _binding(root, path)
        record = _read(root, record_ref)
        if (not isinstance(record, dict) or set(record) != {'schema_version', 'action', 'receipt_binding'}
                or record['schema_version'] != JOURNAL_SCHEMA or record['action'] != 'no_order'):
            raise ValueError('Native journal completion contract invalid')
        receipt = _read(root, record['receipt_binding'])
        if (not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS
                or receipt['schema_version'] != RECEIPT_SCHEMA or receipt['action'] != 'no_order'
                or receipt['scope'] != 'NATIVE_RESEARCH_ONLY'
                or receipt['candidate_binding'] != candidate_ref):
            raise ValueError('Native journal consumption binding invalid')
        payload, approval = _validate_response(root, receipt['response_binding'], receipt['trust_root_binding'],
            now, historical=True)
        sequence = len(records) + 1
        if (payload['candidate_binding'] != candidate_ref or payload['sequence'] != sequence
                or receipt['sequence'] != sequence or type(receipt['sequence']) is not int
                or path.name != f'{sequence:08d}.json'
                or payload['previous_response_binding'] != previous
                or receipt['previous_response_binding'] != previous
                or previous is not None and (payload['reviewer_id'] != reviewer
                    or _review_time(payload['reviewed_at'], 'reviewed') <= reviewed)):
            raise ValueError('Native journal predecessor/sequence/identity mismatch')
        consumed = _review_time(receipt['consumed_at'], 'native consumed_at')
        if not _review_time(payload['reviewed_at'], 'reviewed') <= consumed <= now:
            raise ValueError('Native journal actual availability invalid')
        if receipt['source_bindings'] != payload['source_bindings']:
            raise ValueError('Native consumption source closure mismatch')
        _closure(root, [record_ref, record['receipt_binding'], *receipt['source_bindings']])
        records.append((record_ref, record, receipt, payload, approval))
        previous = receipt['response_binding']
        reviewed = _review_time(payload['reviewed_at'], 'reviewed')
        reviewer = payload['reviewer_id']
    _recheck_history(root, candidate_ref, records)
    return records


def _recheck_history(root, candidate_ref, records):
    paths = [ref['path'] for ref, _, _, _, _ in records]
    actual = [p.relative_to(root).as_posix() for p in sorted(_journal_dir(root, candidate_ref).glob('*.json'))]
    if actual != paths:
        raise ValueError('Native journal head changed during final read')
    for record_ref, record, receipt, _, _ in records:
        _closure(root, [record_ref, record['receipt_binding'], receipt['response_binding'],
            receipt['trust_root_binding'], *receipt['source_bindings']])
        require_pinned_trust_root(_read(root, receipt['trust_root_binding']))


def consume_native_signed_review_response(*, root: Path, candidate_path: Path, candidate_sha256: str,
    response_path: Path, response_sha256: str, trust_root_path: Path, trust_root_sha256: str,
    output_dir: Path, now=None) -> dict:
    """Commit one verified transport atomically. Existing/incomplete outputs fail closed."""
    root, clock = root.resolve(), _clock(now)
    candidate_ref = dict(path=require_inside(root / 'runtime', candidate_path, 'native candidate').relative_to(root).as_posix(),
        sha256=candidate_sha256)
    response_ref = dict(path=require_inside(root, response_path, 'native response').relative_to(root).as_posix(), sha256=response_sha256)
    trust_ref = dict(path=require_inside(root, trust_root_path, 'native trust root').relative_to(root).as_posix(), sha256=trust_root_sha256)
    output_base = root / CONSUMPTIONS
    if output_base.resolve().relative_to(root).as_posix() != CONSUMPTIONS:
        raise ValueError('Native consumption namespace must not be redirected')
    target = require_inside(output_base, output_dir, 'native consumption output')
    if target == output_base:
        raise ValueError('Native consumption output requires a new transaction directory')
    directory = _journal_dir(root, candidate_ref)
    with InterProcessLock(directory / 'transaction.lock'):
        payload, _ = _validate_response(root, response_ref, trust_ref, clock)
        if payload['candidate_binding'] != candidate_ref:
            raise ValueError('Native signed candidate path/hash identity mismatch')
        history = _history(root, candidate_ref, clock)
        previous = history[-1][2]['response_binding'] if history else None
        if (payload['sequence'] != len(history) + 1 or payload['previous_response_binding'] != previous
                or history and (payload['reviewer_id'] != history[-1][3]['reviewer_id']
                    or _review_time(payload['reviewed_at'], 'reviewed') <=
                       _review_time(history[-1][3]['reviewed_at'], 'previous reviewed'))):
            raise ValueError('Native review stale head/replay/predecessor mismatch')
        if target.exists():
            raise FileExistsError('Native consumption output must be new; no automatic resume')
        target.mkdir(parents=True)
        receipt = dict(schema_version=RECEIPT_SCHEMA, action='no_order', scope='NATIVE_RESEARCH_ONLY',
            candidate_binding=candidate_ref, response_binding=response_ref, trust_root_binding=trust_ref,
            sequence=payload['sequence'], previous_response_binding=previous,
            consumed_at=clock.isoformat(), source_bindings=payload['source_bindings'])
        receipt_path = target / 'receipt.json'
        write_new_json(receipt_path, receipt)
        receipt_ref = _binding(root, receipt_path)
        _validate_response(root, response_ref, trust_ref, clock)
        if _history(root, candidate_ref, clock) != history:
            raise ValueError('Native journal changed during consumption')
        _closure(root, [receipt_ref, response_ref, trust_ref, *receipt['source_bindings']])
        # This immutable record, not the output directory, grants completion.
        write_new_json(directory / f"{payload['sequence']:08d}.json",
            dict(schema_version=JOURNAL_SCHEMA, action='no_order', receipt_binding=receipt_ref))
        return dict(schema_version=RECEIPT_SCHEMA, action='no_order', consumption_binding=receipt_ref,
            scope='NATIVE_RESEARCH_ONLY', price_admitted=False, registered_current_case_changed=False)


def _completed(root, candidate_ref, now, *, consumption_ref=None, response_ref=None):
    history = _history(root, candidate_ref, now)
    if not history:
        raise ValueError('Native review has no completed authenticated journal')
    _, record, receipt, payload, approval = history[-1]
    if (consumption_ref is not None and record['receipt_binding'] != consumption_ref
            or response_ref is not None and receipt['response_binding'] != response_ref):
        raise ValueError('Native approval is not the current completed head')
    # Current use must still have a valid authorization interval.
    _validate_response(root, receipt['response_binding'], receipt['trust_root_binding'], now)
    _recheck_history(root, candidate_ref, history)
    return receipt, payload, approval


def _verify_approval_in_transaction(root, approval, clock, *, consumption_ref=None):
    binding = getattr(approval, 'authenticated_transport_binding', None)
    if (not isinstance(binding, dict) or set(binding) != {'schema_version', 'transport',
            'response_binding', 'candidate_binding', 'trust_root_binding'}
            or binding['schema_version'] != 'human-research-approval-authenticated-transport-v1'
            or binding['transport'] != 'SIGNED_PENDING_REVIEW_RESPONSE'):
        raise ValueError('Native approval requires complete authenticated transport')
    receipt, payload, signed = _completed(root, binding['candidate_binding'], clock,
        response_ref=binding['response_binding'], consumption_ref=consumption_ref)
    if receipt['trust_root_binding'] != binding['trust_root_binding']:
        raise ValueError('Native approval trust binding drift')
    if replace(approval, authenticated_transport_binding=None, verified_transport=None).as_policy() != signed.as_policy():
        raise ValueError('Native approval differs from signed whole-model receipt')
    _closure(root, [receipt['response_binding'], receipt['trust_root_binding'], *payload['source_bindings']])
    require_pinned_trust_root(_read(root, receipt['trust_root_binding']))
    return mint_verified_human_research_approval_transport(signed, binding)


def verify_native_human_approval_provenance(root: Path, approval, *, now=None):
    """Cold-read verification before reminting the existing nonserializable capability."""
    root, clock = root.resolve(), _clock(now)
    binding = getattr(approval, 'authenticated_transport_binding', None)
    if not isinstance(binding, dict):
        raise ValueError('Native approval requires authenticated transport')
    with InterProcessLock(_journal_dir(root, binding.get('candidate_binding')) / 'transaction.lock'):
        return _verify_approval_in_transaction(root, approval, clock)


def run_native_reviewed_research(*, root: Path, candidate_binding: dict, consumption_binding: dict,
                                now=None) -> dict:
    """Actual typed service and DI cold restoration; no registry, price or publication writes."""
    root, clock = root.resolve(), _clock(now)
    candidate_binding, consumption_binding = deepcopy(candidate_binding), deepcopy(consumption_binding)
    with InterProcessLock(_journal_dir(root, candidate_binding) / 'transaction.lock'):
        receipt, payload, approval = _completed(root, candidate_binding, clock,
            consumption_ref=consumption_binding)
        transport = dict(schema_version='human-research-approval-authenticated-transport-v1',
            transport='SIGNED_PENDING_REVIEW_RESPONSE', response_binding=receipt['response_binding'],
            candidate_binding=candidate_binding, trust_root_binding=receipt['trust_root_binding'])
        approval = mint_verified_human_research_approval_transport(approval, transport)
        candidate = _read(root, candidate_binding)
        package = _read(root, candidate['source_package_binding'])
        descriptor = build_descriptor(package, root=root)
        spec = build_research_run_spec(descriptor)
        original = descriptor.as_policy()
        run_input = dict(schema_version='source-native-reviewed-run-input-v2',
            original_input_descriptor_sha256=descriptor.input_sha256,
            candidate_binding=candidate_binding, consumption_binding=consumption_binding,
            model_context=payload['model_context'], available_at=clock.isoformat(), computed_at=clock.isoformat())
        run_input_sha = sha256(canonical_contract_payload(run_input).encode('utf-8')).hexdigest()
        spec = replace(spec, human_research_approval=approval,
            research_case_payload=original['research_case'], facts_payload=original['facts'],
            assumptions_payload=original['assumptions'], available_at=clock, computed_at=clock,
            input_descriptor_sha256=run_input_sha)
        outcome = ResearchApplicationService(now_utc=lambda: clock).run_company_research(spec)
        result = _serialize_outcome(outcome)
        template, _, _ = _intake(root, candidate_binding, clock)
        if valuation_result_sha256(outcome.valuation) != payload['valuation_artifact_sha256']:
            raise ValueError('Native reviewed service valuation changed')
        wb = dict(schema_version='product-current-workbench-request-v1', generated_at=clock.isoformat(),
            symbol=candidate['symbol'], action='no_order', command='native_reviewed_research',
            suggested_state='NO_ACTION', portfolio_input_status='BLOCKED_PRIVATE_INPUT',
            position_guidance=None, schedule_gate=None, canonical_workbook_written=False,
            research_status=result['status'], research_blockers=result['blockers'],
            input_descriptor_sha256=run_input_sha)
        for field in ('current_status', 'valuation', 'price_bridge', 'price_attractiveness',
                      'pre_decision_eligibility', 'decision_recommendation', 'artifact_bundle'):
            wb[field] = result[field]
        # Already locked: use the same full verifier without reacquiring an OS lock.
        def verify_in_transaction(value):
            if getattr(value, 'authenticated_transport_binding', None) != transport:
                raise ValueError('Native restored transport identity differs')
            return _verify_approval_in_transaction(root, value, clock, consumption_ref=consumption_binding)
        restored = verify_current_decision_workbench(wb,
            human_approval_provenance_verifier=verify_in_transaction)
        if (restored.recommendation.action != 'no_order'
                or outcome.quote_snapshot is not None
                or wb['price_bridge'] is not None and (wb['price_bridge']['current_price'] is not None
                    or wb['price_bridge']['quote_date'] is not None
                    or wb['price_bridge']['bridge_status'] == 'READY')
                or current_recommendation_type(restored.recommendation) != 'NO_ACTION'):
            raise ValueError('Native reviewed result must remain research-only/no-order')
        _completed(root, candidate_binding, clock, consumption_ref=consumption_binding)
        _closure(root, [consumption_binding, *template['source_bindings']])
        wb['native_review'] = dict(schema_version='source-native-reviewed-run-v2', scope='RESEARCH_ONLY',
            candidate_binding=deepcopy(candidate_binding), consumption_binding=deepcopy(consumption_binding),
            original_model_context=payload['model_context'], review_available_at=receipt['consumed_at'],
            derived_run_input=run_input, derived_run_input_sha256=run_input_sha,
            research_as_of=spec.as_of.isoformat(), valuation_date=spec.valuation_date.isoformat(),
            run_available_at=clock.isoformat(), price_admitted=False, formal_eligibility=False,
            research_gate=result['gate'],
            strategy_approved=False, primary_registered=False, action='no_order')
        return wb
