"""Verify explicit local bytes independently of official-source URLs."""
from pathlib import Path
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .common import require_inside, sha256_file

SOURCE_BOUND_PACKAGE_SCHEMA = 'm1-valuation-package-v2'


def _timestamp(value: Any, label: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} requires an ISO timestamp') from None
    if result.utcoffset() is None:
        raise ValueError(f'{label} requires a timezone')
    return result


def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ValueError('scenario assumption must be a finite numeric value')
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError('scenario assumption must be a finite numeric value') from None
    if not result.is_finite():
        raise ValueError('scenario assumption must be a finite numeric value')
    return result


def _scenario_leaves(value: Any, prefix: str = '') -> dict[str, Any]:
    if is_dataclass(value):
        values = {field.name: getattr(value, field.name) for field in fields(value)}
    elif isinstance(value, Mapping):
        values = dict(value)
    elif isinstance(value, (list, tuple)):
        values = {str(index): item for index, item in enumerate(value)}
    else:
        return {prefix: value}
    leaves = {}
    for key, item in values.items():
        path = f'{prefix}.{key}' if prefix else key
        leaves.update(_scenario_leaves(item, path))
    return leaves


def verify_package_local_sources(
    root: Path, payload: Mapping[str, Any],
) -> tuple[tuple[Path, str], ...]:
    sources = payload.get('sources') or []
    if payload.get('schema_version') == SOURCE_BOUND_PACKAGE_SCHEMA and not sources:
        raise ValueError('source-bound package requires local sources')
    if not any(isinstance(source, Mapping) and 'local_path' in source for source in sources):
        if payload.get('schema_version') == SOURCE_BOUND_PACKAGE_SCHEMA:
            raise ValueError('source-bound package cannot omit local binding metadata')
        return ()
    verified = []
    ids = set()
    for source in sources:
        if not isinstance(source, Mapping) or not source.get('id') or not source.get('local_path'):
            raise ValueError('source-bound package requires an explicit local path for every source')
        if source['id'] in ids:
            raise ValueError('source-bound package source ids must be unique')
        ids.add(source['id'])
        path = require_inside(root, root / source['local_path'], 'package source bytes')
        expected = source.get('sha256')
        if not isinstance(expected, str) or len(expected) != 64 or sha256_file(path) != expected.lower():
            raise ValueError('source-bound package source hash mismatch')
        verified.append((path, expected.lower()))
    return tuple(verified)


def validate_source_bound_descriptor(payload: Mapping[str, Any], descriptor) -> None:
    """Enforce the versioned real-input boundary without promoting research gates."""
    if payload.get('schema_version') != SOURCE_BOUND_PACKAGE_SCHEMA:
        return
    contract = payload.get('source_contract') or {}
    if contract.get('schema_version') != 'source-bound-research-inputs-v1':
        raise ValueError('source-bound package requires a versioned source contract')
    cutoff = _timestamp(contract.get('cutoff_at'), 'research cutoff')
    if cutoff.astimezone(timezone(timedelta(hours=8))).date() != descriptor.point_in_time.research_as_of:
        raise ValueError('research cutoff date differs from the declared research date')
    catalog = {source['id']: source for source in payload['sources']}
    def verify_reference(reference: Mapping[str, Any]) -> None:
        source = catalog.get(reference.get('id'))
        if source is None:
            raise ValueError('research evidence references an unbound source')
        if 'sha256' in reference:
            digest = reference['sha256']
            if not isinstance(digest, str) or digest.lower() != source['sha256'].lower():
                raise ValueError('research evidence hash differs from source catalog')
        for key in ('path', 'local_path'):
            if key in reference:
                path = reference[key]
                if not isinstance(path, str) or path.replace('\\', '/') != str(source['local_path']).replace('\\', '/'):
                    raise ValueError('research evidence path differs from source catalog')
    for source in payload['sources']:
        available = _timestamp(source.get('source_available_at'), 'source available_at')
        if not source.get('availability_basis'):
            raise ValueError('source availability requires an explicit basis')
        published = source.get('published_at')
        if published and available < _timestamp(published, 'source published_at'):
            raise ValueError('source availability precedes publication')
        if available > cutoff:
            raise ValueError('source input follows research cutoff')
    if cutoff > descriptor.point_in_time.available_at:
        raise ValueError('research output availability precedes its input cutoff')
    source_pairs = {(str(source['local_path']).replace('\\', '/'), source['sha256'])
                    for source in payload['sources']}
    for reference in (payload.get('quote') or {},
                      (payload.get('model_validity_input') or {}).get('event_scan_ref') or {}):
        path = reference.get('bundle_path', reference.get('path'))
        digest = reference.get('bundle_sha256', reference.get('sha256'))
        if path is not None and (str(path).replace('\\', '/'), digest) not in source_pairs:
            raise ValueError('consumed market input is not bound to the source catalog')
    for reference in getattr(descriptor.facts, 'evidence_refs', ()):
        verify_reference(reference)
        if reference.get('available_at') and _timestamp(reference['available_at'], 'fact available_at') > cutoff:
            raise ValueError('financial fact input follows research cutoff')
    if descriptor.quote is not None:
        for reference in descriptor.quote.evidence_refs:
            for key in ('fetched_at', 'observed_trade_at'):
                if reference.get(key) and _timestamp(reference[key], f'quote {key}') > cutoff:
                    raise ValueError('quote observation follows research cutoff')
    if contract.get('distribution_input_status') != 'NOT_ADMITTED':
        raise ValueError('source-bound v2 requires explicit unadmitted distribution scope')
    if descriptor.distribution_result is not None:
        raise ValueError('unadmitted distribution scope must not consume an implicit package')

    scenarios = getattr(descriptor.facts, 'scenario_inputs', None)
    assumptions = descriptor.assumptions
    if not scenarios or assumptions is None:
        raise ValueError('source-bound valuation requires explicit reviewed assumptions')
    for reference in assumptions.evidence_refs:
        verify_reference(reference)
    for reference in descriptor.research_case.evidence_refs:
        verify_reference(reference)
    required = {(scenario, path): value for scenario, inputs in scenarios.items()
                for path, value in _scenario_leaves(inputs).items()}
    named = {item.name: item for item in assumptions.assumptions}
    if len(named) != len(assumptions.assumptions):
        raise ValueError('source-bound assumptions must have unique names')
    seen = set()
    for binding in descriptor.assumption_bindings:
        key = (binding.scenario, binding.field_path)
        if key in seen or key not in required:
            raise ValueError('scenario bindings must be unique and reference consumed inputs')
        seen.add(key)
        assumption = named.get(binding.assumption_name)
        if assumption is None or not binding.evidence_refs or not assumption.evidence_refs:
            raise ValueError('scenario binding requires a named evidence-backed assumption')
        for reference in (*binding.evidence_refs, *assumption.evidence_refs):
            verify_reference(reference)
        reviewed = getattr(assumption, binding.scenario)
        if not (_decimal(reviewed) == _decimal(binding.expected_value)
                == _decimal(required[key])):
            raise ValueError('reviewed assumption differs from the consumed scenario input')
    if seen != set(required):
        raise ValueError('source-bound assumptions must cover every consumed scenario input')
