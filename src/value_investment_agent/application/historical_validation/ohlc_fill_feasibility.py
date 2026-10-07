"""Check frozen fill prices against retained day bars, without admitting execution."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path

from ..product.common import load_json_object, load_json_value, require_inside, sha256_file


def _price(value: object, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f'{label} is not a price') from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f'{label} must be finite and positive')
    return parsed


def audit_frozen_fill_bars(*, root: Path, result_path: Path, result_sha256: str,
                           journal_path: Path, journal_sha256: str) -> dict:
    """A day-bar range is necessary, not sufficient, evidence of historical fillability."""
    root = root.resolve()
    result_path = require_inside(root, result_path, 'historical replay result')
    journal_path = require_inside(root, journal_path, 'historical replay journal')
    if sha256_file(result_path) != result_sha256 or sha256_file(journal_path) != journal_sha256:
        raise ValueError('historical replay result/journal hash mismatch')
    result = load_json_object(result_path, 'historical replay result')
    journal = load_json_value(journal_path, 'historical replay journal')
    if (result.get('schema_version') != 'historical-execution-replay-v1'
            or result.get('action') != 'no_order' or result.get('historical_execution_validated') is not False
            or result.get('performance_claim_allowed') is not False
            or result.get('mechanical_reproduction_verified') is not True
            or not isinstance(journal, list)):
        raise ValueError('frozen replay scope mismatch')
    comparison = result.get('comparison', {})
    if (comparison.get('frozen_journal', {}).get('status') != 'MATCH'
            or comparison.get('range_result', {}).get('status') != 'MATCH'
            or comparison['frozen_journal'].get('rows_compared') != len(journal)):
        raise ValueError('frozen replay comparison not established')
    proof = result.get('price_source_correspondence', {})
    if (proof.get('schema_version') != 'historical-price-correspondence-v1'
            or proof.get('status') != 'MATCH' or proof.get('action') != 'no_order'
            or proof.get('validated_fields') != ['open', 'close']):
        raise ValueError('matched original open/close correspondence required')
    indexed = {item['date']: item for item in proof['rows']}
    if (len(indexed) != len(proof['rows']) or len(indexed) != len(journal)
            or [item['date'] for item in proof['rows']] != [item['date'] for item in journal]):
        raise ValueError('historical price correspondence must cover the journal')
    result_fills = [(item['date'], item['fill']) for item in result.get('execution_events', [])
                    if item.get('fill') is not None]
    journal_fills = [(item['date'], item['fill']) for item in journal if item.get('fill') is not None]
    if (not journal_fills or result_fills != journal_fills
            or result.get('summary', {}).get('fills') != len(journal_fills)
            or comparison['frozen_journal'].get('fills_compared') != len(journal_fills)):
        raise ValueError('fill journal does not match frozen replay result')
    originals = {(item['path'].replace('\\', '/'), item['sha256']) for item in result.get('source_bindings', [])
                 if item.get('role', '').startswith('execution_original_')}
    if not originals:
        raise ValueError('historical price originals are not pinned')
    parsed_files = {}
    checks = []
    for entry in journal:
        fill = entry.get('fill')
        if fill is None:
            continue
        day = entry['date']
        match = indexed.get(day)
        if match is None or not match.get('sources'):
            raise ValueError('fill day lacks matched original: ' + day)
        fill_price = _price(fill.get('price'), f'{day} fill price')
        observations = []
        source_refs = []
        for source in match['sources']:
            key = (source['path'].replace('\\', '/'), source['sha256'])
            if key not in originals:
                raise ValueError('fill original is not pinned in replay')
            path = require_inside(root, root / key[0], 'fill day original')
            if key not in parsed_files:
                if sha256_file(path) != source['sha256']:
                    raise ValueError('fill original hash mismatch')
                data = load_json_object(path, 'fill day original')
                groups = data.get('data', {})
                matches = [venue for venue in ('sh', 'sz', 'bj') if venue + result['symbol'] in groups]
                if data.get('code') != 0 or len(matches) != 1:
                    raise ValueError('fill original response/symbol mismatch')
                rows = groups[matches[0] + result['symbol']].get('day')
                if not isinstance(rows, list):
                    raise ValueError('fill original unadjusted day rows missing')
                parsed_files[key] = (path, rows)
            rows = parsed_files[key][1]
            index = source['row_index']
            if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(rows):
                raise ValueError('fill original row index invalid')
            row = rows[index]
            if len(row) < 6 or row[0] != day or fill.get('filled_on') != day:
                raise ValueError('fill original date/OHLC fields mismatch')
            opening, closing, high, low = (_price(row[i], f'{day} price field {i}') for i in range(1, 5))
            try:
                volume = Decimal(str(row[5]))
            except (InvalidOperation, ValueError) as error:
                raise ValueError('fill day volume invalid') from error
            if not volume.is_finite() or volume <= 0:
                raise ValueError('fill day volume missing or zero: ' + day)
            if (opening != _price(entry.get('open'), 'journal open')
                    or closing != _price(entry.get('close'), 'journal close')
                    or opening != _price(match.get('open'), 'matched open')
                    or closing != _price(match.get('close'), 'matched close')
                    or low > min(opening, closing) or high < max(opening, closing)
                    or not low <= fill_price <= high):
                raise ValueError('fill price/OHLC inconsistent with original: ' + day)
            observations.append((opening, closing, high, low, volume))
            source_refs.append(dict(path=key[0], sha256=source['sha256'], row_index=index))
        if len(set(observations)) != 1:
            raise ValueError('conflicting overlapping fill originals: ' + day)
        _, _, high, low, volume = observations[0]
        if fill.get('side') not in {'buy', 'sell'} or isinstance(fill.get('quantity'), bool) or not isinstance(fill.get('quantity'), int) or fill['quantity'] <= 0:
            raise ValueError('fill side/quantity invalid: ' + day)
        checks.append(dict(date=day, side=fill['side'], quantity=fill['quantity'],
            fill_price=str(fill_price), low=str(low), high=str(high),
            observed_volume=str(volume), volume_unit='SOURCE_UNVERIFIED',
            status='BAR_RANGE_CONSISTENT_NOT_FILL_PROVEN',
            originals=source_refs))
    if not checks:
        raise ValueError('frozen replay has no fills to audit')
    for (_, digest), (source, _) in parsed_files.items():
        if sha256_file(source) != digest:
            raise ValueError('fill original changed during audit')
    if sha256_file(result_path) != result_sha256 or sha256_file(journal_path) != journal_sha256:
        raise ValueError('frozen replay changed during audit')
    return dict(schema_version='historical-ohlc-fill-feasibility-v1', symbol=result['symbol'],
        scenario=result['scenario'], result_sha256=result_sha256,
        journal_sha256=journal_sha256, checked_fills=len(checks), checks=checks,
        feasibility_status='DAY_BAR_RANGE_CONSISTENT_NOT_EXECUTION_PROVEN',
        execution_admitted=False, historical_execution_validated=False,
        strict_pit_admitted=False, performance_claim_allowed=False,
        limitation='Daily bars do not prove order-book queue, limit status, suspension, liquidity or contemporaneous rule availability.',
        action='no_order')
