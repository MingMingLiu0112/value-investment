"""Exact fair-value intervals where observed price conflicts can change triggers."""
import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path


def flip_intervals(first, second, margin='0.30'):
    first, second, margin = Fraction(first), Fraction(second), Fraction(margin)
    if min(first, second) <= 0 or not 0 <= margin < 1:
        raise ValueError('Positive prices and a safety margin in [0,1) required')
    low, high = sorted((first, second))
    def interval(lower, upper):
        return {'lower_exact': str(lower), 'lower_inclusive': True,
                'upper_exact': str(upper), 'upper_inclusive': False,
                'empty': lower == upper}
    return {'buy_fair_value_interval': interval(low / (1 - margin), high / (1 - margin)),
            'sell_fair_value_interval': interval(low, high),
            'entry_margin_exact': str(margin),
            'condition': 'All other gates pass; buy upstream candidate; sell known positive holding',
            'historical_fair_value_available': False, 'actual_historical_signal_changed': None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('third_source_audit', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    raw = args.third_source_audit.read_bytes()
    source = json.loads(raw)
    results = []
    for row in source['results']:
        if row['status'] != 'corroboration_only':
            raise ValueError('Third-source audit is incomplete')
        if hashlib.sha256(Path(row['raw_path']).read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Third-source evidence hash mismatch')
        results.append({'symbol': row['symbol'], 'date': row['date'],
                        'tencent_close': row['tencent_close'], 'sina_close': row['sina_close'],
                        'sohu_close': row['values']['close'],
                        **flip_intervals(row['tencent_close'], row['sina_close'])})
    if not 1 <= len(results) <= 20:
        raise ValueError('Unexpected conflict count')
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump({'scope': 'Conditional trigger sensitivity, not historical signals or returns',
                   'source_path': str(args.third_source_audit),
                   'source_sha256': hashlib.sha256(raw).hexdigest(),
                   'rows': results, 'backtest_ready': False}, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'rows': len(results), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
