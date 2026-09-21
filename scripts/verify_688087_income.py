"""Verify committed corrected income and retained quarantine of the old summary."""
import json
import argparse
from decimal import Decimal
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings

parser = argparse.ArgumentParser()
parser.add_argument('--refresh', action='store_true')
args = parser.parse_args()
if args.refresh:
    from value_investment_agent.cli import _refresh_financial_quality
    from value_investment_agent.db import begin_run, end_run
    with connect(get_settings().database_url) as db:
        db.execute("SET lock_timeout='5s'")
        db.execute("SET statement_timeout='60s'")
        run = begin_run(db, 'refresh-corrected-income-dependencies')
        _refresh_financial_quality(db, ['688087'])
        end_run(db, run, 'succeeded', {'symbols':['688087']})

with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    point = db.execute("""SELECT p.value,p.validation_status,p.metadata,d.sha256,d.source_url
        FROM data_points p JOIN raw_documents d ON d.document_id=p.source_id
        WHERE p.symbol='688087' AND p.field_name='net_income' AND p.period_label='2025-12-31'
        ORDER BY p.created_at DESC,p.data_point_id DESC LIMIT 1""").fetchone()
    assert point['value']==Decimal('285734507.57') and point['validation_status']=='verified'
    assert point['metadata']['page_number']==125
    assert point['metadata']['automatic_cross_source_verification'] is True
    assert point['sha256']=='d5ea80d0a678586b178bb95bdedcabd00459fd23c98ea5601d772ec55adfaa9a'
    old = db.execute("""SELECT count(*) AS n FROM data_points
        WHERE metadata->>'candidate_id'='7ecc2c98-6b65-43cd-86ad-d56bf21d1bd9'
        AND validation_status='verified' AND NOT (metadata ? 'evidence_quarantine')""").fetchone()
    assert old['n']==0
    ratios = db.execute("""SELECT DISTINCT ON (field_name) field_name,value,validation_status,metadata
        FROM data_points WHERE symbol='688087' AND period_label='2025-12-31'
        AND field_name IN ('net_margin','operating_cash_flow_to_net_income')
        ORDER BY field_name,created_at DESC,data_point_id DESC""").fetchall()
    print(json.dumps({'corrected_income':point,'old_summary_not_trusted':True,
        'latest_annual_ratios':ratios},default=str))
