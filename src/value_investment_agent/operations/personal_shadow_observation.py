"""Append-only offline observation evidence; never grants operational admission."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from ..application.product.common import (
    encode_json_bytes, load_json_object, require_inside, sha256_bytes, sha256_file,
)
from .shadow_daily_input import audit_shadow_daily_input

SCHEMA = 'personal-shadow-observation-ledger-v1'
GENESIS = '0' * 64


def _records(ledger: Path) -> list[dict]:
    paths = sorted(ledger.glob('*.json')) if ledger.exists() else []
    if ledger.exists() and any(p.name != f'{i:06d}.json' for i, p in enumerate(paths, 1)):
        raise ValueError('observation ledger has a gap or unexpected record')
    records = []
    predecessor = GENESIS
    seen_days, seen_runs = set(), set()
    for path in paths:
        data = path.read_bytes()
        record = json.loads(data)
        if (not isinstance(record, dict) or record.get('schema_version') != SCHEMA
                or record.get('sequence') != len(records) + 1
                or record.get('predecessor_sha256') != predecessor
                or record.get('action') != 'no_order'
                or record.get('verified_real_session_count') != 0
                or data != encode_json_bytes(record)):
            raise ValueError('observation ledger integrity mismatch')
        day, run_id = record.get('session_date'), record.get('run_id')
        if not day or not run_id or day in seen_days or run_id in seen_runs:
            raise ValueError('observation ledger duplicate day/run')
        seen_days.add(day)
        seen_runs.add(run_id)
        predecessor = sha256_bytes(data)
        records.append(record)
    return records


def verify_offline_observation_ledger(*, root: Path, ledger: Path,
                                      expected_head_sha256: str | None = None) -> dict:
    """Validate local continuity; an external head pin detects deletion of a tail."""
    ledger = require_inside(root, ledger, 'observation ledger')
    records = _records(ledger)
    head = sha256_file(ledger / f'{len(records):06d}.json') if records else GENESIS
    if expected_head_sha256 is not None and head != expected_head_sha256:
        raise ValueError('observation ledger external head mismatch')
    return dict(schema_version=SCHEMA, record_count=len(records), head_sha256=head,
                verified_real_session_count=0, admission_status='OFFLINE_CONTINUITY_ONLY',
                action='no_order')


def append_offline_observation(*, root: Path, ledger: Path, manifest: Path,
                               expected_manifest_sha256: str,
                               expected_head_sha256: str, now: datetime) -> dict:
    """Record a source-bound attempt; no local clock or receipt proves a real session."""
    root = root.resolve()
    ledger = require_inside(root, ledger, 'observation ledger')
    manifest = require_inside(root, manifest, 'observation manifest')
    if now.utcoffset() is None:
        raise ValueError('observation clock requires timezone')
    ledger.mkdir(parents=True, exist_ok=True)
    lock = ledger / '.append.lock'
    locked = False
    try:
        with lock.open('x', encoding='utf-8') as handle:
            handle.write('offline append in progress\n')
        locked = True
        records = _records(ledger)
        predecessor = sha256_file(ledger / f'{len(records):06d}.json') if records else GENESIS
        if predecessor != expected_head_sha256:
            raise ValueError('observation ledger external head mismatch')
        audit = audit_shadow_daily_input(root=root, path=manifest,
            expected_sha256=expected_manifest_sha256, now=now)
        source = load_json_object(manifest, 'observation manifest')
        receipt_binding = source.get('bindings', {}).get('run_receipt')
        if not isinstance(receipt_binding, dict):
            raise ValueError('observation run receipt binding required')
        receipt_path = require_inside(root, root / receipt_binding['path'], 'observation run receipt')
        receipt = load_json_object(receipt_path, 'observation run receipt')
        run_id = receipt.get('run_id')
        if not isinstance(run_id, str) or not run_id:
            raise ValueError('observation run id required')
        if any(r['session_date'] == audit['session_date'] or r['run_id'] == run_id for r in records):
            raise ValueError('observation duplicate day/run')
        if records and audit['session_date'] <= records[-1]['session_date']:
            raise ValueError('observation day rollback')
        if sha256_file(receipt_path) != receipt_binding['sha256']:
            raise ValueError('observation run receipt changed')
        if sha256_file(manifest) != expected_manifest_sha256:
            raise ValueError('observation manifest changed')
        record = dict(schema_version=SCHEMA, sequence=len(records) + 1,
            predecessor_sha256=predecessor, session_date=audit['session_date'],
            run_id=run_id, manifest_sha256=expected_manifest_sha256,
            receipt_sha256=receipt_binding['sha256'], audited_at=now.isoformat(),
            input_consistency_status=audit['input_consistency_status'],
            blockers=audit['blockers'], assurance='LOCAL_OFFLINE_ONLY',
            admission_status='NOT_ADMITTED', verified_real_session_count=0,
            action='no_order')
        path = ledger / f'{len(records) + 1:06d}.json'
        with path.open('xb') as handle:
            handle.write(encode_json_bytes(record))
            handle.flush()
            os.fsync(handle.fileno())
        return dict(record_path=str(path), record_sha256=sha256_file(path), record=record)
    finally:
        if locked:
            lock.unlink(missing_ok=True)
