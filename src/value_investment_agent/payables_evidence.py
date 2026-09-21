"""Validate retained same-snapshot payables components before corroboration."""
from decimal import Decimal, InvalidOperation

FIELDS = ('long_term_payables_excluding_special', 'special_payables_noncurrent')
SOURCE = 'AkShare / Sina detailed financial statements'


def validate_payables_components(match, inputs, symbol, period):
    metadata = match.get('metadata') or {}
    if not isinstance(metadata, dict) or not match.get('source_id'):
        return False
    components = metadata.get('source_components')
    if not isinstance(components, dict) or set(components) != set(FIELDS):
        return False
    if match.get('source_name') != SOURCE or match.get('unit') != 'CNY':
        return False
    if metadata.get('statement_scope') != 'consolidated' or metadata.get('components_same_raw_snapshot') is not True:
        return False
    if metadata.get('derivation_formula') != ' + '.join(FIELDS):
        return False
    values = {}
    try:
        for field in FIELDS:
            rows = [r for r in inputs if r.get('field_name') == field]
            if len(rows) != 1:
                return False
            row = rows[0]
            meta = row.get('metadata') or {}
            if not isinstance(meta, dict) or not row.get('source_id'):
                return False
            if (row.get('symbol') != symbol or row.get('period_label') != period
                or str(row.get('source_id')) != str(match.get('source_id'))
                or not row.get('data_point_id') or row.get('unit') != 'CNY'
                or row.get('validation_status') not in ('pending', 'verified')
                or meta.get('statement_scope') != 'consolidated'
                or meta.get('evidence_quarantine') or meta.get('superseded_by_parser')):
                return False
            value = Decimal(str(row['value']))
            if not value.is_finite() or value < 0:
                return False
            if value != Decimal(str(components.get(field))):
                return False
            values[field] = value
        return sum(values.values()) == Decimal(str(match['value']))
    except (ValueError, TypeError, InvalidOperation, KeyError):
        return False
