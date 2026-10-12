"""Hash/time-bound cache consumption using existing market and bar parsers."""
from datetime import datetime, date, time
import json
from pathlib import Path
from value_investment_agent.application.product.common import require_inside, sha256_file
from value_investment_agent.m1_historical_quote import tencent_daily_bar
from value_investment_agent.quote_sessions import CHINA


def aware(value: str) -> datetime:
    stamp = datetime.fromisoformat(value)
    if stamp.utcoffset() is None:
        raise ValueError('Source time requires explicit timezone')
    return stamp


def read_bound(root: Path, binding: dict, cutoff: datetime) -> tuple[bytes, dict]:
    path = require_inside(root / 'runtime', root / binding['path'], 'hotspot source')
    if sha256_file(path) != binding['sha256']:
        raise ValueError('Hotspot source hash mismatch: ' + binding['path'])
    available = aware(binding['available_at'])
    if available > cutoff:
        raise ValueError('Source not available at observation cutoff')
    raw = path.read_bytes()
    if sha256_file(path) != binding['sha256']:
        raise ValueError('Source changed while reading')
    return raw, dict(binding, scope='RETAINED_SECONDARY_SOURCE_NOT_STRICT_PIT')


def load_quote_history(root: Path, binding: dict, cutoff: datetime) -> tuple[list[dict], list[dict]]:
    raw, source = read_bound(root, binding, cutoff)
    manifest = json.loads(raw)
    symbol = manifest['symbol']
    target = date.fromisoformat(manifest['quote_date'])
    market_cutoff = cutoff.astimezone(CHINA)
    if (aware(manifest['created_at']) > cutoff or target > market_cutoff.date()
            or (target == market_cutoff.date() and market_cutoff.time() < time(15, 5))):
        raise ValueError('Future history manifest')
    provider = manifest['provider_documents']['tencent']
    provider_binding = dict(path=provider['path'].replace('\\', '/'), sha256=provider['sha256'],
        available_at=provider['fetched_at'], source_url=provider['source_url'])
    bars_raw, evidence = read_bound(root, provider_binding, cutoff)
    rows = json.loads(bars_raw)['data'][('sz' if symbol.startswith(('0','3')) else 'sh') + symbol]['day']
    dates = [row[0] for row in rows]
    if dates != sorted(set(dates)):
        raise ValueError('Duplicate or unordered bars')
    bars = [tencent_daily_bar(bars_raw, symbol, date.fromisoformat(day)) for day in dates if date.fromisoformat(day) <= target]
    if not bars or bars[-1]['date'] != target.isoformat():
        raise ValueError('History does not cover declared target')
    if bars[-1]['close'] != str(manifest['tencent_close']):
        # Decimal equality avoids source formatting differences.
        from decimal import Decimal
        if Decimal(bars[-1]['close']) != Decimal(str(manifest['tencent_close'])):
            raise ValueError('Manifest close does not match raw')
    return bars, [source, evidence]
