"""Read an explicitly registered, separate unadmitted event-review context."""
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import normalize_symbol, require_inside, sha256_file
from .event_scan_supplement import _read, verify_consumed_event_scan_supplement
from .research_reviews import _strict_review_json

WORKFLOW = Path('config/user-research-workflow-v1.json')


def _available(value, now):
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None or stamp > now:
        raise ValueError('Supplemental event context is not yet available')


def _quote(value):
    return "'" + value.replace("'", "''") + "'"


def _authenticated_import(root, consumption, supplement, now):
    from .research_materiality_reviews import (
        _context_key, verify_authenticated_materiality, build_materiality_review_descriptor,
    )
    from .research_reviews import attach_research_reviews
    from ...research_input import build_research_run_spec

    journal = require_inside(root, root / 'runtime/materiality-review-responses' /
        _context_key(consumption['model_context']), 'event materiality journal')
    if not journal.exists():
        return None
    completion = journal / 'completion.json'
    if not completion.is_file():
        raise ValueError('Supplemental materiality consumption incomplete; audit required')
    completion_ref = dict(path=completion.relative_to(root).as_posix(), sha256=sha256_file(completion))
    receipt_ref = _read(root, completion_ref)
    receipt = _read(root, receipt_ref)
    if (receipt.get('schema_version') != 'materiality-review-consumption-v1'
            or receipt.get('action') != 'no_order'
            or receipt.get('model_context') != consumption['model_context']
            or any(receipt.get(key) is not False for key in
                   ('whole_model_approved', 'research_admitted', 'price_admitted'))):
        raise ValueError('Supplemental materiality receipt context/scope mismatch')
    packet_ref = receipt['review_packet_binding']
    packet = _read(root, packet_ref)
    if set(packet.get('bindings', {})) != {'event_materiality'}:
        raise ValueError('Supplemental event packet cannot carry a G3 approval')
    materiality = _read(root, packet['bindings']['event_materiality'])
    _available(materiality['reviewed_at'], now)
    verify_authenticated_materiality(root=root, packet=packet,
        model_context=consumption['model_context'], materiality=materiality,
        packet_sha256=packet_ref['sha256'])
    descriptor = build_materiality_review_descriptor(root=root,
        package_binding=supplement['package_binding'], scan_binding=supplement['scan_binding'])
    spec = attach_research_reviews(root=root, descriptor=descriptor,
        spec=build_research_run_spec(descriptor), path=root / packet_ref['path'],
        expected_sha256=packet_ref['sha256'], event_sha256=supplement['scan_binding']['sha256'],
        require_model_binding=True)
    if spec.event_materiality_review is None or spec.human_research_approval is not None:
        raise ValueError('Supplemental materiality attachment scope mismatch')
    if _read(root, completion_ref) != receipt_ref:
        raise ValueError('Supplemental materiality completion changed during read')
    return dict(materiality_consumption_binding=receipt_ref, review_packet_binding=packet_ref,
                completion_binding=completion_ref)


def load_current_event_supplement_handoff(root: Path, symbol: str, now: datetime) -> dict | None:
    """Replay explicit inputs without publishing, signing or upgrading old G3.

    Absence is optional. An explicitly registered invalid context fails closed;
    callers must not substitute an unrelated historical materiality handoff.
    """
    root = root.resolve()
    symbol = normalize_symbol(symbol)
    workflow_path = require_inside(root, root / WORKFLOW, 'event supplement workflow')
    if not workflow_path.exists():
        return None
    try:
        if workflow_path.stat().st_size > 1_000_000:
            raise ValueError('Supplemental event workflow exceeds byte bounds')
        workflow_hash = sha256_file(workflow_path)
        workflow = _strict_review_json(workflow_path)
        if (workflow.get('schema_version') != 'user-research-workflow-v1'
                or workflow.get('action') != 'no_order'):
            raise ValueError('Supplemental event workflow scope mismatch')
        entries = workflow.get('supplemental_event_consumptions', {})
        if not isinstance(entries, dict):
            raise ValueError('Supplemental event consumption bindings must be an object')
        if symbol not in entries:
            if sha256_file(workflow_path) != workflow_hash:
                raise ValueError('Supplemental event registry changed during read')
            return None
        if not isinstance(now, datetime) or now.utcoffset() is None:
            raise ValueError('Supplemental event read time must include a timezone')
        binding = entries[symbol]
        declared = _read(root, binding)
        runtime = require_inside(root, root / 'runtime', 'event supplement runtime')
        require_inside(runtime, root / binding['path'], 'event consumption binding')
        consumption = verify_consumed_event_scan_supplement(root=root, binding=binding)
        if declared != consumption or consumption['symbol'] != symbol:
            raise ValueError('Supplemental event consumption issuer mismatch')
        supplement = _read(root, consumption['supplement_binding'])
        handoff = _read(root, consumption['handoff_binding'])
        package = _read(root, supplement['package_binding'])
        workbench = _read(root, consumption['workbench_binding'])
        context = consumption['model_context']
        if (handoff['symbol'] != symbol or supplement['symbol'] != symbol
                or package['symbol'] != symbol or workbench['symbol'] != symbol
                or handoff['model_context'] != context
                or handoff['unsigned_response']['model_context'] != context
                or handoff['package_binding'] != supplement['package_binding']
                or handoff['scan_binding'] != supplement['scan_binding']):
            raise ValueError('Supplemental event handoff exact binding/context mismatch')
        for value in (supplement['generated_at'], handoff['scan_window']['retrieved_at'],
                      workbench['generated_at'], package['point_in_time']['available_at'],
                      package['point_in_time']['computed_at'], package['research_case']['generated_at']):
            _available(value, now)
        local_day = now.astimezone(ZoneInfo('Asia/Shanghai')).date()
        if (date.fromisoformat(context['research_as_of']) > local_day
                or date.fromisoformat(handoff['scan_window']['scan_to']) >= local_day):
            raise ValueError('Supplemental event review requires an elapsed available window')
        for item in handoff['announcements']:
            _available(item['published_at'], now)
        ref = consumption['handoff_binding']
        command = ('python scripts/current/review_materiality.py consume '
            f"--handoff {_quote(ref['path'])} --handoff-sha256 {ref['sha256']} "
            '--response <SIGNED_RESPONSE_PATH> --response-sha256 <SIGNED_RESPONSE_SHA256> '
            '--trust-root <PINNED_TRUST_ROOT_PATH> --trust-root-sha256 <PINNED_TRUST_ROOT_SHA256> '
            '--output <NEW_RUNTIME_DIRECTORY>')
        recompute = ('python scripts/current/run_company_research.py '
            f"--symbol {symbol} --package {_quote(supplement['package_binding']['path'])} "
            f"--schedule-request {_quote(consumption['schedule_binding']['path'])} "
            '--research-reviews <IMPORTED_RESEARCH_REVIEWS_PATH> '
            '--research-reviews-sha256 <IMPORTED_RESEARCH_REVIEWS_SHA256> '
            '--output <NEW_RUNTIME_RESEARCH_JSON>')
        imported = _authenticated_import(root, consumption, supplement, now)
        if imported:
            packet_ref = imported['review_packet_binding']
            recompute = recompute.replace('<IMPORTED_RESEARCH_REVIEWS_PATH>', _quote(packet_ref['path']))
            recompute = recompute.replace('<IMPORTED_RESEARCH_REVIEWS_SHA256>', packet_ref['sha256'])
        result = dict(status='EXTERNAL_SIGNATURE_REQUIRED', action='no_order', symbol=symbol,
            scope='SEPARATE_UNADMITTED_EVENT_CONTEXT_NOT_CURRENT_G3',
            consumption_binding=dict(binding), handoff_binding=dict(ref),
            model_context=context, model_context_scope='ACTUALLY_CONSUMED',
            scan_binding=handoff['scan_binding'], scan_window=handoff['scan_window'],
            announcements=handoff['announcements'], unsigned_response=handoff['unsigned_response'],
            signature_contract=handoff['signature_contract'],
            commands=dict(consume_signed_response=command, recompute=recompute),
            approval_granted=False, g3_approval_granted=False, research_admitted=False,
            price_admitted=False, position_guidance=None, recompute_required=True, publication_required=True)
        if imported:
            result.update(imported, status='AUTHENTICATED_RESPONSE_IMPORTED',
                instructions='Signed event decisions imported; recompute and publish the separate context. '
                             'This does not grant G3, research or price admission.')
        # Replaying twice catches source replacement during projection, including
        # nested official originals; the mutable registration must also stay put.
        if (verify_consumed_event_scan_supplement(root=root, binding=binding) != consumption
                or _read(root, consumption['handoff_binding']) != handoff
                or _authenticated_import(root, consumption, supplement, now) != imported
                or sha256_file(workflow_path) != workflow_hash):
            raise ValueError('Supplemental event registry or sources changed during read')
        return result
    except (OSError, KeyError, TypeError, AttributeError, OverflowError) as error:
        raise ValueError('Registered supplemental event handoff is unavailable or malformed') from error
