"""Authenticated materiality transport using the existing research trust registry.

Preparation and import never approve G3, admit research, or authorize orders.
"""
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ...event_materiality import event_materiality_review_from_payload
from ...m1_valuation_package_builder import build_descriptor, build_validity
from ...research_input import build_research_run_spec, finalize_input_descriptor
from ...research_run_contract import canonical_contract_payload
from ...infrastructure.evidence.trust_root_registry import require_pinned_trust_root
from .common import require_inside, sha256_file, sha256_bytes
from .research_reviews import (
    _append_review_json, _strict_review_json, _review_time,
    build_research_review_model_context,
)

MATERIALITY_RESPONSE_PURPOSE = b'value-investment/materiality-research-response/v1\x00'
# No legacy materiality transport packet is admitted without reviewed exact bytes.
_PINNED_LEGACY_MATERIALITY_PACKET_SHA256 = frozenset()


def _binding(root, path, digest=None):
    path = require_inside(root, Path(path), 'materiality original')
    actual = sha256_file(path)
    if digest is not None and actual != digest:
        raise ValueError('materiality original hash mismatch')
    return dict(path=path.relative_to(root).as_posix(), sha256=actual)


def _load(root, binding):
    path = root / binding['path']
    _binding(root, path, binding['sha256'])
    return _strict_review_json(path)


def _context_key(context):
    return sha256_bytes(canonical_contract_payload(context).encode('utf-8'))


def build_materiality_review_descriptor(*, root, package_binding, scan_binding):
    """Validate frozen research first; supplement only its typed validity input.

    Post-cutoff disclosures are not historical research sources. In particular,
    never add them to a source-bound package's pre-cutoff source catalog.
    """
    from .source_bound_inputs import verify_package_local_sources
    package = _load(root, package_binding)
    _load(root, scan_binding)
    verify_package_local_sources(root, package)
    contracts = {row.get('retention_contract') for row in
                 package.get('facts', {}).get('scenario_inputs', {}).values()
                 if isinstance(row, dict)}
    from ..research.v4_input_adapter import RETENTION_CONTRACT
    if RETENTION_CONTRACT in contracts:
        if contracts != {RETENTION_CONTRACT}:
            raise ValueError('materiality rejects mixed terminal scenario contracts')
        from ..research.v4_input_adapter import build_descriptor_for_package
        original = build_descriptor_for_package(package, root=root)
    else:
        original = build_descriptor(package, root=root)
    validity = package.get('model_validity_input')
    if not isinstance(validity, dict) or validity.get('events'):
        raise ValueError('materiality handoff needs non-conflicting validity inputs')
    existing_scan = validity.get('event_scan_ref') or {}
    if all(existing_scan.get(key) == scan_binding[key] for key in ('path', 'sha256')):
        return original
    ref = dict(id='daily-event-' + scan_binding['sha256'], symbol=package['symbol'], **scan_binding)
    supplemented = build_validity(dict(validity, event_scan_ref=ref,
                                       event_scan_evidence_refs=[ref]), root=root)
    return finalize_input_descriptor(replace(original, model_validity_input=supplemented,
                                             input_sha256=None))


def prepare_materiality_review_handoff(*, root, package_path, package_sha256,
                                      scan_path, scan_sha256):
    """Bind an effective descriptor without mutating the original research cutoff."""
    root = Path(root).resolve()
    package_ref = _binding(root, package_path, package_sha256)
    scan_ref = _binding(root, scan_path, scan_sha256)
    package = _load(root, package_ref)
    symbol = package['symbol']
    validity = package.get('model_validity_input')
    if not isinstance(validity, dict) or validity.get('events'):
        raise ValueError('materiality handoff needs non-conflicting validity inputs')
    ref = dict(id='daily-event-' + scan_sha256, symbol=symbol, **scan_ref)
    descriptor = build_materiality_review_descriptor(root=root,
        package_binding=package_ref, scan_binding=scan_ref)
    spec = build_research_run_spec(descriptor)
    scan = spec.model_validity_input.event_scan
    if scan is None or scan.symbol != symbol or scan.coverage_status != 'COMPLETE':
        raise ValueError('materiality handoff requires complete acquired scan coverage')
    if scan.validity_from != spec.model_validity_input.valid_from:
        raise ValueError('materiality scan validity start mismatch')
    for evidence in scan.evidence_refs:
        if not evidence.get('path') or not evidence.get('sha256'):
            raise ValueError('materiality scan requires retained hash-bound acquisition evidence')
        _binding(root, root / evidence['path'], evidence['sha256'])
    announcements = []
    for item in scan.announcements:
        sources = []
        for evidence in item.evidence_refs:
            if evidence.get('path') and evidence.get('sha256'):
                _binding(root, root / evidence['path'], evidence['sha256'])
                sources.append(dict(evidence))
        if not sources:
            raise ValueError('materiality announcement requires hash-bound local original')
        announcements.append(dict(announcement_id=item.announcement_id,
            published_at=item.published_at.isoformat(), title=item.title,
            source_url=item.source_url, evidence_refs=sources))
    if not announcements:
        raise ValueError('materiality handoff requires acquired announcements')
    if spec.model_version == 'residual-income-equity-path-v4':
        from ..research.v4_review_context import build_v4_research_review_model_context
        context = build_v4_research_review_model_context(descriptor=descriptor, spec=spec)
    else:
        context = build_research_review_model_context(descriptor=descriptor, spec=spec)
    fixed = dict(schema_version='materiality-review-handoff-v1', action='no_order',
        symbol=symbol, package_binding=package_ref, scan_binding=scan_ref,
        model_context=context,
        scan_window=dict(scan_from=scan.scan_from.isoformat(), scan_to=scan.scan_to.isoformat(),
                         retrieved_at=scan.retrieved_at.isoformat()),
        announcements=announcements,
        signature_contract=dict(algorithm='Ed25519', canonicalization='canonical_contract_payload',
            purpose_hex=MATERIALITY_RESPONSE_PURPOSE.hex(), required_scope='human_event_materiality',
            trust_schema='research-review-transport-trust-root-v1',
            envelope_fields=['payload', 'signature']))
    draft = dict(schema_version='post-m1-event-materiality-v1', action='no_order',
        review_id=None, symbol=symbol, scan_id=ref['id'], scan_sha256=scan_sha256,
        scan_from=scan.scan_from.isoformat(), scan_to=scan.scan_to.isoformat(),
        reviewed_at=None, review_as_of=None, reviewer_type='human_research_lead', reviewer_id=None,
        reviewer_authorization_ref=None, model_context=context, evidence_refs=[ref],
        decisions=[dict(schema_version='post-m1-event-materiality-v1', action='no_order',
            event_decision_id=None, symbol=symbol, announcement_id=item['announcement_id'],
            title=item['title'], published_at=item['published_at'],
            source_ref={key: value for key, value in item['evidence_refs'][0].items() if key != 'sha256'},
            source_sha256=item['evidence_refs'][0]['sha256'],
            machine_candidate_reason='Acquired announcement; independent human classification required',
            human_decision=None, affected_domains=[], affected_fact_fields=[], affected_assumptions=[],
            affected_artifacts=[], requires_recalculation=None, requires_model_stale=None,
            requires_followup=None, reviewed_at=None, reviewer_type='human_research_lead',
            reviewer_id=None, reviewer_authorization_ref=None, review_notes=[], decision_version='20260923.1')
            for item in announcements])
    response = dict(schema_version='materiality-review-response-v1', action='no_order',
        symbol=symbol, handoff_sha256=_context_key(fixed), model_context=context,
        reviewer_id=None, reviewed_at=None, event_materiality=draft)
    return dict(**fixed, unsigned_response=response)


def _validate(root, handoff, envelope, trust, *, historical=False):
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    expected = prepare_materiality_review_handoff(root=root,
        package_path=root / handoff['package_binding']['path'],
        package_sha256=handoff['package_binding']['sha256'],
        scan_path=root / handoff['scan_binding']['path'],
        scan_sha256=handoff['scan_binding']['sha256'])
    if handoff != expected:
        raise ValueError('materiality handoff descriptor, window or original drift')
    require_pinned_trust_root(trust)
    if (set(envelope) != {'payload', 'signature'} or
            set(trust) != {'schema_version', 'reviewer_id', 'public_key', 'scopes',
                           'symbols', 'valid_from', 'valid_until'} or
            trust['schema_version'] != 'research-review-transport-trust-root-v1' or
            not isinstance(trust['scopes'], list) or
            'human_event_materiality' not in trust['scopes'] or
            set(trust['scopes']) - {'human_event_materiality', 'human_group_research', 'human_whole_model'} or
            not isinstance(trust['symbols'], list) or handoff['symbol'] not in trust['symbols']):
        raise ValueError('materiality trust scope mismatch')
    payload = envelope['payload']
    template = handoff['unsigned_response']
    if not isinstance(payload, dict) or set(payload) != set(template):
        raise ValueError('materiality response fields mismatch')
    for key in ('schema_version', 'action', 'symbol', 'handoff_sha256', 'model_context'):
        if payload[key] != template[key]:
            raise ValueError('materiality response exact context mismatch: ' + key)
    if not payload['reviewer_id'] or payload['reviewer_id'] != trust['reviewer_id']:
        raise ValueError('materiality reviewer mismatch')
    reviewed = _review_time(payload['reviewed_at'], 'materiality reviewed_at')
    now = datetime.now(timezone.utc)
    start, end = (_review_time(trust[k], k) for k in ('valid_from', 'valid_until'))
    if (not start <= reviewed <= end or reviewed > now or
            (not historical and now > end) or
            reviewed < _review_time(handoff['scan_window']['retrieved_at'], 'scan observation')):
        raise ValueError('materiality review authorization time mismatch')
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(trust['public_key'])).verify(
            bytes.fromhex(envelope['signature']), MATERIALITY_RESPONSE_PURPOSE +
            canonical_contract_payload(payload).encode('utf-8'))
    except (InvalidSignature, TypeError, ValueError) as error:
        raise ValueError('materiality response signature invalid') from error
    raw_review = payload['event_materiality']
    if (not isinstance(raw_review, dict) or
            any(not isinstance(raw_review.get(key), str) or not raw_review[key].strip()
                for key in ('review_id', 'scan_id', 'reviewer_id')) or
            not isinstance(raw_review.get('decisions'), list)):
        raise ValueError('materiality review requires explicit typed identity and decisions')
    for item in raw_review['decisions']:
        if (not isinstance(item, dict) or
                any(type(item.get(key)) is not bool for key in
                    ('requires_recalculation', 'requires_model_stale', 'requires_followup')) or
                any(not isinstance(item.get(key), str) or not item[key].strip() for key in
                    ('event_decision_id', 'reviewer_id', 'human_decision')) or
                not isinstance(item.get('review_notes'), list) or not item['review_notes'] or
                any(not isinstance(note, str) or not note.strip() for note in item['review_notes'])):
            raise ValueError('materiality decisions require typed flags, identity and human rationale')
    review = event_materiality_review_from_payload(raw_review)
    if (payload['event_materiality'].get('model_context') != handoff['model_context'] or
            review.symbol != handoff['symbol'] or
            review.scan_sha256 != handoff['scan_binding']['sha256'] or
            review.scan_from.isoformat() != handoff['scan_window']['scan_from'] or
            review.scan_to.isoformat() != handoff['scan_window']['scan_to'] or
            review.reviewed_at != reviewed or review.reviewer_id != payload['reviewer_id'] or
            review.reviewer_type != 'human_research_lead'):
        raise ValueError('materiality typed review binding mismatch')
    originals = {item['announcement_id']: item for item in handoff['announcements']}
    if set(originals) != {item.announcement_id for item in review.decisions}:
        raise ValueError('materiality decisions must cover every announcement')
    for item in review.decisions:
        original = originals[item.announcement_id]
        if (item.published_at.isoformat() != original['published_at'] or
                item.title != original['title'] or item.reviewer_id != payload['reviewer_id'] or
                item.reviewer_type != 'human_research_lead' or item.reviewed_at != reviewed or
                not any(item.source_sha256 == ref['sha256'] and
                        item.source_ref.get('path') == ref['path'] and
                        item.source_ref.get('id') == ref.get('id')
                        for ref in original['evidence_refs'])):
            raise ValueError('materiality announcement identity, source or reviewer mismatch')
    return payload


def consume_materiality_review_response(*, root, handoff_path, handoff_sha256,
        response_path, response_sha256, trust_root_path, trust_root_sha256, output_dir,
        resume_incomplete=False, incomplete_consumption_sha256=None):
    """Authenticate once, append originals-bound receipt, emit the existing v2 packet."""
    root = Path(root).resolve()
    bindings = {role: _binding(root, path, digest) for role, path, digest in (
        ('handoff', handoff_path, handoff_sha256), ('response', response_path, response_sha256),
        ('trust_root', trust_root_path, trust_root_sha256))}
    handoff, envelope, trust = (_load(root, bindings[key]) for key in ('handoff', 'response', 'trust_root'))
    payload = _validate(root, handoff, envelope, trust)
    output = require_inside(root / 'runtime', Path(output_dir), 'materiality consumption')
    history = root / 'runtime/materiality-review-responses' / _context_key(handoff['model_context'])
    checkpoint_path = output / 'incomplete-consumption.json'
    checkpoint = dict(schema_version='materiality-incomplete-consumption-v1', action='no_order',
        authenticated_materiality_binding=bindings, model_context=handoff['model_context'],
        output_directory=output.relative_to(root).as_posix())
    if (history / 'completion.json').exists():
        raise ValueError('materiality response replay: already completed')
    if resume_incomplete:
        if (not incomplete_consumption_sha256 or not checkpoint_path.is_file() or
                sha256_file(checkpoint_path) != incomplete_consumption_sha256 or
                _strict_review_json(checkpoint_path) != checkpoint):
            raise ValueError('materiality resume requires exact original incomplete consumption')
    elif incomplete_consumption_sha256 is not None or output.exists() or history.exists():
        raise ValueError('materiality response replay or existing context consumption; explicit resume required')
    output.mkdir(parents=True, exist_ok=resume_incomplete)
    _append_review_json(checkpoint_path, checkpoint)
    # Atomic append claims exact inputs/output. A failed write remains explicitly resumable.
    history.mkdir(parents=True, exist_ok=True)
    _append_review_json(history / 'claim.json', _binding(root, checkpoint_path))
    artifact = output / 'event-materiality.json'
    _append_review_json(artifact, payload['event_materiality'])
    packet_path = output / 'research-reviews.json'
    packet = dict(schema_version='shared-research-review-inputs-v2', action='no_order',
        symbol=handoff['symbol'], bindings=dict(event_materiality=_binding(root, artifact)),
        authenticated_materiality_binding=bindings)
    _append_review_json(packet_path, packet)
    # Recheck signed originals and acquired sources before committing the receipt.
    _validate(root, _load(root, bindings['handoff']), _load(root, bindings['response']),
              _load(root, bindings['trust_root']))
    receipt = dict(schema_version='materiality-review-consumption-v1', action='no_order',
        authenticated_materiality_binding=bindings, model_context=handoff['model_context'],
        review_packet_binding=_binding(root, packet_path), authenticated_reviewer=payload['reviewer_id'],
        research_admitted=False, whole_model_approved=False, price_admitted=False)
    receipt_path = output / 'consumption.json'
    _append_review_json(receipt_path, receipt)
    _append_review_json(history / 'completion.json', _binding(root, receipt_path))
    return receipt


def verify_authenticated_materiality(*, root, packet, model_context, materiality, packet_sha256=None):
    """Revalidate current trust (including revocation) at the actual v2 consumer."""
    root = Path(root).resolve()
    record = root / 'runtime/materiality-review-responses' / _context_key(model_context) / 'completion.json'
    bindings = packet.get('authenticated_materiality_binding')
    if (bindings is None and not record.parent.exists() and
            packet_sha256 in _PINNED_LEGACY_MATERIALITY_PACKET_SHA256):
        return  # Exact frozen legacy bytes only; never authorize a new unsigned context.
    if bindings is None or not record.is_file():
        raise ValueError('materiality authenticated provenance stripped or consumption incomplete')
    receipt = _load(root, _strict_review_json(record))
    if (receipt.get('schema_version') != 'materiality-review-consumption-v1' or
            receipt.get('action') != 'no_order' or receipt.get('model_context') != model_context or
            receipt.get('authenticated_materiality_binding') != bindings):
        raise ValueError('materiality completion identity mismatch')
    committed_packet = _load(root, receipt['review_packet_binding'])
    # Independently validated G3 may be combined with this materiality packet.
    # Its addition must not change any authenticated materiality contract field.
    if (any(committed_packet.get(key) != packet.get(key) for key in
            ('schema_version', 'action', 'symbol', 'authenticated_materiality_binding')) or
            committed_packet['bindings']['event_materiality'] != packet['bindings']['event_materiality']):
        raise ValueError('materiality completed packet mismatch')
    handoff, envelope, trust = (_load(root, bindings[key]) for key in ('handoff', 'response', 'trust_root'))
    payload = _validate(root, handoff, envelope, trust, historical=True)
    if (payload['model_context'] != model_context or payload['event_materiality'] != materiality or
            receipt.get('authenticated_reviewer') != payload['reviewer_id']):
        raise ValueError('materiality authenticated artifact mismatch')


def registered_materiality_handoff(*, root, symbol, today):
    """Existing Web/quote entry: explicit registered supplement, never filename discovery."""
    from .incremental_validity import registered_package, read_bound_json, load_incremental_scan_binding
    from .quote_bridge import POINTER_PATH
    from datetime import date

    root = Path(root).resolve()
    pointer = _strict_review_json(root / POINTER_PATH)
    entry = pointer.get('quotes', {}).get(symbol, {})
    binding_ref = entry.get('incremental_validity_binding')
    if not binding_ref:
        return dict(status='NO_REGISTERED_INCREMENTAL_SCAN', action='no_order', approval_granted=False,
                    g3_approval_granted=False, steps=[])
    package_ref, _ = registered_package(root, symbol)
    _, binding = read_bound_json(root, binding_ref, 'materiality incremental binding')
    scan_ref = load_incremental_scan_binding(root=root, symbol=symbol, binding_ref=binding_ref,
        package_path=root / package_ref['path'], package_sha256=package_ref['sha256'],
        review_cutoff=date.fromisoformat(binding['review_cutoff']), today=today)
    _, scan_payload = read_bound_json(root, scan_ref, 'materiality acquired scan')
    if not scan_payload.get('announcements'):
        return dict(status='NO_MATERIALITY_ANNOUNCEMENTS', action='no_order',
                    approval_granted=False, g3_approval_granted=False, steps=[],
                    scan_binding=scan_ref, incremental_binding=binding_ref)
    handoff = prepare_materiality_review_handoff(root=root,
        package_path=root / package_ref['path'], package_sha256=package_ref['sha256'],
        scan_path=root / scan_ref['path'], scan_sha256=scan_ref['sha256'])
    handoff_path = root / 'runtime/research-review-handoffs/materiality' / (
        handoff['unsigned_response']['handoff_sha256'] + '.json')
    _append_review_json(handoff_path, handoff)
    handoff_ref = _binding(root, handoff_path)
    context = handoff['model_context']
    record = root / 'runtime/materiality-review-responses' / _context_key(context) / 'completion.json'
    result = dict(status='EXTERNAL_SIGNATURE_REQUIRED', action='no_order',
        approval_granted=False, g3_approval_granted=False, handoff_binding=handoff_ref,
        incremental_binding=binding_ref, model_context=context, scan_binding=scan_ref,
        scan_window=handoff['scan_window'], announcements=handoff['announcements'],
        unsigned_response=handoff['unsigned_response'], signature_contract=handoff['signature_contract'],
        commands=dict(consume_signed_response='python scripts/current/review_materiality.py consume '
            f'--handoff "{handoff_ref["path"]}" --handoff-sha256 {handoff_ref["sha256"]} '
            '--response <SIGNED_RESPONSE_PATH> --response-sha256 <SIGNED_RESPONSE_SHA256> '
            '--trust-root <PINNED_TRUST_ROOT_PATH> --trust-root-sha256 <PINNED_TRUST_ROOT_SHA256> '
            '--output <NEW_RUNTIME_DIRECTORY>',
            recompute=f'python scripts/current/review_materiality.py recheck --symbol {symbol} '
            '--output <NEW_RUNTIME_RESULT_PATH>'),
        steps=[dict(id='REVIEW', action='Review each acquired original and classify every announcement independently.'),
               dict(id='SIGN', action='An authorized external reviewer signs the exact payload; never upload private keys.'),
               dict(id='IMPORT', action='Import the response, then recheck and publish; materiality never grants G3 or orders.')],
        publication_required=True)
    if record.parent.exists():
        if not record.is_file():
            raise ValueError('materiality consumption incomplete; audit required')
        receipt_ref = _strict_review_json(record)
        receipt = _load(root, receipt_ref)
        packet_ref = receipt['review_packet_binding']
        packet = _load(root, packet_ref)
        artifact = _load(root, packet['bindings']['event_materiality'])
        verify_authenticated_materiality(root=root, packet=packet, model_context=context, materiality=artifact)
        descriptor = build_materiality_review_descriptor(root=root,
            package_binding=package_ref, scan_binding=scan_ref)
        from .research_reviews import attach_research_reviews
        attach_research_reviews(root=root, descriptor=descriptor, spec=build_research_run_spec(descriptor),
            path=root / packet_ref['path'], expected_sha256=packet_ref['sha256'],
            event_sha256=scan_ref['sha256'], require_model_binding=True)
        result.update(status='AUTHENTICATED_RESPONSE_IMPORTED', review_packet_binding=packet_ref,
                      consumption_binding=receipt_ref)
    return result


def apply_registered_materiality_review(*, root, symbol, today, fallback):
    """Replay authenticated decisions through the existing typed validity evaluator."""
    from datetime import date
    from ...model_validity import evaluate_model_validity
    from .incremental_validity import read_bound_json

    route = registered_materiality_handoff(root=root, symbol=symbol, today=today)
    if route['status'] != 'AUTHENTICATED_RESPONSE_IMPORTED':
        return fallback, route
    _, binding = read_bound_json(root, route['incremental_binding'], 'materiality increment')
    _, observation = read_bound_json(root, binding['observation_ref'], 'materiality observation')
    descriptor = build_materiality_review_descriptor(root=root,
        package_binding=binding['package_ref'], scan_binding=binding['scan_ref'])
    spec = build_research_run_spec(descriptor)
    packet = _load(root, route['review_packet_binding'])
    materiality = event_materiality_review_from_payload(_load(root, packet['bindings']['event_materiality']))
    validity_input = spec.model_validity_input
    scan = validity_input.event_scan
    blockers = list(dict.fromkeys((*validity_input.blockers, *scan.blockers)))
    # A signed classification cannot turn an intraday snapshot into full-day coverage.
    if observation.get('full_calendar_window_elapsed') is not True:
        blockers.append('INCREMENTAL_WINDOW_NOT_ELAPSED')
    _, package = read_bound_json(root, binding['package_ref'], 'original materiality package')
    original_ref = package['model_validity_input'].get('event_scan_ref')
    if original_ref and original_ref != binding['scan_ref']:
        from ...event_scan import event_scan_from_payload
        prior = event_scan_from_payload(_load(root, original_ref))
        if prior.status != 'COMPLETE_NO_MATERIAL_EVENT_IN_VALIDITY_WINDOW' or prior.blockers:
            blockers.append('ORIGINAL_EVENT_REVIEW_UNRESOLVED')
    validity = evaluate_model_validity(model_id=validity_input.model_id, symbol=symbol,
        model_as_of=descriptor.point_in_time.research_as_of, valid_from=validity_input.valid_from,
        quote_date=date.fromisoformat(binding['review_cutoff']), events=[],
        event_scan_evidence_refs=[dict(id='authenticated-materiality-' + ref['sha256'], **ref)
            for ref in (binding['scan_ref'], route['review_packet_binding'], route['consumption_binding'])],
        blockers=blockers, event_materiality=materiality)
    if validity.status == 'VALID' and validity.blockers:
        validity = replace(validity, status='UNKNOWN', material_event_found=None)
    return validity, route


def materiality_transport_identity_refs(*, root, package_binding, scan_binding):
    """Find only the exact context journal, including absent/incomplete/revoked state."""
    from ...infrastructure.evidence.trust_root_registry import trust_registry_path
    refs = []
    registry = trust_registry_path().resolve()
    if registry.is_relative_to(root.resolve()):
        refs.append(dict(path=registry.relative_to(root.resolve()).as_posix()))
    try:
        handoff = prepare_materiality_review_handoff(root=root,
            package_path=root / package_binding['path'], package_sha256=package_binding['sha256'],
            scan_path=root / scan_binding['path'], scan_sha256=scan_binding['sha256'])
        directory = root / 'runtime/materiality-review-responses' / _context_key(handoff['model_context'])
        for name in ('claim.json', 'completion.json'):
            record_path = directory / name
            refs.append(dict(path=record_path.relative_to(root).as_posix()))
            if record_path.is_file():
                binding = _strict_review_json(record_path)
                refs.append(binding)
                if name == 'completion.json':
                    receipt = _load(root, binding)
                    packet_ref = receipt['review_packet_binding']
                    refs.append(packet_ref)
                    packet = _load(root, packet_ref)
                    refs.extend(packet['bindings'].values())
                    transport = packet['authenticated_materiality_binding']
                    refs.extend(transport.values())
                else:
                    checkpoint = _load(root, binding)
                    refs.extend(checkpoint['authenticated_materiality_binding'].values())
    except (ValueError, KeyError, TypeError, OSError):
        pass  # Observed paths already retained; invalid bytes still affect identity.
    return refs
