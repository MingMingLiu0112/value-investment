"""Archive dated quotes with shared source documents; no database or signal writes."""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from value_investment_agent.quote_session_collection import collect_session_bundle, resolve_session_reference
from value_investment_agent.quote_sessions import evaluate_quote_session, parse_quote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbols', required=True)
    args = parser.parse_args()
    bundle = collect_session_bundle(args.symbols.split(','))
    now = datetime.now(timezone.utc)
    results = []
    for symbol, reference in bundle['references'].items():
        price = None
        try:
            resolved = resolve_session_reference(reference, bundle['documents'])
            price = parse_quote(resolved['tencent'], 'tencent', symbol, now)['price']
        except (ValueError, KeyError, TypeError):
            pass
        result = evaluate_quote_session(symbol, price, reference, now, documents=bundle['documents'])
        results.append({'symbol': symbol, 'observed_price': str(price) if price is not None else None,
                        'result': result})
    target = ROOT / 'runtime/quote-sessions' / now.strftime('%Y%m%dT%H%M%S%fZ')
    target.mkdir(parents=True)
    raw = json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode('utf-8')
    (target / 'bundle.json').write_bytes(raw)
    report = {'bundle_sha256': hashlib.sha256(raw).hexdigest(), 'bundle_bytes': len(raw),
              'document_count': len(bundle['documents']), 'company_count': len(results),
              'status': bundle['status'], 'observations': results,
              'production_database_changed': False, 'financial_or_strategy_approval': False}
    (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    # This CLI is consumed by the scheduled PowerShell workflow. Keep its final
    # result to one JSON line so diagnostic output cannot corrupt command parsing.
    print(json.dumps({'path': str(target), **report}, ensure_ascii=False))


if __name__ == '__main__':
    main()
