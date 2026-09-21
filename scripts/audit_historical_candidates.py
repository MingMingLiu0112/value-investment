"""Audit historical candidate coverage and parser deltas, without approving facts."""
import argparse
import json
from collections import Counter
from pathlib import Path


FIELDS = ('revenue', 'net_income', 'operating_cash_flow', 'total_assets',
          'total_liabilities', 'roe', 'eps_annual', 'eps_ttm', 'bvps')


def load_packets(directory):
    packets = {}
    for path in sorted(directory.glob('*.json')):
        packet = json.loads(path.read_text(encoding='utf-8'))
        key = (packet['symbol'], packet['announcement']['announcement_id'])
        if key in packets:
            raise ValueError('Duplicate announcement packet')
        packets[key] = packet
    if not packets:
        raise ValueError('No historical packets found')
    return packets


def identities(packet):
    return Counter((r['field_name'], str(r['value']), r['unit'], r['page'])
                   for r in packet['candidates'])


def audit(current, previous):
    changes = []
    for key in sorted(set(current) | set(previous)):
        old = identities(previous[key]) if key in previous else Counter()
        new = identities(current[key]) if key in current else Counter()
        added, removed = list((new - old).elements()), list((old - new).elements())
        if added or removed or key not in current or key not in previous:
            changes.append({'symbol': key[0], 'announcement_id': key[1],
                            'added': added, 'removed': removed,
                            'packet_missing': key not in current})
    companies = []
    for symbol in sorted({key[0] for key in current}):
        packets = [p for key, p in current.items() if key[0] == symbol]
        missing = {field: sorted(p['report_period_from_title'] for p in packets
                                if field not in {r['field_name'] for r in p['candidates']})
                   for field in FIELDS}
        companies.append({'symbol': symbol, 'reports': len(packets),
                          'missing_candidate_periods': missing})
    return {'scope': 'Candidate inventory only; presence does not verify a financial fact',
            'packet_count': len(current),
            'candidate_count': sum(len(p['candidates']) for p in current.values()),
            'changes': changes, 'companies': companies,
            'historical_backtest_ready': False,
            'remaining_gates': ['Independent financial verification and period scope',
                'Actual publication availability and revision chronology',
                'Historical TTM EPS and BVPS with consistent share basis',
                'Valuation assumptions and model validation',
                'Execution prices, corporate actions, costs and trading constraints']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('current', type=Path)
    parser.add_argument('previous', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = audit(load_packets(args.current), load_packets(args.previous))
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        # Preserve earlier audit artifacts rather than silently replacing them.
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(encoded + '\n')
    print(encoded)


if __name__ == '__main__':
    main()
