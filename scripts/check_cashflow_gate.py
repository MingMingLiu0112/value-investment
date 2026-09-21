"""Read-only exercise of the staged cashflow gate with retained database evidence."""
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

spec = importlib.util.spec_from_file_location('value_investment_agent.cashflow_review_ready',
    Path(__file__).with_name('cashflow_review_ready.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    db.execute("SET statement_timeout='30s'")
    facts = db.execute("""SELECT DISTINCT ON(p.symbol) p.symbol,p.value,p.unit,p.period_label
        FROM data_points p WHERE p.symbol=ANY(%s) AND p.field_name='operating_cash_flow'
        AND p.validation_status='verified' AND p.period_label='2025-12-31'
        AND NOT (p.metadata ? 'evidence_quarantine') AND NOT (p.metadata ? 'superseded_by_parser')
        ORDER BY p.symbol,p.created_at DESC,p.data_point_id DESC""",
        (['000709','000830','000858','000887','000928'],)).fetchall()
    results = []
    for fact in facts:
        matches = db.execute("""SELECT p.value,p.unit,p.metadata,p.data_point_id,d.source_name,d.local_path
            FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.symbol=%s AND p.period_label=%s AND p.field_name='operating_cash_flow'
              AND d.source_name LIKE 'AkShare / Sina%%'
              AND p.validation_status IN ('pending','verified')
              AND NOT (p.metadata ? 'evidence_quarantine')
              AND NOT (p.metadata ? 'superseded_by_parser')
            ORDER BY p.created_at DESC,p.data_point_id DESC""",
            (fact['symbol'],fact['period_label'])).fetchall()
        match = module.cashflow_secondary(matches,Decimal(fact['value']),fact['unit'])
        if match is None:
            raise ValueError('Scoped corroboration unavailable: '+fact['symbol'])
        results.append({'symbol':fact['symbol'],'source':match['source_name'],
            'scope':match['metadata']['statement_scope'],'data_point_id':str(match['data_point_id']),
            'archived':bool(match['local_path'])})
    if len(results)!=5:
        raise ValueError('Expected five retained company facts')
    print(json.dumps({'read_only':True,'results':results}))
