"""The private input area is separate; blank cells never masquerade as zero."""
from copy import deepcopy
import csv
from io import StringIO
import json
from pathlib import Path

import pytest

from test_dual_sleeve_risk import synthetic_input, GENERATED_AT, CORE, HOTSPOT
from value_investment_agent.application.product.dual_sleeve_input_sheet import (
    parse_dual_sleeve_input_csv, parse_dual_sleeve_input_rows, POLICY, SNAPSHOT, SHARED, SLEEVE_FIELDS,
)


def populated_rows():
    payload = synthetic_input()
    groups = [('IPS', payload['portfolio']['policy'], POLICY),
        ('SNAPSHOT', payload['portfolio']['snapshot'], SNAPSHOT),
        ('SHARED_BUDGET', payload['shared_budget'], SHARED),
        (CORE, payload['sleeves'][CORE], SLEEVE_FIELDS),
        (HOTSPOT, payload['sleeves'][HOTSPOT], SLEEVE_FIELDS),
        ('CASH_RESERVE', {'cash_cny': payload['cash_reserve_cny']}, ['cash_cny']),
        ('ALLOCATIONS', {'rows': payload['allocations']}, ['rows']),
        ('SECURITY_ATTRIBUTES', {'rows': payload['security_attributes']}, ['rows']),
        ('HOTSPOT_REQUEST', {'request': payload['hotspot_request']}, ['request'])]
    rows = []
    for group, source, names in groups:
        for field in names:
            value = source.get(field)
            if isinstance(value, bool): value = str(value).lower()
            elif field == 'restrictions': value = '|'.join(value)
            elif isinstance(value, (list, dict)): value = json.dumps(value)
            rows.append(dict(section=group, field=field, value='' if value is None else str(value),
                source_ref='synthetic-user-source'))
    return rows


def test_empty_csv_template_preserves_missing_values_without_writes():
    template = Path(__file__).resolve().parents[1]/'config/private-template/dual-sleeve-private-input-v1.csv'
    original = template.read_bytes()
    result = parse_dual_sleeve_input_csv(original.decode('utf-8'), generated_at=GENERATED_AT)
    assert result['status'] == 'INPUT_INCOMPLETE'
    assert result['payload'] is result['risk_report'] is None
    assert 'CORE_VALUE.cash_cny' in result['missing_inputs']
    assert template.read_bytes() == original


def test_populated_input_area_reuses_existing_contracts_and_preserves_explicit_zero():
    rows = populated_rows()
    before = deepcopy(rows)
    result = parse_dual_sleeve_input_rows(rows, namespace='SIMULATED', generated_at=GENERATED_AT, allow_synthetic=True)
    assert result['status'] == 'INPUT_VALIDATED'
    assert result['risk_report']['aggregate']['total_assets_cny'] == '10000'
    assert result['payload']['portfolio']['snapshot']['holdings'][0]['quantity'] == '100'
    assert result['payload']['sleeves'][CORE]['realized_pnl_cny'] is None
    assert rows == before
    pnl = next(row for row in rows if row['section'] == CORE and row['field'] == 'realized_pnl_cny')
    pnl['value'] = '0'
    assert parse_dual_sleeve_input_rows(rows, namespace='SIMULATED', generated_at=GENERATED_AT,
        allow_synthetic=True)['risk_report']['sleeves'][CORE]['realized_pnl_cny'] == '0'
    cash = next(row for row in rows if row['section'] == CORE and row['field'] == 'cash_cny')
    cash['value'] = ''
    assert parse_dual_sleeve_input_rows(rows, namespace='SIMULATED', generated_at=GENERATED_AT,
        allow_synthetic=True)['status'] == 'INPUT_INCOMPLETE'


@pytest.mark.parametrize('bad', ['duplicate', 'unknown', 'formula', 'no_source', 'implicit_simulation'])
def test_private_sheet_bad_inputs_fail_closed(bad):
    rows = populated_rows()
    if bad == 'duplicate': rows.append(deepcopy(rows[0]))
    if bad == 'unknown': rows[0]['field'] = 'order_quantity'
    if bad == 'formula':
        next(row for row in rows if row['section'] == CORE and row['field'] == 'cash_cny')['value'] = '=SUM(A1:A2)'
    if bad == 'no_source': rows[0]['source_ref'] = ''
    with pytest.raises(ValueError):
        parse_dual_sleeve_input_rows(rows, namespace='SIMULATED', generated_at=GENERATED_AT,
            allow_synthetic=bad != 'implicit_simulation')


@pytest.mark.parametrize('raw', ['[{"symbol":"600519","symbol":"600000"}]', '[NaN]'])
def test_structured_private_cell_rejects_duplicate_or_nonfinite_json(raw):
    rows = populated_rows()
    next(row for row in rows if row['section'] == 'SNAPSHOT' and row['field'] == 'holdings')['value'] = raw
    with pytest.raises(ValueError):
        parse_dual_sleeve_input_rows(rows, namespace='SIMULATED', generated_at=GENERATED_AT, allow_synthetic=True)
