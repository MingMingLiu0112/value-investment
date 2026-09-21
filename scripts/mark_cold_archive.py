#!/usr/bin/env python3
"""Record a verified local cold archive receipt; this command never deletes PDFs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.db import connect, mark_disclosures_cold_archived
from value_investment_agent.settings import get_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--archive-uri', required=True,
                        help='Immutable local archive identifier, not a server path')
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    if manifest.get('mode') != 'copy_and_verify_only' or manifest.get('deletion_permitted') is not False:
        raise ValueError('Expected an immutable copy-only cold archive manifest')
    candidates = manifest.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('Manifest has no candidates')
    ids = [str(row['disclosure_id']) for row in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('Manifest contains duplicate disclosure IDs')
    manifest_sha256 = hashlib.sha256(raw).hexdigest()
    with connect(get_settings().database_url) as connection:
        updated = mark_disclosures_cold_archived(
            connection, manifest_sha256=manifest_sha256,
            archive_uri=args.archive_uri, disclosure_ids=ids,
        )
    print(json.dumps({'status': 'recorded_only', 'updated': updated,
                      'manifest_sha256': manifest_sha256, 'deletion_permitted': False}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
