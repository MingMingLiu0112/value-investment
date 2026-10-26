"""Verify explicit local bytes independently of official-source URLs."""
from pathlib import Path
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any, Mapping

from .common import require_inside, sha256_file

SOURCE_BOUND_PACKAGE_SCHEMA = 'm1-valuation-package-v2'
SOURCE_CONTRACT_SCHEMA = 'source-bound-research-inputs-v2'
CONSUMED_FACT_CONTRACT_SCHEMA = 'source-bound-research-inputs-v3'
LEGACY_SOURCE_CONTRACT_SCHEMA = 'source-bound-research-inputs-v1'


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
    from ...valuation_models.residual_income_path_v2 import ResidualIncomePathScenarioInputs
    if is_dataclass(value):
        values = {field.name: getattr(value, field.name) for field in fields(value)}
        if isinstance(value, ResidualIncomePathScenarioInputs):
            # The v2 constructor fixes/validates these compatibility labels.
            # Every *consumed numeric* annual retention remains bound below.
            values.pop('retention')
            values.pop('currency')
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


def source_catalog_sha256(sources: Any) -> str:
    """Hash every source field so extended availability metadata is not free text."""
    if not isinstance(sources, (list, tuple)) or not sources:
        raise ValueError('source-bound package requires a nonempty source catalog')
    def normalize(value: Any) -> Any:
        if isinstance(value, str):
            return value.replace('\\', '/')
        if isinstance(value, Mapping):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item) for item in value]
        return value
    payload = {'schema_version': 'source-catalog-v1', 'sources': normalize(list(sources))}
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, allow_nan=False,
        separators=(',', ':'),
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _validate_fact_anchors(
    payload: Mapping[str, Any], descriptor, contract: Mapping[str, Any], *, strict: bool,
) -> None:
    if not strict:
        return
    anchors = contract.get('fact_anchors')
    if anchors is None:
        return
    if not isinstance(anchors, list):
        raise ValueError('source contract fact_anchors must be a list')
    catalog = {source['id']: source for source in payload['sources']}
    fact_source_ids = {
        ref.get('id') for ref in getattr(descriptor.facts, 'evidence_refs', ())
        if isinstance(ref, Mapping)
    }
    summary = getattr(descriptor.research_case, 'financial_summary', {})
    seen = set()
    for anchor in anchors:
        if not isinstance(anchor, Mapping):
            raise ValueError('source contract fact anchor must be an object')
        source_id = anchor.get('source_id')
        source = catalog.get(source_id)
        field = anchor.get('field')
        allowed_kinds = {'official_issuer_filing'}
        if contract.get('schema_version') == CONSUMED_FACT_CONTRACT_SCHEMA:
            allowed_kinds.add('official_exchange_filing')
        if source is None or source.get('kind') not in allowed_kinds:
            raise ValueError('fact anchor requires a bound official issuer filing')
        if source_id not in fact_source_ids:
            raise ValueError('fact anchor source is not consumed by financial facts')
        if not isinstance(field, str) or not field or field in seen:
            raise ValueError('fact anchors require unique financial fields')
        seen.add(field)
        if field not in summary:
            raise ValueError('fact anchor field is absent from the research case')
        page = anchor.get('physical_page')
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError('fact anchor requires a positive physical page')
        for key in ('unit', 'scope', 'period_end'):
            if not isinstance(anchor.get(key), str) or not anchor[key].strip():
                raise ValueError(f'fact anchor requires {key}')
        if _decimal(anchor.get('source_value')) != _decimal(summary[field]):
            raise ValueError('fact anchor value differs from the research case')
        if 'sha256' in anchor and anchor['sha256'] != source.get('sha256'):
            raise ValueError('fact anchor hash differs from the source catalog')


def _validate_anchor_normalization(anchor, anchors_by_field) -> None:
    derivation = anchor.get('derivation')
    if derivation is None:
        return
    if not isinstance(derivation, Mapping) or set(derivation) != {'rule', 'component_fields'}:
        raise ValueError('fact anchor normalization requires a known rule and components')
    components = derivation['component_fields']
    if (not isinstance(components, list) or not components
            or any(not isinstance(field, str) for field in components)
            or len(set(components)) != len(components)):
        raise ValueError('fact anchor normalization requires unique component fields')
    rows = []
    for field in components:
        row = anchors_by_field.get(field)
        if (row is None or field == anchor['field'] or row.get('derivation') is not None
                or any(row.get(key) != anchor.get(key)
                       for key in ('source_id', 'physical_page', 'period_end', 'scope'))):
            raise ValueError('fact anchor normalization component source/period/scope mismatch')
        rows.append(row)
    if derivation['rule'] == 'SUM_COMPONENTS':
        if len(rows) < 2 or anchor['unit'] != 'shares' or any(row['unit'] != 'shares' for row in rows):
            raise ValueError('share normalization requires at least two share components')
        values = [_decimal(row['source_value']) for row in rows]
        if any(value <= 0 or value != value.to_integral_value() for value in values):
            raise ValueError('share normalization components must be positive integral shares')
        normalized = sum(values, Decimal(0))
    elif derivation['rule'] == 'CNY_THOUSANDS_TO_CNY':
        if len(rows) != 1 or rows[0]['unit'] != 'CNY_thousand' or anchor['unit'] != 'CNY':
            raise ValueError('currency normalization requires one thousand-CNY source')
        normalized = _decimal(rows[0]['source_value']) * 1000
    else:
        raise ValueError('unsupported fact anchor normalization rule')
    if normalized != _decimal(anchor['source_value']):
        raise ValueError('normalized fact anchor differs from its source components')


def _validate_consumed_fact_bindings(descriptor, contract: Mapping[str, Any]) -> None:
    """Bind normalized capital facts to model inputs, not merely display facts.

    This authenticates consistency with declared, hash-bound source anchors;
    it does not certify issuer semantics or grant financial/research approval.
    Undeclared conversions and derived capital inputs must not silently pass.
    """
    share_basis = contract.get('share_basis')
    if share_basis not in {'issued_ordinary_shares', 'ordinary_shares_excluding_treasury'}:
        raise ValueError('consumed fact contract requires an explicit ordinary share basis')
    expected = {
        'start_book_equity': ('CNY', 'consolidated_parent_equity'),
        'ordinary_shares': ('shares', share_basis),
    }
    required = getattr(descriptor.facts, 'REQUIRED_COMMON_INPUTS', ())
    if set(required) != set(expected):
        raise ValueError('consumed fact contract requires a supported model input basis')
    anchors = contract.get('fact_anchors')
    bindings = contract.get('consumed_fact_bindings')
    if not isinstance(anchors, list) or not anchors or not isinstance(bindings, list) or not bindings:
        raise ValueError('consumed fact contract requires anchors and consumed fact bindings')
    anchors_by_field = {anchor['field']: anchor for anchor in anchors}
    timing = getattr(descriptor.facts, 'valuation_timing', None)
    basis = (timing.basis_at.astimezone(timezone(timedelta(hours=8))).date()
        if timing is not None else descriptor.facts.as_of)
    seen = set()
    consumed_anchors = set()
    for binding in bindings:
        if not isinstance(binding, Mapping) or set(binding) - {'field_path', 'anchor_field', 'operation'}:
            raise ValueError('consumed fact binding has unsupported fields or conversion')
        path = binding.get('field_path')
        valid_paths = {'operating_inputs.' + field for field in expected}
        if (not isinstance(path, str) or path not in valid_paths or path in seen
                or binding.get('operation', 'DIRECT') != 'DIRECT'):
            raise ValueError('consumed fact bindings require unique supported direct input paths')
        seen.add(path)
        field = path.split('.')[1]
        anchor_field = binding.get('anchor_field')
        if not isinstance(anchor_field, str) or anchor_field not in anchors_by_field:
            raise ValueError('consumed fact binding requires an existing fact anchor')
        anchor = anchors_by_field[anchor_field]
        consumed_anchors.add(anchor_field)
        _validate_anchor_normalization(anchor, anchors_by_field)
        unit, scope = expected[field]
        if (anchor.get('unit') != unit or anchor.get('scope') != scope
                or anchor.get('period_end') != basis.isoformat()):
            raise ValueError('consumed fact anchor unit/scope/period mismatch')
        value = _decimal(descriptor.facts.operating_inputs.get(field))
        if value <= 0 or (field == 'ordinary_shares' and value != value.to_integral_value()):
            raise ValueError('consumed capital facts require positive canonical values and integral shares')
        if value != _decimal(anchor['source_value']):
            raise ValueError('consumed model input differs from its source fact anchor')
    if seen != {'operating_inputs.' + field for field in required}:
        raise ValueError('consumed fact bindings must cover every required model input')
    if any('derivation' in anchor and anchor['field'] not in consumed_anchors for anchor in anchors):
        raise ValueError('fact anchor normalization must target a consumed model input')


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
    contract_schema = contract.get('schema_version')
    if contract_schema not in {CONSUMED_FACT_CONTRACT_SCHEMA, SOURCE_CONTRACT_SCHEMA, LEGACY_SOURCE_CONTRACT_SCHEMA}:
        raise ValueError('source-bound package requires a versioned source contract')
    strict = contract_schema in {SOURCE_CONTRACT_SCHEMA, CONSUMED_FACT_CONTRACT_SCHEMA}
    descriptor_contract = getattr(descriptor, 'source_contract', None)
    if descriptor_contract is None or descriptor_contract.as_policy() != dict(contract):
        raise ValueError('source contract is not bound into the input descriptor')
    expected_catalog = contract.get('source_catalog_sha256')
    if strict:
        if expected_catalog != source_catalog_sha256(payload['sources']):
            raise ValueError('source catalog hash differs from the declared contract')
    elif expected_catalog is not None and expected_catalog != source_catalog_sha256(payload['sources']):
        raise ValueError('source catalog hash differs from the declared contract')
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
        retrieved = (
            _timestamp(source.get('retrieved_at'), 'source retrieved_at')
            if source.get('retrieved_at') is not None
            else None
        )
        if not source.get('availability_basis'):
            raise ValueError('source availability requires an explicit basis')
        published = source.get('published_at')
        if published and available < _timestamp(published, 'source published_at'):
            raise ValueError('source availability precedes publication')
        if available > cutoff:
            raise ValueError('source input follows research cutoff')
        if retrieved is not None and retrieved > cutoff:
            raise ValueError('source retrieval follows research cutoff')
        if retrieved is not None and retrieved < available:
            raise ValueError('source retrieval precedes observed availability')
        if strict and retrieved is None:
            raise ValueError('source-bound v2 requires every source retrieval time')
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

    validity_input = getattr(descriptor, 'model_validity_input', None)
    event_scan = getattr(validity_input, 'event_scan', None)
    declared_coverage = contract.get('event_coverage_status')
    if event_scan is not None:
        if strict:
            if declared_coverage != event_scan.coverage_status:
                raise ValueError('event coverage status differs from the bound event scan')
        if event_scan.retrieved_at > cutoff:
            raise ValueError('event scan retrieval follows research cutoff')
        if (
            event_scan.coverage_status != 'COMPLETE'
            and 'EVENT_COVERAGE_INCOMPLETE'
            not in getattr(validity_input, 'blockers', ())
        ):
            raise ValueError('incomplete event coverage requires an explicit blocker')

    _validate_fact_anchors(
        payload,
        descriptor,
        contract,
        strict=strict,
    )
    if contract_schema == CONSUMED_FACT_CONTRACT_SCHEMA:
        _validate_consumed_fact_bindings(descriptor, contract)

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
