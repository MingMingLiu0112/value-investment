"""Validate staged exact-period collection against retained official sample values."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path

from value_investment_agent.candidate_review import values_agree

spec = importlib.util.spec_from_file_location('value_investment_agent.period_probe_adapter',
                                            Path(__file__).with_name('adapters.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
records = module.AkshareFinancialAbstractAdapter().fetch(['000333'], report_period='2025-12-31')
official = {'revenue': Decimal('456451731000'), 'net_income': Decimal('43945411000'),
            'operating_cash_flow': Decimal('53345930000')}
results = []
for record in records:
    if record.field_name in official:
        results.append({'field':record.field_name,'period':record.period_label,
                        'secondary_value':str(record.value),'unit':record.unit,
                        'official_value':str(official[record.field_name]),
                        'source_url':record.source_url,
                        'matches':values_agree(official[record.field_name],record.value,record.unit)})
print(json.dumps({'symbol':'000333','records':len(records),'comparison':results},ensure_ascii=False))
if {r['field'] for r in results} != set(official) or not all(r['matches'] for r in results):
    raise SystemExit('Official comparison incomplete or conflicting; no data promoted')
