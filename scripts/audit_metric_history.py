"""Read-only recent evidence history for one symbol and metric."""
import argparse
import json
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('symbol')
    parser.add_argument('field')
    args = parser.parse_args()
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION READ ONLY')
        db.execute("SET statement_timeout='30s'")
        rows = db.execute("""SELECT p.data_point_id,p.symbol,p.field_name,p.period_label,
            p.value,p.unit,p.validation_status,p.metadata,p.created_at,
            d.source_url,d.sha256,d.parser_version
            FROM data_points p JOIN raw_documents d ON p.source_id=d.document_id
            WHERE p.symbol=%s AND p.field_name=%s ORDER BY p.created_at DESC LIMIT 20""",
            (args.symbol,args.field)).fetchall()
        print(json.dumps(rows,ensure_ascii=False,default=str))


if __name__ == '__main__':
    main()
