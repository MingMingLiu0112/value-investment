"""Rehearse promotion read-only and count latest-source conflicts."""
import json
from collections import Counter

from value_investment_agent import candidate_review
from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


counts = Counter()
samples = []
original = candidate_review.latest_consistent_secondary


def inspect(matches, value, unit):
    result = original(matches, value, unit)
    counts['secondary_checks'] += 1
    if result is None:
        counts['latest_source_conflicts'] += 1
        if len(samples) < 10:
            latest = {}
            for row in matches:
                latest.setdefault(row['source_name'], row)
            samples.append({'official_value': str(value), 'unit': unit,
                            'latest_sources': list(latest.values())})
    return result


candidate_review.latest_consistent_secondary = inspect


class ObservedConnection:
    def __init__(self, db):
        self.db = db

    def execute(self, sql, params):
        result = self.db.execute(sql, params)
        if 'FROM filing_candidates c JOIN' not in sql:
            return result
        rows = result.fetchall()
        counts['selected_candidates'] = len(rows)
        for row in rows:
            counts['selected_' + row['field_name']] += 1
            if row['field_name'] in ('revenue_yoy', 'net_income_yoy') and not (
                candidate_review.official_growth_period_matches(row.get('excerpt'), row['report_period'])
            ):
                counts['invalid_growth_header'] += 1

        class Result:
            def fetchall(self):
                return rows

        return Result()


with connect(get_settings().database_url) as db:
    db.execute('SET TRANSACTION READ ONLY')
    for candidate_id, record in candidate_review.automatically_verified_candidates(ObservedConnection(db), 300):
        counts['eligible_promotions'] += 1
    print(json.dumps({'counts': counts, 'conflict_samples': samples}, default=str))
