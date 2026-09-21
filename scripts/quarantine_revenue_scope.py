"""Transactional quarantine with same-transaction valuation/quality refresh."""
import argparse
import json

from evidence_dependencies import affected_point_ids
from evidence_quarantine import quarantine_metadata
from value_investment_agent.db import connect, begin_run, end_run, latest_points, upsert_valuation
from value_investment_agent.cli import _refresh_financial_quality
from value_investment_agent.quality import evaluate
from value_investment_agent.settings import get_settings
from decimal import Decimal
from value_investment_agent.cli import as_valuation_row


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--rehearse', action='store_true')
    args = parser.parse_args()
    settings = get_settings()
    with connect(settings.database_url) as db:
        db.execute("SET lock_timeout='5s'")
        db.execute("SET statement_timeout='60s'")
        # Block concurrent point writers for this short, all-or-nothing transition.
        if args.apply or args.rehearse:
            db.execute('LOCK TABLE data_points IN SHARE ROW EXCLUSIVE MODE')
        initial = db.execute("""SELECT p.data_point_id FROM data_points p
            JOIN raw_documents d ON d.document_id=p.source_id
            WHERE p.field_name='revenue' AND d.source_name='AkShare / Sina financial abstract'""").fetchall()
        rows = db.execute("""SELECT p.data_point_id,p.symbol,p.field_name,p.period_label,
                p.source_id,p.validation_status,p.metadata
            FROM data_points p WHERE p.metadata ? 'secondary_data_point_id'
                OR p.metadata ? 'input_source_ids' OR p.metadata ? 'input_facts'
                OR p.metadata ? 'input_data_point_ids'
                OR p.data_point_id=ANY(%s)""", ([r['data_point_id'] for r in initial],)).fetchall()
        affected = affected_point_ids(rows, [r['data_point_id'] for r in initial])
        selected = [p for p in rows if str(p['data_point_id']) in affected]
        result = {'affected':len(selected),'previously_verified':sum(p['validation_status']=='verified' for p in selected),
                  'apply':args.apply, 'rehearsal':args.rehearse}
        if args.apply or args.rehearse:
            run_id = begin_run(db,'quarantine-revenue-scope')
            for point in selected:
                db.execute("UPDATE data_points SET validation_status='failed', metadata=%s WHERE data_point_id=%s",
                           (json.dumps(quarantine_metadata(point,run_id)),point['data_point_id']))
            symbols = sorted({p['symbol'] for p in selected})
            grouped = {s:[] for s in symbols}
            for point in latest_points(db):
                if point['symbol'] in grouped:
                    grouped[point['symbol']].append(point)
            for symbol, points in grouped.items():
                verdict = evaluate(symbol,points,settings.data_max_age_hours,Decimal(str(settings.price_conflict_tolerance)))
                upsert_valuation(db,as_valuation_row(verdict))
            _refresh_financial_quality(db,symbols)
            end_run(db,run_id,'succeeded',result)
            if args.rehearse:
                db.rollback()
                result['rolled_back'] = True
        else:
            db.rollback()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
