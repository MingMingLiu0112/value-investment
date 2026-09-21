"""Validate archived CFETS pages and normalize explicitly documented percent units."""
from datetime import datetime, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'runtime/valuation-research'
SOURCES = [
    ('cfets-curve-20260909T080004856262Z/curve.raw', 'e364688dc8a866c53e19b733b9672fb1059bddeb5aae5b5804fc7bb8258b948f'),
    ('cfets-unit-20260909T083724878031Z/page2.json', '6cd6ccc2cc466b8577a7dda82163678dff28e52ca83c63534c96385e736be811'),
    ('cfets-unit-20260909T084057742537Z/closed-fragment.html', '0a48796e324479b7c7c7d26dd9e19f228b7f36d1563f1245a6de4f0bfacc1b91'),
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def normalize(pages):
    rows = []
    for number, page in enumerate(pages, 1):
        data = page['data']
        require(page['head']['rep_code'] == '200', 'Response failed')
        for key, value in {'pageNum': number, 'total': 54, 'pageTotal': 2,
                           'pageSize': 50, 'firstBondType': 'CYCC000',
                           'startDateCN': '2026-09-08', 'endDateCN': '2026-09-08',
                           'dateList': ['2026-09-08']}.items():
            require(data[key] == value, f'Unexpected metadata {key}')
        require(len(page['records']) == (50 if number == 1 else 4), 'Incomplete page')
        for raw in page['records']:
            require(raw['newDateValueCN'] == '2026-09-08', 'Mixed observation dates')
            row = {'tenor_years': str(Decimal(raw['yearTermStr'])), 'page': number,
                   'raw': raw, 'rates_decimal': {}, 'status': {}}
            for field in ('maturityYieldStr', 'currentYieldStr', 'futureYieldStr'):
                value = raw[field]
                if value == '---':
                    row['rates_decimal'][field] = None
                    row['status'][field] = 'source_missing'
                    continue
                rate = Decimal(value) / Decimal(100)
                require(rate.is_finite(), 'Nonfinite yield')
                require(Fraction(rate) == Fraction(value) / 100, 'Independent conversion mismatch')
                row['rates_decimal'][field] = str(rate)
                row['status'][field] = 'source_value_unit_verified'
            rows.append(row)
    terms = [Decimal(row['tenor_years']) for row in rows]
    expected = [Decimal(x) for x in ('0.083', '0.25', '0.5', '0.75')] + list(map(Decimal, range(1, 51)))
    require(terms == expected, 'Missing, duplicate or reordered tenors')
    return rows


def main():
    raw = []
    for path, digest in SOURCES:
        content = (BASE / path).read_bytes()
        require(hashlib.sha256(content).hexdigest() == digest, f'Original changed: {path}')
        raw.append(content)
    require('收益率(%)' in raw[2].decode('utf-8'), 'Official percentage heading missing')
    pages = [json.loads(item) for item in raw[:2]]
    rows = normalize(pages)
    # Exercise failure cases against the real archived pages, not fabricated yields.
    failures = []
    for label in ('duplicate_tenor', 'wrong_date', 'incomplete_page', 'wrong_curve'):
        altered = json.loads(json.dumps(pages))
        if label == 'duplicate_tenor':
            altered[1]['records'][0]['yearTermStr'] = '46.0'
        elif label == 'wrong_date':
            altered[0]['records'][0]['newDateValueCN'] = '2026-09-09'
        elif label == 'incomplete_page':
            altered[1]['records'].pop()
        else:
            altered[0]['data']['firstBondType'] = 'OTHER'
        try:
            normalize(altered)
        except ValueError:
            failures.append(label)
        else:
            raise ValueError(f'Failed to reject {label}')
    ten = next(row for row in rows if Decimal(row['tenor_years']) == 10)
    require(ten['rates_decimal']['maturityYieldStr'] == '0.016813', 'Ten-year mismatch')
    missing = sum(value is None for row in rows for value in row['rates_decimal'].values())
    require(missing == 5, 'Missing observation count changed')
    result = {'curve_id': 'CYCC000', 'observation_date': '2026-09-08',
              'source_unit': 'percent', 'normalized_unit': 'decimal',
              'field_meanings': {'maturityYieldStr': 'yield_to_maturity',
                                 'currentYieldStr': 'spot_yield', 'futureYieldStr': 'forward_yield'},
              'sources': [{'path': p, 'sha256': h} for p, h in SOURCES],
              'rows': rows, 'points': len(rows), 'missing_values': missing,
              'failure_checks_passed': failures, 'company_discount_rate_approved': False,
              'limitations': ['No interpolation or missing-value imputation.',
                             'Percent conversion does not establish annual-effective compounding.',
                             'A sovereign curve is not issuer equity cost or WACC.',
                             'Do not use September 2026 observations in historical backtests.']}
    out = BASE / ('cfets-normalized-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(exist_ok=False)
    content = json.dumps(result, ensure_ascii=False, indent=2).encode('utf-8')
    (out / 'evidence.json').write_bytes(content)
    (out / 'manifest.json').write_text(json.dumps({
        'evidence_sha256': hashlib.sha256(content).hexdigest(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(out), 'points': len(rows), 'missing_values': missing,
                      'ten_year': ten['rates_decimal'], 'failure_checks': failures}))


if __name__ == '__main__':
    main()
