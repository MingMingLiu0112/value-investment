"""General CSRC thresholds as research references, never compliance approval."""
from datetime import date
from decimal import Decimal, InvalidOperation


RULE_URL = 'https://www.csrc.gov.cn/csrc/c101954/c7507765/content.shtml'
RULE_SHA256 = '6259b9d61918aaa5491a514cd161a9e3ccf5d7f78cb320eac3b94f3f19f8b530'
REVIEWED_THROUGH = date(2026, 9, 8)
MINIMUMS = {'risk_coverage': Decimal('100'), 'capital_leverage': Decimal('8'),
            'liquidity_coverage': Decimal('100'), 'net_stable_funding': Decimal('100')}


def reference(field, period, value):
    """Compare a disclosed percentage without asserting data or scope validity."""
    try:
        day = date.fromisoformat(str(period))
    except (ValueError, TypeError):
        return None
    if field not in MINIMUMS or not date(2025, 1, 1) <= day <= REVIEWED_THROUGH:
        return None
    minimum = MINIMUMS[field]
    warning = minimum * Decimal('1.2')
    position = '缺值，不能对照'
    try:
        number = Decimal(str(value))
        if isinstance(value, bool) or not number.is_finite() or number < 0:
            raise ValueError('Invalid ratio')
        if number < minimum:
            position = '数值低于一般监管下限'
        elif number <= warning:
            position = '数值处于一般预警区间'
        else:
            position = '数值高于一般预警线'
    except (InvalidOperation, ValueError, TypeError):
        pass
    return {'minimum': minimum, 'warning': warning, 'position': position,
            'source_url': RULE_URL, 'source_sha256': RULE_SHA256,
            'regulatory_compliance_verified': False,
            'limitation': '仅对照一般标准；数据、主体口径及个别监管要求仍须核实，不构成合规或投资结论'}
