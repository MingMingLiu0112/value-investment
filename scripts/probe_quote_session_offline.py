"""Validate installed imports and replay retained raw evidence without network."""
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

from value_investment_agent import candidate_tracking, tracking_collection
from value_investment_agent.quote_session_collection import resolve_session_reference
from value_investment_agent.quote_sessions import evaluate_quote_session, parse_quote


stage = Path(__file__).resolve().parent
manifest = json.loads((stage / 'manifest.json').read_text())
installed = Path(candidate_tracking.__file__).parent
for row in manifest['files']:
    assert hashlib.sha256((installed / row['name']).read_bytes()).hexdigest() == row['new_sha256']
assert callable(tracking_collection.collect_candidate_quotes)
raw = (stage / 'bundle.json').read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'f1df713b937b540bd993bc433fa3bd9fd92942ce7892b2ae3c2e31c47556c0fe'
bundle = json.loads(raw)
now = datetime.fromisoformat(bundle['finished_at']) + timedelta(minutes=1)
results = {}
for symbol, ref in bundle['references'].items():
    resolved = resolve_session_reference(ref, bundle['documents'])
    price = parse_quote(resolved['tencent'], 'tencent', symbol, now)['price']
    result = evaluate_quote_session(symbol, price, ref, now, documents=bundle['documents'])
    assert not result['passed']
    results[symbol] = result['status']
assert results == {'000333': 'intraday_quote', '600519': 'unsupported_calendar', '601088': 'unsupported_calendar'}
print(json.dumps({'offline_imports': 'passed', 'installed_hashes_match': True,
                  'real_source_replay': results, 'approved_quotes': 0}))
