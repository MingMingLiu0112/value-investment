"""Read current screening leads, independently of admitted decision publications."""
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path

from ..product.common import require_inside
from ..product.value_discovery_surface import project_value_discovery_report
from .public_financial_input import verify_public_supplement


def _bound_json(root: Path, binding: dict, base: Path, limit: int) -> dict:
    name, digest = binding['path'], binding['sha256']
    if not isinstance(name, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('invalid scan binding')
    path = require_inside(base, root / name, 'scan source')
    if path.stat().st_size > limit:
        raise ValueError('oversized scan source')
    raw = path.read_bytes()
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('scan source hash mismatch')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('scan source must be an object')
    return value


def current_scan_details(root: Path, manifest: dict) -> dict:
    """Return verified leads or a separate failure, never an empty-market verdict."""
    unavailable = {'status': 'SOURCE_REVALIDATION_FAILED', 'leads': [],
                   'formal_eligibility': False, 'action': 'no_order'}
    try:
        summary, files = manifest['summary'], manifest['files']
        base = root / 'runtime/daily-marketwide'
        report = _bound_json(root, files['lead_report'], base, 2_000_000)
        receipt = _bound_json(root, files['receipt'], base, 20_000_000)
        expected = project_value_discovery_report(root=root,
            receipt_path=root / files['receipt']['path'], receipt_sha256=files['receipt']['sha256'])
        if (report != expected or report['as_of'] != summary['as_of']
                or report['channel_counts'] != summary['channel_counts']
                or report['data_health'] != summary['data_health']
                or len(report['leads']) > 200):
            raise ValueError('scan report differs from bound receipt')
        result = dict(status='SOURCE_REVALIDATED', leads=report['leads'],
                      summary=dict(as_of=report['as_of'], universe_count=report['data_health']['universe_count'],
                          lead_count=len(report['leads']), channel_counts=report['channel_counts'],
                          quote_date_verification=report['quote_date_verification'],
                          data_status=report['data_health']['status'], blockers=report['data_health']['blockers']),
                      formal_eligibility=False, action='no_order')
        # Financial collection is independently degradable: a damaged supplement
        # never becomes facts, and never discards the verified screening receipt.
        result['financial'] = _financial_details(root, files, receipt, result['leads'])
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return unavailable


def _financial_details(root, files, receipt, leads):
    try:
        reference = next((ref for ref in receipt['evidence_refs'] if ref['id'] == 'financial'), None)
        if reference is None:
            return {'status': 'PUBLIC_SUPPLEMENT_NOT_CONSUMED'}
        if (reference['sha256'] != files['financial']['sha256']
                or (root / reference['path']).resolve() != (root / files['financial']['path']).resolve()):
            raise ValueError('financial supplement not consumed by this receipt')
        payload = _bound_json(root, files['financial'], root / 'runtime/daily-marketwide', 150_000_000)
        when = datetime.fromisoformat(receipt['generated_at'])
        verify_public_supplement(root=root, payload=payload, evaluation_at=when)
        info = payload.get('public_financial_input') or {}
        if info.get('status') != 'PROVIDER_OBSERVATIONS_NOT_FORMAL_FACTS':
            return {'status': 'PUBLIC_SUPPLEMENT_NOT_AVAILABLE'}
        by_symbol = {lead['symbol']: [] for lead in leads}
        for point in payload['points']:
            if (point['symbol'] in by_symbol
                    and str(point.get('data_point_id', '')).startswith('public-summary-')):
                by_symbol[point['symbol']].append({key: point[key] for key in (
                    'field_name', 'value', 'unit', 'period_label', 'available_at',
                    'source_name', 'source_url', 'raw_file_hash', 'validation_status')})
        for lead in leads:
            lead['financial_observations'] = by_symbol[lead['symbol']]
        return {key: info[key] for key in ('status', 'period', 'provider_rows',
            'observation_count', 'adopted_observation_count', 'missing_fields', 'generated_at')}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'PUBLIC_SUPPLEMENT_REVALIDATION_FAILED'}
