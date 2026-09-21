"""Classify legacy ratio input gaps without changing financial facts."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from value_investment_agent.derived_financials import _accepted, MONEY_UNITS
from value_investment_agent.financial_institutions import provisional_financial_type


def audit(path):
    raw = path.read_bytes()
    payload = json.loads(raw)
    points = {(p['symbol'], p['field_name']): p for p in payload['points']}
    issuers = {c['symbol']: c for c in payload['market_candidates']}
    rows = []
    for ratio in payload['points']:
        if (ratio['field_name'] != 'operating_cash_flow_to_net_income'
                or ratio.get('source_name') != 'AkShare / Sina financial indicators'):
            continue
        symbol = ratio['symbol']
        issuer = issuers.get(symbol, {})
        model = provisional_financial_type(issuer.get('name'), issuer.get('sector'))
        reasons, inputs = [], {}
        if symbol not in issuers:
            reasons.append('outside_current_candidate_pool')
        if model:
            reasons.append('financial_institution_not_general_cashflow_model')
        for field in ('operating_cash_flow', 'net_income'):
            point = points.get((symbol, field))
            inputs[field] = point
            if point is None:
                reasons.append(field + ':missing')
                continue
            if not _accepted(point):
                reasons.append(field + ':not_accepted:' + str(point.get('validation_status')))
            if point['period_label'] != ratio['period_label']:
                reasons.append(field + ':period_mismatch')
            if point.get('unit') not in MONEY_UNITS:
                reasons.append(field + ':unsupported_unit')
            value = Decimal(str(point['value']))
            if not value.is_finite() or (field == 'net_income' and value <= 0):
                reasons.append(field + ':invalid_denominator_or_value')
        rows.append({'symbol': symbol, 'name': issuer.get('name'), 'model': model,
                     'period': ratio['period_label'], 'reasons': reasons,
                     'input_records': inputs, 'ready_under_existing_gates': not reasons})
    return {'payload_sha256': hashlib.sha256(raw).hexdigest(),
            'generated_at': payload.get('generated_at'), 'companies': len(rows),
            'reason_counts': dict(Counter(reason for row in rows for reason in row['reasons'])),
            'rows': rows, 'database_writes': False,
            'scope': 'Latest export only; passed metadata is not new independent verification.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.payload)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k != 'rows'}, ensure_ascii=False, indent=2))
