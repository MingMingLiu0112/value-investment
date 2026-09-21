"""Identify supplemental provider fields from retained, unconverted values."""
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation

from value_investment_agent.adapters import SinaFinancialAdapter

REPLACEMENTS = {
    'net_margin': 'provider_sales_net_margin',
    'revenue_yoy': 'main_business_revenue_yoy',
    'net_income_yoy': 'provider_net_income_yoy',
    'operating_cash_flow_to_net_income': 'provider_cashflow_profit_ratio',
}


def snapshot_proves_provider_field(payload, symbol, period, field, value, unit):
    if field not in REPLACEMENTS or unit != 'percent':
        return False
    label = SinaFinancialAdapter._fields[REPLACEMENTS[field]][0]
    try:
        snapshot = json.loads(payload)
        if not isinstance(snapshot, dict) or snapshot.get('code') != symbol:
            return False
        if datetime.fromisoformat(str(snapshot['report_date'])).date().isoformat() != period:
            return False
        if not isinstance(snapshot.get('row'), dict):
            return False
        raw = Decimal(str(snapshot['row'][label]))
        expected = Decimal(str(value))
        return raw.is_finite() and expected.is_finite() and raw == expected
    except (ValueError, TypeError, KeyError, InvalidOperation, UnicodeDecodeError):
        return False
