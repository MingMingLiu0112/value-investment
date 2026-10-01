"""Expose a source-verified lifecycle ledger without importing stale yields."""
from datetime import datetime, timezone
import json
from pathlib import Path
from .common import require_inside, sha256_file, load_json_object
from ...m1_distribution_package_builder import build_dividend_result


def read_dividend_history(*, root: Path, path: Path, expected_sha256: str, symbol: str) -> dict:
    path = require_inside(root, path, 'dividend package')
    if sha256_file(path) != expected_sha256:
        raise ValueError('dividend package hash mismatch')
    package = load_json_object(path, 'dividend package')
    result = build_dividend_result(package, root=root)
    if result.symbol != symbol:
        raise ValueError('dividend history symbol mismatch')
    if result.as_of > datetime.now(timezone.utc).date():
        raise ValueError('dividend package observation is in the future')
    value = json.loads(result.to_json())
    sources = {source['id']: source for source in package['sources']}
    records = value['history']['records']
    for record in records:
        if not record['evidence_refs'] or any(ref['id'] not in sources for ref in record['evidence_refs']):
            raise ValueError('dividend record lacks verified source bindings')
        if datetime.fromisoformat(record['known_at']).date() > result.as_of:
            raise ValueError('dividend record exceeds package observation')
    # Recheck after conversion; package and originals must stay byte-identical.
    if sha256_file(path) != expected_sha256 or any(sha256_file(require_inside(root, root / source['location'],
            'dividend original')) != source['sha256'] for source in sources.values()):
        raise ValueError('dividend sources changed during review')
    return dict(schema_version='source-bound-dividend-history-v1', symbol=symbol,
        observed_at=datetime.now(timezone.utc).isoformat(), package_sha256=expected_sha256,
        package_as_of=value['as_of'], records=records, sources=list(sources.values()),
        history_completeness=value['history']['status'],
        blockers=value['blockers'], dividend_sustainability_admitted=False,
        current_yield_admitted=False, strict_pit_admitted=False, action='no_order')
