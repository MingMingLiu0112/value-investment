"""Research reconciliation of financing rows to retained balance-sheet evidence."""
from decimal import Decimal, InvalidOperation
import re

from .financial_quality import _accepted


FIELDS = {
    '短期借款': 'short_term_borrowings',
    '长期借款': 'long_term_borrowings',
    '一年内到期的非流动负债': 'current_portion_long_term_debt',
    '应付债券': 'bonds_payable',
    '租赁负债': 'lease_liabilities_noncurrent',
}
SCALES = {'CNY': Decimal(1), 'CNY 10K': Decimal(10000), 'CNY 100M': Decimal(100000000)}


def amount(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result >= 0 else None
    except (InvalidOperation, ValueError, TypeError):
        return None


def bridge_financing_rows(table, points, symbol, period, digest, source_url):
    """Exact numeric agreement is not liability classification or debt approval."""
    if not re.fullmatch(r'[0-9a-f]{64}', digest) or not source_url:
        raise ValueError('Pinned report identity required')
    rows = []
    for row in table['rows']:
        label = ''.join(row['label'].split())
        field = FIELDS.get(label)
        result = {'label': row['label'], 'field_name': field,
                  'closing': row['amounts']['closing'], 'raw_row': row,
                  'status': 'requires_note_classification', 'balance_fact': None}
        if field and amount(row['amounts']['closing']) is None:
            result['status'] = 'financing_closing_unknown_or_invalid'
            rows.append(result)
            continue
        if field:
            candidates = []
            for point in points:
                if (point.get('symbol') == symbol and point.get('field_name') == field
                        and point.get('period_label') == period and point not in candidates):
                    candidates.append(point)
            result['candidate_ids'] = [p.get('data_point_id') for p in candidates]
            result['status'] = 'missing_balance_fact' if not candidates else 'ambiguous_balance_facts'
            if len(candidates) == 1:
                fact = candidates[0]
                meta = fact.get('metadata') or {}
                result['balance_fact'] = fact
                result['status'] = 'balance_evidence_not_accepted'
                if (_accepted(fact) and not meta.get('superseded_by_parser')
                        and fact.get('data_point_id') and fact.get('source_id')
                        and meta.get('secondary_data_point_id') and meta.get('secondary_source_id')
                        and str(meta['secondary_source_id']) != str(fact['source_id'])
                        and str(meta['secondary_data_point_id']) != str(fact['data_point_id'])
                        and meta.get('secondary_source_url')
                        and meta.get('official_file_sha256') == digest
                        and fact.get('sha256') == digest and fact.get('source_url') == source_url):
                    closing = amount(row['amounts']['closing'])
                    value = amount(fact.get('value'))
                    scale = SCALES.get(fact.get('unit'))
                    result['status'] = 'unknown_or_incompatible_amount'
                    if closing is not None and value is not None and scale is not None and table['total'].get('unit') == 'CNY':
                        difference = closing - value * scale
                        result['difference_cny'] = str(difference)
                        result['status'] = ('amount_matches_scope_unverified' if difference == 0
                                            else 'amount_conflict')
        rows.append(result)
    return {'symbol': symbol, 'report_period': period, 'sha256': digest,
            'source_url': source_url, 'rows': rows,
            'matched_rows': sum(r['status'] == 'amount_matches_scope_unverified' for r in rows),
            'complete_debt_verified': False,
            'scope': 'Exact amount bridge only; labels, current maturities and omitted financing require notes'}
