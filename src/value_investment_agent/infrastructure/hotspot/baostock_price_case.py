"""Bounded BaoStock SDK snapshots; historical research, never Sina/current admission."""
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from ...domain.execution.exchange_calendar import is_exchange_session
from ...domain.hotspot.current_price import aggregate_sessions, completed_session_bars
from ...domain.hotspot.price_action_plan import calculate_price_levels
from ...quote_sessions import CHINA


def load_baostock_history(*, root: Path, binding: dict, now: datetime) -> dict:
    """Cold-load retained SDK result snapshots, preserving actual acquisition time."""
    root = root.resolve()
    if now.utcoffset() is None:
        raise ValueError('Aware research cutoff required')

    def read(ref):
        path = (root / ref['path']).resolve()
        if not path.is_relative_to(root / 'runtime') or path.stat().st_size > 8_000_000:
            raise ValueError('Bounded runtime source required')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise ValueError('BaoStock source hash mismatch')
        return json.loads(raw)

    attempt = read(binding)
    if (attempt.get('provider') != 'BaoStock official SDK 0.9.4'
            or attempt.get('endpoint') != 'public-api.baostock.com:10030'
            or attempt.get('adjustflag') != '3' or attempt.get('action') != 'no_order'
            or attempt.get('login', {}).get('error_code') != '0'
            or attempt.get('exception')):
        raise ValueError('Unverified BaoStock request')
    code = attempt['symbol']
    symbol = code[3:]
    if (len(symbol) != 6 or not symbol.isascii() or not symbol.isdigit()
            or code[:3] != ('sh.' if symbol.startswith('6') else 'sz.')):
        raise ValueError('BaoStock security identity mismatch')
    start, end = date.fromisoformat(attempt['start_date']), date.fromisoformat(attempt['end_date'])
    if not 0 <= (end - start).days <= 90:
        raise ValueError('Bounded historical window required')
    acquired = datetime.fromisoformat(attempt['finished_at'])
    begun = datetime.fromisoformat(attempt['started_at'])
    if acquired.utcoffset() is None or begun.utcoffset() is None or not begun <= acquired <= now:
        raise ValueError('Historical acquisition cutoff mismatch')
    if acquired <= datetime.combine(end, datetime.min.time(), CHINA).replace(hour=15):
        raise ValueError('Historical source acquired before requested session completed')
    expected = set()
    day = start
    while day <= end:
        if is_exchange_session('SSE', day):
            expected.add(day.isoformat())
        day += timedelta(days=1)
    bars, refs = {}, {}
    for ref in attempt['queries']:
        period = {'d': 'daily', '15': '15m', '60': '60m'}.get(ref['frequency'])
        if period is None or period in bars or ref['error_code'] != '0':
            raise ValueError('Distinct successful daily/15m/60m queries required')
        payload = read(ref)
        fields = ['date', 'code', 'open', 'high', 'low', 'close', 'volume', 'amount', 'adjustflag']
        if period != 'daily':
            fields.insert(1, 'time')
        fetched = datetime.fromisoformat(payload['fetched_at'])
        if (payload['fields'] != fields or payload['error_code'] != '0'
                or len(payload['rows']) != ref['rows'] or not 0 < len(payload['rows']) <= 2000
                or fetched.utcoffset() is None or not begun <= fetched <= acquired):
            raise ValueError('Invalid SDK result contract')
        rows = []
        for values in payload['rows']:
            if len(values) != len(fields):
                raise ValueError('Malformed SDK row')
            row = dict(zip(fields, values))
            if row['code'] != code or row['adjustflag'] != '3' or row['date'] not in expected:
                raise ValueError('Row identity/adjustment/session mismatch')
            amount, volume = Decimal(row['amount']), Decimal(row['volume'])
            low, high = Decimal(row['low']), Decimal(row['high'])
            if (not all(x.is_finite() for x in (amount, volume, low, high))
                    or volume <= 0 or not low * volume <= amount <= high * volume):
                raise ValueError('Inconsistent share/CNY amount or volume units')
            label = row['date']
            if period != 'daily':
                stamp = datetime.strptime(row['time'], '%Y%m%d%H%M%S%f')
                if len(row['time']) != 17 or stamp.microsecond or stamp.date().isoformat() != label:
                    raise ValueError('Invalid completed bar label')
                label = stamp.strftime('%Y-%m-%d %H:%M:%S')
            rows.append(dict(time=label, **{key: row[key] for key in
                ('open', 'high', 'low', 'close', 'volume', 'amount')}))
        calculate_price_levels(rows, period=period)
        if len({r['time'] for r in rows}) != len(rows):
            raise ValueError('Duplicate historical bar')
        if period != 'daily' and completed_session_bars(rows, period=period) != rows:
            raise ValueError('Partial leading session is not accepted')
        if {r['time'][:10] for r in rows} != expected:
            raise ValueError('Missing historical session')
        bars[period], refs[period] = rows, dict(ref)
    if set(bars) != {'daily', '15m', '60m'}:
        raise ValueError('All three historical periods required')
    for index, hour in enumerate(bars['60m']):
        quarter = bars['15m'][index * 4:index * 4 + 4]
        if len(quarter) != 4 or quarter[-1]['time'] != hour['time']:
            raise ValueError('15m/60m interval mismatch')
        aggregate = aggregate_sessions(quarter)[0]
        if any(Decimal(aggregate[k]) != Decimal(hour[k])
                for k in ('open', 'high', 'low', 'close', 'volume')):
            raise ValueError('15m/60m OHLCV conflict')
        if abs(Decimal(aggregate['amount']) - Decimal(hour['amount'])) > Decimal('0.01'):
            raise ValueError('15m/60m amount conflict')
    for period in ('15m', '60m'):
        for actual, daily in zip(aggregate_sessions(bars[period]), bars['daily']):
            if actual['time'] != daily['time']:
                raise ValueError('Daily/minute session conflict')
            for key in ('open', 'high', 'low', 'close', 'volume'):
                if Decimal(actual[key]) != Decimal(daily[key]):
                    raise ValueError(f"Daily/{period} {daily['time']} {key} conflict: "
                                     f"daily={daily[key]} aggregate={actual[key]}")
            if abs(Decimal(actual['amount']) - Decimal(daily['amount'])) > Decimal('0.01'):
                raise ValueError('Daily/minute amount conflict')
    # Bind the returned calculation to the same bytes even during concurrent refresh.
    for ref in (binding, *attempt['queries']):
        read(ref)
    return dict(schema_version='baostock-historical-structure-input-v1', symbol=symbol,
        bars=bars, source_bindings=refs, attempt_binding=dict(binding),
        data_available_at=acquired.isoformat(), volume_unit='SHARES', amount_unit='CNY',
        adjustment='UNADJUSTED', source_representation='SDK_RESULT_SNAPSHOT_NOT_WIRE_BYTES',
        current_pit=False, strict_pit_admitted=False, strict_oos_admitted=False,
        strategy_validation='NOT_PROVEN', formal_eligibility=False, action='no_order')
