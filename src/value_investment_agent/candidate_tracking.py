"""Refresh quotes without changing the membership or score of a research pool."""
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
import json


def normalize_tracking_quotes(rows):
    """Normalize supported market snapshots without applying initial-screen filters."""
    aliases = {
        'symbol': ('代码', 'symbol', 'code'), 'name': ('名称', 'name'),
        'current_price': ('最新价', 'current_price'),
        'pe': ('市盈率-动态', '动态市盈率', 'pe'),
        'pb': ('市净率', 'pb'), 'market_cap': ('总市值', 'market_cap'),
    }
    result = []
    for row in rows:
        normalized = {'valuation_field_conflicts': {}}
        for field, keys in aliases.items():
            values = [row[k] for k in keys if row.get(k) is not None]
            if field == 'symbol':
                values = [str(v).zfill(6) for v in values]
            if len(values) > 1 and any(str(v) != str(values[0]) for v in values[1:]):
                if field in ('pe', 'pb', 'market_cap'):
                    normalized['valuation_field_conflicts'][field] = {
                        key: row[key] for key in keys if row.get(key) is not None}
                    normalized[field] = None
                    continue
                raise ValueError('Conflicting quote aliases: ' + field)
            normalized[field] = values[0] if values else None
        symbol = normalized['symbol']
        if not symbol or len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit():
            raise ValueError('Invalid quote symbol')
        normalized['price_cross_check'] = row.get('price_cross_check')
        normalized['pe_basis'] = row.get('pe_basis', 'unspecified')
        normalized['pe_source_values'] = dict(row.get('pe_source_values') or {})
        result.append(normalized)
    return result


def _positive(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except (ValueError, TypeError, InvalidOperation):
        return None


def track_candidates(members, quotes, quote_as_of, *, now=None):
    """Use normalized quote rows; absence/conflicts never inherit a fresh old price."""
    if not quote_as_of:
        raise ValueError('A quote observation timestamp is required')
    observed = datetime.fromisoformat(str(quote_as_of).replace('Z', '+00:00'))
    if observed.tzinfo is None:
        raise ValueError('Quote observation must have a timezone')
    now = now or datetime.now(timezone.utc)
    fresh = now - timedelta(hours=30) <= observed <= now + timedelta(minutes=5)
    membership = {}
    for member in members:
        symbol = member['symbol']
        if symbol in membership:
            raise ValueError('Duplicate candidate membership: ' + symbol)
        membership[symbol] = member
    indexed = {}
    for quote in quotes:
        symbol = quote['symbol']
        if symbol not in membership:
            continue
        if symbol in indexed:
            raise ValueError('Duplicate tracked quote: ' + symbol)
        indexed[symbol] = quote
    result = []
    for symbol, member in membership.items():
        quote = indexed.get(symbol)
        price = _positive(quote.get('current_price')) if quote else None
        proof = (quote.get('price_cross_check') or {}) if quote else {}
        if not isinstance(proof, dict):
            proof = {}
        status = 'missing_quote' if quote is None else 'invalid_price' if price is None else (
            'price_conflict' if proof.get('status') == 'conflict' else
            'cross_check_missing' if proof.get('status') != 'matched' else 'matched')
        if status == 'matched':
            primary = _positive(proof.get('tencent_price'))
            secondary = _positive(proof.get('sina_price'))
            if primary is None or secondary is None or not proof.get('sina_url'):
                status = 'cross_check_missing'
            elif primary != price or abs(primary-secondary) > max(Decimal('0.03'), primary*Decimal('0.02')):
                status = 'price_conflict'
            elif not fresh:
                status = 'stale_quote'
        # Keep entry evidence distinct from present-day market observations.
        result.append({'symbol': symbol, 'membership': dict(member),
            'quote_as_of': quote_as_of, 'current_price': price,
            'quote_status': status, 'signal_blocked': status != 'matched',
            'price_cross_check': dict(proof),
            'pe': quote.get('pe') if quote else None,
            'pe_basis': quote.get('pe_basis', 'unspecified') if quote else 'unspecified',
            'pe_source_values': dict(quote.get('pe_source_values') or {}) if quote else {},
            'pb': quote.get('pb') if quote else None,
            'market_cap': quote.get('market_cap') if quote else None,
            'valuation_field_conflicts': dict(quote.get('valuation_field_conflicts') or {}) if quote else {},
            'risk_warning': bool(quote and 'ST' in str(quote.get('name', '')).upper())})
        if result[-1]['risk_warning'] or result[-1]['valuation_field_conflicts']:
            result[-1]['signal_blocked'] = True
    return result


def store_tracking_observations(connection, run_id, source_id, observations):
    """Append within the caller's transaction; never replace an earlier observation."""
    symbols = [row['symbol'] for row in observations]
    if len(symbols) != len(set(symbols)):
        raise ValueError('Duplicate observation symbols')
    for row in observations:
        if row['membership']['symbol'] != row['symbol']:
            raise ValueError('Observation membership does not match symbol')
        payload = json.dumps(row, default=str, sort_keys=True)
        params = (run_id, row['symbol'], source_id, row['quote_as_of'], row['quote_status'],
                  row['signal_blocked'], payload)
        connection.execute("""INSERT INTO candidate_tracking_observations
            (run_id,symbol,source_id,quote_as_of,quote_status,signal_blocked,observation)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (run_id,symbol) DO NOTHING""", params)
        existing = connection.execute("""SELECT source_id,observation FROM candidate_tracking_observations
            WHERE run_id=%s AND symbol=%s""", (run_id, row['symbol'])).fetchone()
        if not existing or str(existing['source_id']) != str(source_id) or existing['observation'] != json.loads(payload):
            raise ValueError('Tracking retry differs from retained observation')
    return len(observations)


def export_tracking_observations(connection):
    """Export one coherent run; a failed latest run must not revive older quotes."""
    run = connection.execute("""SELECT run_id, status FROM task_runs
        WHERE task_name = 'track-candidates'
        ORDER BY started_at DESC, run_id DESC LIMIT 1""").fetchone()
    if run is None:
        return {}
    if run['status'] != 'succeeded':
        return {'candidate_tracking': []}
    rows = connection.execute("""SELECT symbol, source_id, quote_as_of,
        quote_status, signal_blocked, observation
        FROM candidate_tracking_observations WHERE run_id = %s ORDER BY symbol""",
        (run['run_id'],)).fetchall()
    # Relational identity and status override any stale fields in the JSON payload.
    result = {'candidate_tracking': [dict(row['observation'],
        symbol=row['symbol'], source_id=str(row['source_id']),
        quote_as_of=row['quote_as_of'].isoformat(),
        quote_status=row['quote_status'], signal_blocked=row['signal_blocked'])
        for row in rows]}
    source_ids = sorted({str(row['source_id']) for row in rows
                         if row['observation'].get('quote_session_evidence') is not None})
    if source_ids:
        sources = connection.execute('''SELECT document_id, metadata FROM raw_documents
            WHERE document_id = ANY(%s::uuid[])''', (source_ids,)).fetchall()
        documents = {}
        for source in sources:
            for identity, document in (source['metadata'].get('quote_session_documents') or {}).items():
                if identity in documents and documents[identity] != document:
                    raise ValueError('Conflicting shared quote evidence documents')
                documents[identity] = document
        result['quote_session_documents'] = documents
    return result


def tracking_candidate_view(payload):
    """Keep screening identity while presenting only the latest tracking quotes."""
    candidates = payload.get('market_candidates', [])
    if 'candidate_tracking' not in payload:
        return [dict(row) for row in candidates]
    indexed = {}
    duplicates = set()
    for row in payload.get('candidate_tracking') or []:
        if row['symbol'] in indexed:
            duplicates.add(row['symbol'])
        indexed[row['symbol']] = row
    result = []
    for candidate in candidates:
        row = dict(candidate)
        observation = indexed.get(row['symbol'])
        valid = observation and row['symbol'] not in duplicates
        for field in ('current_price', 'pe', 'pb', 'market_cap'):
            row[field] = observation.get(field) if valid else None
        row['quote_as_of'] = observation.get('quote_as_of') if valid else None
        row['quote_source_id'] = observation.get('source_id') if valid else None
        row['pe_basis'] = observation.get('pe_basis', 'unspecified') if valid else 'unspecified'
        result.append(row)
    return result
