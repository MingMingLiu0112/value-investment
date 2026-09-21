"""Read-only exact-period provider comparison with retained official growth figures."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

spec = importlib.util.spec_from_file_location('value_investment_agent.growth_adapter',
                                            Path(__file__).with_name('adapters.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
values = {}
for period in ['2025-12-31','2024-12-31']:
    records = module.SinaFinancialStatementsAdapter().fetch(['000333'],report_period=period)
    records += module.AkshareFinancialAbstractAdapter().fetch(['000333'],report_period=period)
    values[period] = {r.field_name:r for r in records if r.field_name in ['revenue','net_income']}
for field, official in [('revenue',Decimal('12.11')),('net_income',Decimal('14.03'))]:
    current, previous = values['2025-12-31'][field], values['2024-12-31'][field]
    assert current.unit == previous.unit == 'CNY' and previous.value > 0
    growth = (current.value / previous.value - 1) * 100
    print(json.dumps({'field':field,'current':str(current.value),'previous':str(previous.value),
        'calculated_growth':str(growth),'official_growth':str(official),
        'matches':abs(growth-official)<=Decimal('0.05'),
        'current_url':current.source_url,'previous_url':previous.source_url}),flush=True)
