"""Read-only import of a separate private CSV input area; blanks are never zero."""
from __future__ import annotations

import csv
from io import StringIO
import json

from ...domain.portfolio.dual_sleeve_risk import CORE, HOTSPOT, decimal, fields, review_dual_sleeve_risk

POLICY = ('policy_id', 'policy_version', 'as_of', 'confirmation_status', 'confirmed_at',
    'account_scope', 'investable_assets_cny', 'minimum_cash_cny', 'emergency_cash_cny',
    'liquidity_needs_cny', 'time_horizon_years', 'max_single_security_pct',
    'max_single_industry_pct', 'max_cyclical_exposure_pct', 'dividend_income_goal_cny',
    'risk_tolerance', 'concentration_allowed', 'tax_regime', 'restrictions')
SNAPSHOT = ('snapshot_id', 'snapshot_version', 'as_of', 'available_at', 'account_scope',
    'cash_cny', 'reconciliation_status', 'reconciled_at', 'holdings')
SHARED = ('core_value_budget', 'tactical_hotspot_budget', 'cash_floor',
    'cross_sleeve_single_stock_cap', 'cross_sleeve_sector_cap', 'policy_scope')
SLEEVE_FIELDS = ('cash_cny', 'risk_budget_cny', 'max_single_security_fraction',
    'max_industry_fraction', 'max_factor_fraction', 'single_trade_risk_fraction',
    'single_security_risk_cny', 'realized_pnl_cny', 'financing_allowed',
    'risk_tools_allowed', 'confirmed_at')
REQUIRED = {
    'IPS': set(POLICY)-{'emergency_cash_cny', 'liquidity_needs_cny', 'max_cyclical_exposure_pct',
        'dividend_income_goal_cny', 'tax_regime', 'restrictions'},
    'SNAPSHOT': set(SNAPSHOT), 'SHARED_BUDGET': set(SHARED),
    CORE: set(SLEEVE_FIELDS)-{'single_trade_risk_fraction', 'single_security_risk_cny', 'realized_pnl_cny'},
    HOTSPOT: set(SLEEVE_FIELDS)-{'realized_pnl_cny'},
    'CASH_RESERVE': {'cash_cny'}, 'ALLOCATIONS': {'rows'}, 'SECURITY_ATTRIBUTES': {'rows'},
}
ALLOWED = dict(IPS=set(POLICY), SNAPSHOT=set(SNAPSHOT), SHARED_BUDGET=set(SHARED),
    CORE_VALUE=set(SLEEVE_FIELDS), HOTSPOT_SATELLITE=set(SLEEVE_FIELDS),
    CASH_RESERVE={'cash_cny'}, ALLOCATIONS={'rows'}, SECURITY_ATTRIBUTES={'rows'}, HOTSPOT_REQUEST={'request'})
BOOLEANS = {'concentration_allowed', 'financing_allowed', 'risk_tools_allowed'}
NUMBERS = {'investable_assets_cny', 'minimum_cash_cny', 'emergency_cash_cny', 'liquidity_needs_cny',
    'time_horizon_years', 'max_single_security_pct', 'max_single_industry_pct', 'max_cyclical_exposure_pct',
    'dividend_income_goal_cny', 'cash_cny', 'core_value_budget', 'tactical_hotspot_budget', 'cash_floor',
    'cross_sleeve_single_stock_cap', 'cross_sleeve_sector_cap', 'risk_budget_cny',
    'max_single_security_fraction', 'max_industry_fraction', 'max_factor_fraction',
    'single_trade_risk_fraction', 'single_security_risk_cny'}


def _structured_cell(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate structured private cell key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite structured private cell: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def parse_dual_sleeve_input_rows(rows, *, namespace='ACTUAL', generated_at, allow_synthetic=False):
    """Consume rows supplied by CSV or a future private Excel adapter, without writes."""
    if namespace not in ('ACTUAL', 'SIMULATED') or (namespace == 'SIMULATED' and not allow_synthetic):
        raise ValueError('private sheet namespace cannot implicitly enable synthetic input')
    values, sources = {}, {}
    for row in rows:
        fields(row, ('section', 'field', 'value', 'source_ref'), 'private input row')
        section, field = row['section'], row['field']
        if section not in ALLOWED or field not in ALLOWED[section]:
            raise ValueError('unknown private input field')
        key = (section, field)
        if key in values:
            raise ValueError('duplicate private input field')
        raw = row['value']
        if not isinstance(raw, str) or not isinstance(row['source_ref'], str):
            raise ValueError('private sheet cells must be text')
        raw = raw.strip()
        value = None
        if raw:
            if not row['source_ref'].strip():
                raise ValueError('populated private input requires source_ref')
            if field in BOOLEANS:
                if raw not in ('true', 'false'):
                    raise ValueError('private input booleans must be true or false')
                value = raw == 'true'
            elif field in NUMBERS:
                value = str(decimal(raw, section + '.' + field))
            elif field in ('holdings', 'rows', 'request'):
                # Existing structured holding/attribute contracts stay intact.
                value = _structured_cell(raw)
                if field == 'request':
                    if value is not None and not isinstance(value, dict):
                        raise ValueError('hotspot request requires an object or explicit null')
                elif not isinstance(value, list):
                    raise ValueError('holdings/rows require explicit JSON arrays; [] means confirmed empty')
            elif field == 'restrictions':
                value = [item.strip() for item in raw.split('|') if item.strip()]
            else:
                value = raw
        values[key] = value
        sources[key] = row['source_ref'].strip()
    missing = [section + '.' + field for section, names in REQUIRED.items()
        for field in sorted(names) if values.get((section, field)) is None]
    if missing:
        return dict(schema_version='dual-sleeve-private-input-validation-v1', action='no_order',
            status='INPUT_INCOMPLETE', missing_inputs=missing, payload=None, risk_report=None)
    def section(name, names):
        return {field: values.get((name, field)) for field in names}
    def evidence(name):
        return [dict(id=f'{name}.{field}', source_ref=source)
            for (group, field), source in sources.items() if group == name and source]
    policy = dict(section('IPS', POLICY), action='no_order', evidence_refs=evidence('IPS'))
    policy['restrictions'] = policy['restrictions'] or []
    snapshot = dict(section('SNAPSHOT', SNAPSHOT), action='no_order', namespace=namespace,
        evidence_refs=evidence('SNAPSHOT'))
    sleeve_policies = {name: dict(section(name, SLEEVE_FIELDS), evidence_ref='|'.join(
        source for (group, _), source in sources.items() if group == name and source)) for name in (CORE, HOTSPOT)}
    payload = dict(schema_version='dual-sleeve-risk-input-v1', action='no_order', namespace=namespace,
        portfolio=dict(schema_version='m4-portfolio-contracts-v1', action='no_order', policy=policy, snapshot=snapshot),
        shared_budget=dict(section('SHARED_BUDGET', SHARED), action='no_order'), sleeves=sleeve_policies,
        cash_reserve_cny=values[('CASH_RESERVE', 'cash_cny')], allocations=values[('ALLOCATIONS', 'rows')],
        security_attributes=values[('SECURITY_ATTRIBUTES', 'rows')],
        hotspot_request=values.get(('HOTSPOT_REQUEST', 'request')))
    report = review_dual_sleeve_risk(payload, generated_at=generated_at, allow_synthetic=allow_synthetic)
    return dict(schema_version='dual-sleeve-private-input-validation-v1', action='no_order',
        status='INPUT_VALIDATED' if report['sleeves'] is not None else 'INPUT_INCOMPLETE',
        missing_inputs=report['blockers'] if report['sleeves'] is None else [], payload=payload, risk_report=report)


def parse_dual_sleeve_input_csv(content, *, namespace='ACTUAL', generated_at, allow_synthetic=False):
    reader = csv.DictReader(StringIO(content.removeprefix('\ufeff')))
    if reader.fieldnames != ['section', 'field', 'value', 'source_ref']:
        raise ValueError('private CSV requires section,field,value,source_ref header')
    return parse_dual_sleeve_input_rows(list(reader), namespace=namespace,
        generated_at=generated_at, allow_synthetic=allow_synthetic)
