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


def _lane(selector, *, root, now, limit, offset=0, query='', strategy='value'):
    try:
        value = selector(root=root, now=now, limit=30)
        if not isinstance(value, dict) or value.get('action') != 'no_order':
            raise ValueError('Invalid selection envelope')
        _no_new_authority(value)
        # Reject non-JSON data, NaN and accidental runtime objects at the boundary.
        json.dumps(value, allow_nan=False)
        # Keep full-universe coverage, but never ship thousands of evidence rows.
        projected = dict(value)
        rows = list(value.get('items') or [])
        rows = [r for r in rows if r.get('research_priority_eligible') is True] if strategy == 'value' else [r for r in rows if r.get('selection_status') != 'EXCLUDED']
        needle = query.strip().casefold()
        rows = [r for r in rows if not needle or any(needle in str(r.get(k, '')).casefold() for k in ('symbol', 'name', 'company_name', 'industry'))]
        unavailable = value.get('status') in {'UNASSESSABLE', 'UNAVAILABLE', 'SOURCE_OR_SELECTION_UNAVAILABLE'} or value.get('data_status') == 'SOURCE_REVALIDATION_FAILED'
        projected['pagination'] = dict(offset=offset, limit=limit, total=None if unavailable else len(rows))
        projected['items'] = deepcopy(rows[offset:offset + limit])
        projected['shortlist'] = deepcopy(projected['items'])
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
            formal_eligibility=False, trade_eligible=False,
            pagination=dict(offset=offset, limit=limit, total=None))


def _research_summaries(lane, *, root, now):
    """Project only revalidated existing research, never generate or approve it."""
    from ..research.value_research_analysis import load_current_value_research_analysis
    for row in lane['items']:
        summary = dict(status='SCREENING_ONLY', valuation=None, action='no_order')
        try:
            analysis = load_current_value_research_analysis(root=root, symbol=row['symbol'], now=now)
            if analysis is not None:
                if analysis.get('action') != 'no_order' or analysis['symbol'] != row['symbol']:
                    raise ValueError('Research summary identity mismatch')
                valuation = analysis['valuation']
                summary.update(status='CONDITIONAL_RESEARCH', valuation={
                    key: valuation[key] for key in ('bear_value', 'base_value', 'bull_value', 'confidence')},
                    valuation_date=analysis.get('valuation_date'), research_as_of=analysis.get('research_as_of'),
                    counter_evidence=analysis.get('counter_evidence', [])[:2], blockers=analysis.get('blockers', [])[:3])
                _no_new_authority(summary)
                if len(json.dumps(summary, allow_nan=False).encode('utf-8')) > 100_000:
                    raise ValueError('Research summary exceeds row budget')
        except (ValueError, OSError, KeyError, TypeError, ArithmeticError):
            summary = dict(status='RESEARCH_SOURCE_UNAVAILABLE', valuation=None, action='no_order')
        row['research_summary'] = summary
    lane['shortlist'] = deepcopy(lane['items'])


def build_dual_strategy_selection(*, root: Path, now: datetime, limit: int = 30,
                                  value_selector=None, hotspot_selector=None,
                                  value_offset=0, hotspot_offset=0, q_value='', q_hotspot=''):
    if any(type(n) is not int or n < 0 for n in (value_offset, hotspot_offset)):
        raise ValueError('Nonnegative offsets required')
    if now.utcoffset() is None or type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError('Aware evaluation time and bounded research limit required')
    production_value = value_selector is None
    if value_selector is None:
        from .value_candidate_selection import select_current_value_candidates
        value_selector = select_current_value_candidates
    if hotspot_selector is None:
        from ..hotspot.candidate_selection import select_current_hotspot_candidates
        hotspot_selector = select_current_hotspot_candidates
    value = _lane(value_selector, root=Path(root), now=now, limit=limit, offset=value_offset, query=q_value)
    hotspot = _lane(hotspot_selector, root=Path(root), now=now, limit=limit, offset=hotspot_offset, query=q_hotspot, strategy='hotspot')
    if production_value and value['items']:
        _research_summaries(value, root=Path(root), now=now)
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
