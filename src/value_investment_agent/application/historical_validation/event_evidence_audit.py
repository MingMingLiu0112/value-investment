"""Audit event-scan originals without promoting retrospective research admission."""
from pathlib import Path

from ..product.common import require_inside, load_json_object, sha256_file


def audit_event_evidence(*, root: Path, path: Path, expected_sha256: str,
                         symbol: str, recovered_originals: dict[str, Path] | None = None) -> dict:
    path = require_inside(root, path, 'event scan')
    if sha256_file(path) != expected_sha256:
        raise ValueError('event scan hash mismatch')
    payload = load_json_object(path, 'event scan')
    if payload.get('symbol') != symbol:
        raise ValueError('event scan symbol mismatch')
    refs = payload.get('evidence_refs')
    if not isinstance(refs, list) or not refs:
        raise ValueError('event scan requires original evidence references')
    results = []
    recovered_originals = recovered_originals or {}
    if set(recovered_originals) - {ref.get('id') for ref in refs if isinstance(ref, dict)}:
        raise ValueError('unknown recovered event evidence id')
    for ref in refs:
        if not isinstance(ref, dict) or not all(ref.get(k) for k in ('id', 'path', 'sha256')):
            raise ValueError('incomplete event evidence reference')
        original = require_inside(root, root / ref['path'], 'event original')
        actual = sha256_file(original) if original.is_file() else None
        item = dict(id=ref['id'], path=ref['path'], expected_sha256=ref['sha256'],
                            actual_sha256=actual, status='PASS' if actual == ref['sha256']
                            else 'MISSING' if actual is None else 'HASH_MISMATCH')
        if ref['id'] in recovered_originals:
            recovered = require_inside(root, recovered_originals[ref['id']], 'recovered original')
            if sha256_file(recovered) != ref['sha256']:
                raise ValueError('recovered original must match sealed reference hash')
            item['original_path_status'] = item['status']
            item['recovered_path'] = str(recovered.relative_to(root.resolve())).replace('\\', '/')
            item['recovered_sha256'] = ref['sha256']
            item['status'] = 'PASS_RECOVERED_ORIGINAL'
        results.append(item)
    passed = all(item['status'] in ('PASS', 'PASS_RECOVERED_ORIGINAL') for item in results)
    return dict(schema_version='historical-event-evidence-audit-v1', symbol=symbol,
                scan_sha256=expected_sha256, status='PASS' if passed else 'NOT_READY',
                references=results, evidence_integrity_verified=passed,
                model_validity_admitted=False, strict_pit_admitted=False,
                action='no_order')
