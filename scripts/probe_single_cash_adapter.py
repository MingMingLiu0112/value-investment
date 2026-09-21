"""Check the actual installed adapter without network calls or database writes."""
from pathlib import Path
import hashlib
import sys
from types import SimpleNamespace
import pandas as pd
from value_investment_agent import adapters

expected = sys.argv[1]
assert hashlib.sha256(Path(adapters.__file__).read_bytes()).hexdigest() == expected
balance = pd.DataFrame([
    {'报告日': '20260630', '类型': '合并报表', '货币资金': 5000000000},
    {'报告日': '20251231', '类型': '合并报表', '货币资金': 4000000000},
])
sys.modules['akshare'] = SimpleNamespace(stock_financial_report_sina=lambda stock, symbol:
    balance if symbol == '资产负债表' else pd.DataFrame([
        {'报告日': '20260630'}, {'报告日': '20251231'}]))
rows = adapters.SinaFinancialStatementsAdapter().fetch(['600519'])
cash = [r for r in rows if r.field_name == 'cash']
assert len(cash) == 2
assert {r.period_label: r.value for r in cash} == {'2026-06-30': 5000000000, '2025-12-31': 4000000000}
assert all(r.unit == 'CNY' and r.point_metadata['statement_scope'] == 'consolidated' for r in cash)
print('Installed adapter hash and two-period cash preservation passed; synthetic inputs only')
