#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def main() -> None:
    payload = json.loads(Path('runtime/latest-server.json').read_text(encoding='utf-8-sig'))
    quality = {row['symbol']: row for row in payload.get('financial_quality', [])}
    valuation = {row['symbol']: row for row in payload.get('valuations', [])}
    rows = []
    for candidate in payload.get('market_candidates', []):
        symbol = candidate['symbol']
        q, v = quality.get(symbol, {}), valuation.get(symbol, {})
        coverage = float(q.get('coverage_ratio') or 0)
        margin = v.get('safety_margin')
        margin = float(margin) if margin is not None else None
        quality_ok = q.get('quality_status') in {'通过', 'qualified', 'verified'}
        valuation_ok = v.get('fair_value') is not None and margin is not None
        action = 'paper_entry' if quality_ok and coverage >= .8 and valuation_ok and margin >= .25 else (
            'research' if float(candidate.get('initial_score') or 0) >= 55 else 'watch')
        priority = float(candidate.get('initial_score') or 0) + coverage * 20 + max(0, margin or 0) * 10
        rows.append({'symbol': symbol, 'name': candidate.get('name'), 'score': candidate.get('initial_score'),
                     'coverage': coverage, 'quality_status': q.get('quality_status'),
                     'valuation_status': v.get('valuation_status'), 'fair_value': v.get('fair_value'),
                     'safety_margin': margin, 'action': action, 'priority': round(priority, 4)})
    rows.sort(key=lambda row: row['priority'], reverse=True)
    print(json.dumps({'actions': Counter(row['action'] for row in rows), 'top_20': rows[:20]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
