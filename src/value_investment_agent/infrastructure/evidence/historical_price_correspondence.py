"""Match archived open/close inputs to retained unadjusted Tencent day rows."""
from datetime import date
from decimal import Decimal
import json
import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_inside(root: Path, path: Path, label: str) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(label + ' must remain inside repository')
    return resolved


def verify_price_correspondence(*, root: Path, symbol: str, sessions: list, references: list) -> dict:
    prices = {}
    unsupported = []
    bindings = []
    for reference in references:
        if reference.get('kind') != 'prices':
            continue
        path = require_inside(root, root / reference['path'], 'historical price original')
        if sha256_file(path) != reference['sha256']:
            raise ValueError('historical price original hash mismatch')
        value = json.loads(path.read_text(encoding='utf-8'))
        data = value.get('data') if isinstance(value, dict) else None
        if not isinstance(data, dict):
            unsupported.append(reference['path'])
            continue
        matches = [key for key in data if key in ('sh' + symbol, 'sz' + symbol, 'bj' + symbol)]
        if value.get('code') != 0 or len(matches) != 1:
            raise ValueError('historical price response or symbol mismatch')
        rows = data[matches[0]].get('day')
        if not isinstance(rows, list) or not rows:
            raise ValueError('historical price requires unadjusted day rows')
        for index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) < 3:
                raise ValueError('malformed historical price row')
            day = date.fromisoformat(row[0]).isoformat()
            pair = tuple(Decimal(str(value)) for value in row[1:3])
            if any(not number.is_finite() or number <= 0 for number in pair):
                raise ValueError('historical prices must be finite and positive')
            previous = prices.get(day)
            if previous is not None and previous['prices'] != pair:
                raise ValueError('conflicting historical price originals')
            source = dict(path=reference['path'], sha256=reference['sha256'], row_index=index,
                          source_url=reference.get('url'))
            if previous is None:
                prices[day] = dict(prices=pair, sources=[source])
            else:
                previous['sources'].append(source)
        bindings.append((path, reference['sha256']))
    matched = []
    missing = []
    for session in sessions:
        day = session['date']
        original = prices.get(day)
        if original is None:
            missing.append(day)
            continue
        actual = (Decimal(str(session['open'])), Decimal(str(session['close'])))
        if actual != original['prices']:
            raise ValueError('execution session price differs from original: ' + day)
        matched.append(dict(date=day, open=str(actual[0]), close=str(actual[1]), sources=original['sources']))
    if bindings and missing:
        raise ValueError('historical price originals do not cover execution sessions')
    if any(sha256_file(path) != digest for path, digest in bindings):
        raise ValueError('historical price original changed during read')
    return dict(schema_version='historical-price-correspondence-v1',
                status='MATCH' if matched and not missing and not unsupported else 'NOT_ASSESSABLE',
                matched_sessions=len(matched), source_files=len(bindings), rows=matched,
                missing_dates=missing, unsupported_sources=unsupported,
                validated_fields=['open', 'close'], price_basis='UNADJUSTED_DAY_ROWS',
                historical_availability_proven=False, execution_admitted=False, action='no_order')
