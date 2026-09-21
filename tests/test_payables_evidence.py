from copy import deepcopy
import pytest
from value_investment_agent.payables_evidence import FIELDS, SOURCE, validate_payables_components


def fixture():
    values = dict(zip(FIELDS, ['11525169161', '23000000']))
    match = dict(source_name=SOURCE, source_id='snapshot', unit='CNY', value='11548169161',
        metadata=dict(statement_scope='consolidated', components_same_raw_snapshot=True,
                      derivation_formula=' + '.join(FIELDS), source_components=values))
    rows = [dict(field_name=f, value=v, symbol='000338', period_label='2025-12-31',
                 source_id='snapshot',data_point_id=f,unit='CNY', validation_status='pending',
                 metadata={'statement_scope':'consolidated'}) for f,v in values.items()]
    return match, rows


def test_retained_components_reconcile():
    match, rows = fixture()
    assert validate_payables_components(match, rows, '000338', '2025-12-31')


@pytest.mark.parametrize('field,value', [('symbol','000683'),('period_label','2024-12-31'),
    ('source_id','other'),('value','0'),('unit','CNY 10K'),('validation_status','failed'),('data_point_id',None)])
def test_wrong_input_never_passes(field,value):
    match, rows = fixture()
    rows[0][field] = value
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')


def test_missing_duplicate_or_unscoped_input_blocks():
    match, rows = fixture()
    assert not validate_payables_components(match, rows[:1], '000338', '2025-12-31')
    assert not validate_payables_components(match, rows+[deepcopy(rows[0])], '000338', '2025-12-31')
    rows[0]['metadata']['statement_scope'] = 'unspecified'
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')


def test_missing_shared_source_cannot_establish_same_snapshot():
    match, rows = fixture()
    match['source_id'] = None
    for row in rows:
        row['source_id'] = None
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')


@pytest.mark.parametrize('bad_metadata', ['invalid', ['consolidated'], 1])
def test_malformed_metadata_blocks_without_crashing(bad_metadata):
    match, rows = fixture()
    match['metadata'] = bad_metadata
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')
    match, rows = fixture()
    rows[0]['metadata'] = bad_metadata
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')


@pytest.mark.parametrize('components', [None, [], 'invalid', {}])
def test_malformed_components_block(components):
    match, rows = fixture()
    match['metadata']['source_components'] = components
    assert not validate_payables_components(match, rows, '000338', '2025-12-31')
