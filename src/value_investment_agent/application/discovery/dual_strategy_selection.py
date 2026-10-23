"""Independent nonpersonalized selection lanes; never a decision writer."""
from datetime import datetime
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path


def _no_new_authority(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'action' and item != 'no_order':
                raise ValueError('Selection cannot contain an order action')
            if key in {'trade_eligible', 'formal_eligibility', 'action_admitted',
                       'strategy_admitted', 'broker_execution_permission',
                       'action_eligibility', 'portfolio_eligibility', 'buy_eligible'} and item is not False:
                raise ValueError('Selection cannot grant investment authority')
            _no_new_authority(item)
    elif isinstance(value, list):
        for item in value:
            _no_new_authority(item)


def _lane(selector, *, root, now, limit):
    try:
        value = selector(root=root, now=now, limit=limit)
        if not isinstance(value, dict) or value.get('action') != 'no_order':
            raise ValueError('Invalid selection envelope')
        _no_new_authority(value)
        # Reject non-JSON data, NaN and accidental runtime objects at the boundary.
        json.dumps(value, allow_nan=False)
        # Keep full-universe coverage, but never ship thousands of evidence rows.
        projected = dict(value)
        rows = value.get('shortlist') if 'observation_count' in value.get('coverage', {}) else value.get('items')
        projected['items'] = deepcopy(list(rows or [])[:limit])
        projected['shortlist'] = deepcopy(list(value.get('shortlist') or [])[:limit])
        projected['presentation_scope'] = 'BOUNDED_RESEARCH_ROWS_FULL_COVERAGE_COUNTS'
        projected.pop('diagnostic', None)
        for row in projected['items'] + projected['shortlist']:
            row.pop('diagnostic', None)
        if len(json.dumps(projected, ensure_ascii=False).encode('utf-8')) > 2_000_000:
            raise ValueError('Selection response exceeds bounded presentation budget')
        return projected
    except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
        return dict(status='SOURCE_OR_SELECTION_UNAVAILABLE', items=[], shortlist=[],
            blockers=['SELECTION_SOURCE_OR_CONTRACT_NOT_VERIFIED'], action='no_order',
            formal_eligibility=False, trade_eligible=False)


def build_dual_strategy_selection(*, root: Path, now: datetime, limit: int = 30,
                                  value_selector=None, hotspot_selector=None):
    if now.utcoffset() is None or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Aware evaluation time and bounded research limit required')
    if value_selector is None:
        from .value_candidate_selection import select_current_value_candidates
        value_selector = select_current_value_candidates
    if hotspot_selector is None:
        from ..hotspot.candidate_selection import select_current_hotspot_candidates
        hotspot_selector = select_current_hotspot_candidates
    value = _lane(value_selector, root=Path(root), now=now, limit=limit)
    hotspot = _lane(hotspot_selector, root=Path(root), now=now, limit=limit)
    result = dict(schema_version='dual-strategy-selection-v1', action='no_order',
        scope='NONPERSONAL_RESEARCH_SELECTION_NOT_TRADE_RECOMMENDATION',
        evaluated_at=now.isoformat(), value=value, hotspot=hotspot,
        strategy_validation='NOT_PROVEN', personal_risk_evaluated=False,
        formal_eligibility=False, trade_eligible=False, broker_execution_permission=False,
        process={
            'value': ['Universe', 'Source verification', 'Multi-channel screening',
                      'Financial observations', 'Research priority', 'Company research',
                      'Applicable valuation and model validity', 'Human review'],
            'hotspot': ['Dated market', 'Industry activity and liquidity',
                        'Cross-industry candidate pool', 'Completed price structure',
                        'Strategy and execution validation', 'Human review'],
            'after_selection': ['Confirmed account', 'Shared cash and exposure',
                                'Original entry thesis if held', 'Manual decision']})
    identity = {key: data for key, data in result.items() if key != 'evaluated_at'}
    identity = dict(identity, value={k: v for k, v in value.items() if k != 'evaluated_at'},
                    hotspot={k: v for k, v in hotspot.items() if k != 'evaluated_at'})
    result['content_sha256'] = sha256(json.dumps(identity, sort_keys=True,
        ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    return result
