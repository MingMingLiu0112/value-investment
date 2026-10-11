"""Local private/synthetic IO boundary for the shared dual-sleeve risk contracts."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ...domain.portfolio.dual_sleeve_risk import review_dual_sleeve_risk
from ...domain.portfolio.dual_sleeve_records import (
    build_manual_record, record_sha256, validate_manual_history,
)
from ...private_portfolio_intake import require_private_data_path
from .common import require_inside, sha256_file


def _write_new_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def semantic_content(value):
    """Drop run-local identities, retaining economic dates, versions and source hashes."""
    if isinstance(value, dict):
        return {key: semantic_content(item) for key, item in value.items()
            if key not in ('generated_at', 'input_binding', 'semantic_content', 'path', 'local_path',
                'assessment_id', 'snapshot_id', 'policy_id', 'run_id')}
    if isinstance(value, list):
        return [semantic_content(item) for item in value]
    return value


def _strict_json(path):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('duplicate dual sleeve JSON key')
            value[key] = item
        return value
    def constant(value):
        raise ValueError('nonfinite JSON: ' + value)
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs, parse_constant=constant)


def _storage_path(root, path, *, namespace, private_root, must_exist=False):
    path = root/path if not path.is_absolute() else path
    if namespace == 'SIMULATED':
        result = require_inside(root/'.tmp', path, 'isolated synthetic sleeve storage')
        if must_exist and not result.is_file():
            raise ValueError('synthetic input missing')
        return result
    if private_root is None:
        raise ValueError('actual portfolio requires existing private_root outside Git/sync')
    return require_private_data_path(path, private_root=private_root, repository_root=root,
        must_exist=must_exist)


def run_dual_sleeve_review(*, root: Path, input_path: Path | None = None,
        input_sha256: str | None = None, output_path: Path | None = None,
        private_root: Path | None = None, synthetic=False, generated_at=None):
    generated_at = generated_at or datetime.now(timezone.utc)
    if input_path is None:
        if input_sha256 is not None:
            raise ValueError('input pin requires an explicit input')
        result = review_dual_sleeve_risk(dict(schema_version='dual-sleeve-risk-input-v1',
            action='no_order', namespace='ACTUAL', portfolio=None, shared_budget=None,
            sleeves=None, cash_reserve_cny=None, allocations=None,
            security_attributes=[], hotspot_request=None), generated_at=generated_at)
        result['semantic_content'] = semantic_content(result)
        if output_path is not None:
            _write_new_json(require_inside(root/'runtime', root/output_path, 'not-connected report'), result)
        return result
    namespace = 'SIMULATED' if synthetic else 'ACTUAL'
    source = _storage_path(root, input_path, namespace=namespace, private_root=private_root, must_exist=True)
    if input_sha256 is None or sha256_file(source) != input_sha256:
        raise ValueError('dual sleeve input hash mismatch or missing pin')
    payload = _strict_json(source)
    if payload['namespace'] != namespace:
        raise ValueError('CLI mode cannot relabel input namespace')
    result = review_dual_sleeve_risk(payload, generated_at=generated_at, allow_synthetic=synthetic)
    if sha256_file(source) != input_sha256:
        raise ValueError('dual sleeve input changed during review')
    result['input_binding'] = dict(sha256=input_sha256)
    result['risk_input_semantics'] = semantic_content(payload)
    result['semantic_content'] = semantic_content(result)
    if output_path is not None:
        output = _storage_path(root, output_path, namespace=namespace, private_root=private_root)
        _write_new_json(output, result)
    return result


def run_dual_sleeve_input_sheet_review(*, root, input_path, input_sha256,
        output_path=None, private_root=None, synthetic=False, generated_at=None):
    from .dual_sleeve_input_sheet import parse_dual_sleeve_input_csv
    generated_at = generated_at or datetime.now(timezone.utc)
    namespace = 'SIMULATED' if synthetic else 'ACTUAL'
    source = _storage_path(root, input_path, namespace=namespace, private_root=private_root, must_exist=True)
    if input_sha256 is None or sha256_file(source) != input_sha256:
        raise ValueError('private input sheet hash mismatch')
    parsed = parse_dual_sleeve_input_csv(source.read_text(encoding='utf-8'),
        namespace=namespace, generated_at=generated_at, allow_synthetic=synthetic)
    if sha256_file(source) != input_sha256:
        raise ValueError('private input sheet changed during validation')
    if parsed['risk_report'] is not None:
        result = parsed['risk_report']
        result['risk_input_semantics'] = semantic_content(parsed['payload'])
    else:
        result = run_dual_sleeve_review(root=root, generated_at=generated_at)
        result['namespace'] = namespace
        result['status'] = 'BLOCKED_PRIVATE_INPUT'
        result['blockers'] = parsed['missing_inputs']
    result['input_binding'] = dict(sha256=input_sha256)
    result['semantic_content'] = semantic_content(result)
    if output_path is not None:
        _write_new_json(_storage_path(root, output_path, namespace=namespace, private_root=private_root), result)
    return result


def append_dual_sleeve_manual_record(*, root: Path, directory: Path, body: dict,
        expected_head_sha256: str | None, private_root: Path | None = None,
        synthetic=False, generated_at=None):
    """Append only; callers must explicitly pin the previously observed head."""
    generated_at = generated_at or datetime.now(timezone.utc)
    namespace = 'SIMULATED' if synthetic else 'ACTUAL'
    folder = _storage_path(root, directory, namespace=namespace, private_root=private_root)
    records = []
    paths = sorted(folder.glob('*.json'))
    for index, path in enumerate(paths, start=1):
        record = _strict_json(path)
        if path.name != f'{index:08d}-{record_sha256(record)[:24]}.json':
            raise ValueError('manual journal gap or record hash drift')
        records.append(record)
    head = validate_manual_history(records, namespace=namespace, generated_at=generated_at)
    if head != expected_head_sha256:
        raise ValueError('manual journal head conflict')
    record = build_manual_record(body, previous_record_sha256=head, namespace=namespace, generated_at=generated_at)
    validate_manual_history([*records, record], namespace=namespace, generated_at=generated_at)
    # A stable sequence claim prevents concurrent writers from creating two heads.
    folder.mkdir(parents=True, exist_ok=True)
    claim = folder/f'{len(records)+1:08d}.claim'
    with claim.open('xb') as stream:
        stream.write(record_sha256(record).encode('ascii'))
    path = folder/f'{len(records)+1:08d}-{record_sha256(record)[:24]}.json'
    _write_new_json(path, record)
    return dict(schema_version='dual-sleeve-manual-record-receipt-v1', action='no_order',
        record_sha256=record_sha256(record), kind=body['kind'], namespace=namespace,
        changes_holdings=False, acceptance_authority='NONE')
