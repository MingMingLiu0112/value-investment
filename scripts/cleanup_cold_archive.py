#!/usr/bin/env python3
"""Delete only evidence whose verified cold-copy receipt is already recorded.

The default is a full, non-destructive preflight.  Deletion is deliberately a
separate explicit action and never updates database facts or archive metadata.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from value_investment_agent.db import connect
from value_investment_agent.evidence_tiering import sha256_file
from value_investment_agent.settings import get_settings


def verified_cleanup_paths(manifest: dict, *, manifest_sha256: str, evidence_root: Path, connection) -> list[Path]:
    if manifest.get('mode') != 'copy_and_verify_only' or manifest.get('deletion_permitted') is not False:
        raise ValueError('Expected immutable copy-only cold archive manifest')
    candidates = manifest.get('candidates')
    if not isinstance(candidates, list) or not candidates:
        raise ValueError('Manifest has no candidates')
    ids = [str(row['disclosure_id']) for row in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError('Manifest contains duplicate disclosure IDs')
    rows = connection.execute(
        """SELECT disclosure_id, sha256, archive_status, archive_manifest_sha256, extraction_status
              FROM official_disclosures WHERE disclosure_id = ANY(%s::uuid[])""", (ids,)
    ).fetchall()
    by_id = {str(row['disclosure_id']): row for row in rows}
    if set(by_id) != set(ids):
        raise ValueError('Database does not contain every manifest disclosure')
    paths = []
    for candidate in candidates:
        row = by_id[str(candidate['disclosure_id'])]
        if (row['archive_status'] != 'cold_archived'
                or row['archive_manifest_sha256'] != manifest_sha256
                or row['extraction_status'] not in {'extracted', 'no_candidates'}
                or row['sha256'].lower() != str(candidate['sha256']).lower()):
            raise ValueError('Database archive receipt does not match immutable manifest')
        relative_path = Path(str(candidate.get('relative_path', '')))
        if relative_path.is_absolute() or not relative_path.parts or '..' in relative_path.parts:
            raise ValueError('Manifest has an unsafe evidence relative path')
        path = (evidence_root.resolve() / relative_path).resolve()
        if not path.is_relative_to(evidence_root.resolve()) or not path.is_file():
            raise ValueError('Server evidence path is absent or outside the configured evidence root')
        if path.stat().st_size != int(candidate['bytes']) or sha256_file(path).lower() != row['sha256'].lower():
            raise ValueError('Server evidence file no longer matches the verified manifest')
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--apply', action='store_true', help='Delete only after the complete preflight succeeds')
    args = parser.parse_args()
    raw = args.manifest.read_bytes()
    manifest = json.loads(raw)
    settings = get_settings()
    with connect(settings.database_url) as connection:
        paths = verified_cleanup_paths(
            manifest, manifest_sha256=hashlib.sha256(raw).hexdigest(),
            evidence_root=settings.evidence_directory, connection=connection,
        )
    total_bytes = sum(path.stat().st_size for path in paths)
    if args.apply:
        for path in paths:
            path.unlink()
    print(json.dumps({'status': 'deleted' if args.apply else 'preflight_passed',
                      'files': len(paths), 'bytes': total_bytes,
                      'deletion_performed': args.apply}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
