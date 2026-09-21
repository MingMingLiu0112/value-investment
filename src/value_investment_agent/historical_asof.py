"""Conservative research-only selection of disclosed historical facts."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal


def _timestamp(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.utcoffset() is None:
        raise ValueError('Timezone-aware timestamps required')
    return stamp


def publication_date_upper_bound(value):
    """Exclusive end of a verified China publication date, not an exact timestamp."""
    published = date.fromisoformat(value)
    if published.isoformat() != value:
        raise ValueError('An explicit ISO publication date is required')
    return datetime.combine(published + timedelta(days=1), time(), timezone(timedelta(hours=8)))


def select_asof(points, *, symbol, field_name, period_label, decision_at):
    """Return original evidence rows, or none; do not infer availability from period.

    Callers must supply one explicit reporting period. Publication precision and
    verified availability are distinct from successful document parsing.
    """
    decision = _timestamp(decision_at)
    eligible = []
    for point in points:
        if (point.get('symbol'), point.get('field_name'), point.get('period_label')) != (
                symbol, field_name, period_label):
            continue
        if (point.get('validation_status') != 'verified'
                or not point.get('source_id') or not point.get('raw_file_hash')
                or not point.get('unit')
                or (point.get('metadata') or {}).get('evidence_quarantine')):
            continue
        exact = point.get('timestamp_precision') == 'timestamp'
        if exact:
            if point.get('availability_verified') is not True:
                continue
            published = upper = _timestamp(point['published_at'])
        elif point.get('timestamp_precision') == 'date':
            if (point.get('publication_date_verified') is not True
                    or point.get('availability_bound_verified') is not True
                    or point.get('availability_method') != 'china_publication_date_upper_bound'):
                continue
            upper = publication_date_upper_bound(point['published_date'])
            published = upper - timedelta(days=1)
        else:
            continue
        available = _timestamp(point['available_at'])
        if available < upper:
            raise ValueError('Availability precedes publication')
        if available <= decision:
            value = Decimal(str(point['value']))
            if not value.is_finite():
                raise ValueError('Non-finite financial value')
            eligible.append((published, upper, exact, value, point))
    if not eligible:
        return []
    latest = max(row[0] for row in eligible)
    # An unknown intraday publication may precede or follow an exact one.
    # Retain all versions not certainly older; never guess their order.
    selected = [row for row in eligible if row[1] > latest or (row[2] and row[1] == latest)]
    if len({(row[3], row[4]['unit']) for row in selected}) != 1:
        raise ValueError('Conflicting evidence with unresolved publication order')
    return [dict(row[4]) for row in selected]
