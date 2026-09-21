"""Fetch fresh quotes with staged code; retain evidence without production DB writes."""
import hashlib
import json
import signal
from collections import Counter
from pathlib import Path

from market import AllAMarketAdapter
from candidate_tracking import normalize_tracking_quotes, track_candidates
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def timeout(signum, frame):
    raise TimeoutError('Fresh tracking rehearsal exceeded 240 seconds')


signal.signal(signal.SIGALRM, timeout)
signal.alarm(240)
with connect(get_settings().database_url) as db:
    db.execute("SET statement_timeout='20s'")
    members = db.execute('SELECT * FROM market_screen_results WHERE screen_date=(SELECT max(screen_date) FROM market_screen_results) ORDER BY symbol').fetchall()
    db.rollback()
universe, _, _, raw, fetched_at, source = AllAMarketAdapter().fetch(include_industry=False)
observations = track_candidates(members, normalize_tracking_quotes(json.loads(raw)['rows']), fetched_at.isoformat())
snapshot = json.loads(raw)
digest = hashlib.sha256(raw).hexdigest()
directory = Path('/app/evidence/tracking_rehearsals')
directory.mkdir(parents=True, exist_ok=True)
archive = directory / (digest + '.json')
if archive.exists():
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == digest
else:
    with archive.open('xb') as stream:
        stream.write(raw)
assert [r['membership'] for r in observations] == members
print(json.dumps({'universe':len(universe), 'members':len(members),
    'source':source, 'fetched_at':fetched_at.isoformat(), 'sha256':digest,
    'archive':str(archive), 'statuses':dict(Counter(r['quote_status'] for r in observations)),
    'pe_bases':dict(Counter(r['pe_basis'] for r in observations)),
    'valuation_conflicts':sum(bool(r['valuation_field_conflicts']) for r in observations),
    'blocked':sum(r['signal_blocked'] for r in observations),
    'fallback_reason':snapshot.get('fallback_reason'),
    'cross_check':snapshot.get('valuation_cross_check'),
    'missing_symbols':[r['symbol'] for r in observations if r['quote_status']=='missing_quote'],
    'production_database_writes':False}), flush=True)
