"""Observed research scheduling, deliberately separate from fact admission."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json


VERSION = 'value-observation-research-priority-v1'
# Lowest positive bands in financial-quality-general-v1, not a new quality gate.
CRITERIA = (
    ('roe_weighted', 'percent', '10'),
    ('gross_margin', 'percent', '15'),
    ('total_revenue_yoy', 'percent', '0'),
    ('parent_net_income_yoy', 'percent', '0'),
)


def fingerprint(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def _number(value):
    try:
        result = Decimal(str(value))
        return result if not isinstance(value, bool) and result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def observation_conditions(points: list[dict], *, now: datetime) -> tuple[list[dict], str | None]:
    """Use one latest annual period; ambiguous/invalid evidence never becomes zero."""
    if now.tzinfo is None:
        raise ValueError('timezone-aware cutoff required')
    annual = [point for point in points if str(point.get('period_label', '')).endswith('-12-31')]
    period = max((str(point['period_label']) for point in annual), default=None)
    required_year = now.year - (1 if now.month >= 5 else 2)
    current = [point for point in annual if point['period_label'] == period]
    conditions = []
    for field, unit, minimum in CRITERIA:
        selected = [point for point in current if point.get('field_name') == field]
        entries, problems = [], []
        for point in selected:
            number = _number(point.get('value'))
            try:
                available = datetime.fromisoformat(point['available_at'])
                if available.tzinfo is None or available > now:
                    raise ValueError('not available at cutoff')
                if datetime.fromisoformat(period).date() >= available.date():
                    raise ValueError('period not completed before observation')
            except (ValueError, TypeError, KeyError):
                problems.append('INVALID_OR_FUTURE_AVAILABILITY')
                continue
            if number is None or point.get('unit') != unit:
                problems.append('INVALID_VALUE_OR_UNIT')
                continue
            if not point.get('raw_file_hash') or not point.get('source_url'):
                problems.append('MISSING_SOURCE_REFERENCE')
                continue
            entries.append((number, point))
        distinct = {value for value, _ in entries}
        status = 'conflicting' if problems or len(distinct) > 1 else 'observed' if distinct else 'missing'
        value = next(iter(distinct)) if status == 'observed' else None
        stale = period is not None and int(period[:4]) < required_year
        conditions.append(dict(field=field, unit=unit, period=period, status=status,
            value=str(value) if value is not None else None, operator='>=', threshold=minimum,
            favorable=(value >= Decimal(minimum)) if value is not None and not stale else None,
            stale=stale, problems=sorted(set(problems)),
            basis='financial-quality-general-v1 lowest positive scoring band; observation only',
            evidence=[{key: point.get(key) for key in ('data_point_id', 'source_id', 'source_url',
                'raw_file_hash', 'available_at', 'validation_status', 'period_label')}
                for _, point in entries], formal_fact=False))
    return conditions, period


def rank_research_candidates(rows: list[dict], *, limit: int) -> tuple[list[dict], list[dict]]:
    """Lexicographic work queue, no weighted financial score or return forecast."""
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError('limit must be an integer from 1 to 200')
    ranked = []
    for row in rows:
        item = dict(row)
        conditions = item['conditions']
        item['observation_summary'] = dict(
            favorable=sum(c['favorable'] is True for c in conditions),
            unfavorable=sum(c['favorable'] is False for c in conditions),
            missing=sum(c['status'] == 'missing' for c in conditions),
            conflicting=sum(c['status'] == 'conflicting' for c in conditions))
        item['research_priority_eligible'] = bool(
            item['profile_status'] == 'GENERAL_RESEARCH'
            and not item.get('risk_warning') and not item.get('price_conflict')
            and not item['observation_summary']['conflicting']
            and not any(c['stale'] for c in conditions)
            and (item['observation_summary']['favorable'] or item['channels']))
        item.update(formal_eligibility=False, buy_eligible=False, action='no_order',
            financial_quality_status='NOT_GRANTED_BY_OBSERVATION_RANKING')
        ranked.append(item)
    def key(row):
        count = row['observation_summary']
        return (not row['research_priority_eligible'], -count['favorable'], count['unfavorable'],
                count['missing'], -len(row['channels']), row['symbol'])
    ranked.sort(key=key)
    for rank, row in enumerate(ranked, 1):
        row['research_priority_rank'] = rank if row['research_priority_eligible'] else None
    return ranked, [row for row in ranked if row['research_priority_eligible']][:limit]
