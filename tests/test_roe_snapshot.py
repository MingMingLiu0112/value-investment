import json
import pytest
from value_investment_agent.roe_scope import SIMPLE_LABEL, snapshot_proves_simple_roe


def payload(**changes):
    data = {'code':'000001','report_date':'2025-12-31', 'row':{SIMPLE_LABEL:'7.73'}}
    data.update(changes)
    return json.dumps(data).encode()


def test_exact_retained_column_proves_ordinary_roe():
    assert snapshot_proves_simple_roe(payload(), '000001', '2025-12-31', '7.7300')


@pytest.mark.parametrize('changes', [
    {'code':'000651'}, {'report_date':'2026-06-30'}, {'row':{}}, {'row':[]},
    {'row':{SIMPLE_LABEL:'NaN'}}, {'row':{SIMPLE_LABEL:'9.15'}},
])
def test_wrong_identity_or_value_blocks(changes):
    assert not snapshot_proves_simple_roe(payload(**changes), '000001', '2025-12-31', '7.73')


@pytest.mark.parametrize('raw',[b'invalid', b'[]', b'null', b'\xff'])
def test_invalid_snapshot_blocks(raw):
    assert not snapshot_proves_simple_roe(raw, '000001', '2025-12-31', '7.73')
