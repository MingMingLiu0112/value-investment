"""Explain decision blockers at export time without inventing portfolio holdings."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from value_investment_agent.reminders import build_reminders


def audit(payload):
    alerts = build_reminders(payload, now=datetime.fromisoformat(payload['generated_at']))
    failed = Counter()
    for alert in alerts:
        failed.update(check['name'] for check in alert['decision_checks'] if not check['passed'])
    members = {c['symbol']: c for c in payload['market_candidates']}
    field_gaps = Counter()
    priorities = []
    for quality in payload.get('financial_quality', []):
        symbol = quality['symbol']
        if symbol not in members:
            continue
        details = quality.get('calculation_details') or {}
        required = set(details.get('required_fields', []))
        accepted = set(details.get('accepted_fields', []))
        missing = sorted(required - accepted)
        field_gaps.update(missing)
        priorities.append({'symbol': symbol, 'name': members[symbol]['name'],
                           'model_type': quality.get('model_type'),
                           'required_count': len(required), 'missing_fields': missing,
                           'quality_status': quality.get('quality_status'),
                           'quality_calculated_at': quality.get('calculated_at')})
    priorities.sort(key=lambda row: (not bool(row['required_count']),
                                    len(row['missing_fields']), row['symbol']))
    return {
        'scope': 'Candidate evidence gaps at export time; unknown holdings; not strategy validation',
        'generated_at': payload['generated_at'],
        'candidate_count': len(alerts),
        'board_counts': dict(Counter(c.get('board') for c in payload['market_candidates'])),
        'failed_gate_counts': dict(failed),
        'missing_quality_field_counts': dict(field_gaps.most_common()),
        'evidence_completion_queue': priorities,
        'all_data_gates_passed': sum(all(c['passed'] for c in a['decision_checks']) for a in alerts),
        'companies': [{'symbol': a['symbol'], 'name': a['name'],
                       'failed_checks': [c for c in a['decision_checks'] if not c['passed']]}
                      for a in alerts],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.payload.read_bytes()
    result = audit(json.loads(raw.decode('utf-8-sig')))
    result['payload_sha256'] = hashlib.sha256(raw).hexdigest()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('companies', 'evidence_completion_queue')}, ensure_ascii=False))
