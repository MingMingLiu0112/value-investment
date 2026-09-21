import json
import pytest
from value_investment_agent.adapters import SinaFinancialAdapter
from value_investment_agent.provider_scope import REPLACEMENTS, snapshot_proves_provider_field


@pytest.mark.parametrize('field', REPLACEMENTS)
def test_only_exact_unconverted_source_value_is_proven(field):
    label = SinaFinancialAdapter._fields[REPLACEMENTS[field]][0]
    data = {'code': '000333', 'report_date': '2025-12-31', 'row': {label: '1.1982'}}
    raw = json.dumps(data).encode()
    assert snapshot_proves_provider_field(raw, '000333', '2025-12-31', field, '1.1982', 'percent')
    for symbol, period, value, unit in [
        ('000001', '2025-12-31', '1.1982', 'percent'),
        ('000333', '2024-12-31', '1.1982', 'percent'),
        ('000333', '2025-12-31', '119.82', 'percent'),
        ('000333', '2025-12-31', '1.1982', 'ratio'),
    ]:
        assert not snapshot_proves_provider_field(raw, symbol, period, field, value, unit)


@pytest.mark.parametrize('raw', [b'null', b'[]', b'invalid', b'\xff', b'{}',
    b'{"code":"000333","report_date":"2025-12-31","row":[]}'])
def test_invalid_evidence_rejected(raw):
    assert not snapshot_proves_provider_field(raw, '000333', '2025-12-31', 'net_margin', '1', 'percent')
