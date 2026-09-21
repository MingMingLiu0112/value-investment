"""Read-only coverage diagnostics, without dumping database credentials."""
import json
from collections import Counter

from value_investment_agent.settings import get_settings
from value_investment_agent.db import connect, current_market_candidate_symbols, latest_points
from value_investment_agent.financial_quality import GENERAL_FIELDS


def main():
    with connect(get_settings().database_url) as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        connection.execute("SET statement_timeout = '45s'")
        candidates = set(current_market_candidate_symbols(connection))
        points = [p for p in latest_points(connection, annual_only=True) if p['symbol'] in candidates]
        accepted = [p for p in points if p['validation_status'] == 'verified'
                    and (p.get('metadata') or {}).get('automatic_cross_source_verification')
                    and not (p.get('metadata') or {}).get('evidence_quarantine')]
        closest = connection.execute("""SELECT q.symbol,i.name,q.coverage_ratio,q.calculation_details
            FROM financial_quality_results q JOIN instruments i ON i.symbol=q.symbol
            WHERE q.symbol=ANY(%s) AND q.model_type='general_enterprise'
            ORDER BY q.coverage_ratio DESC,q.symbol LIMIT 10""",(list(candidates),)).fetchall()
        for row in closest:
            details = row.pop('calculation_details') or {}
            row['accepted_fields'] = details.get('accepted_fields',sorted((details.get('values') or {}).keys()))
            row['missing_fields'] = [f for f in GENERAL_FIELDS if f not in row['accepted_fields']]
        quality = connection.execute(
            'SELECT quality_status, count(*) AS count FROM financial_quality_results '
            'WHERE symbol = ANY(%s) GROUP BY quality_status', (list(candidates),)
        ).fetchall()
        specialized = connection.execute(
            'SELECT parser_version, count(*) AS reports, sum(candidate_count) AS facts '
            'FROM institution_extractions GROUP BY parser_version'
        ).fetchall()
        print(json.dumps({'candidates':len(candidates), 'annual_points':len(points),
            'annual_verified_points':len(accepted),
            'annual_general_verified':dict(Counter(p['field_name'] for p in accepted if p['field_name'] in GENERAL_FIELDS)),
            'quality':quality, 'closest_to_complete':closest,
            'institution_extractions':specialized}, ensure_ascii=False, default=str))


if __name__ == '__main__':
    main()
