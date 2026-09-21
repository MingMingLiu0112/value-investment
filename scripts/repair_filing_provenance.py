"""Bounded transaction; dry-run by default. Keep old document rows for audit."""
import argparse
import json

from value_investment_agent.db import connect, begin_run, end_run
from value_investment_agent.provenance_repair import repair_batch
from value_investment_agent.settings import get_settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--limit', type=int, default=500)
    args = parser.parse_args()
    with connect(get_settings().database_url) as connection:
        connection.execute("SET lock_timeout = '5s'")
        connection.execute("SET statement_timeout = '60s'")
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('provenance-repair-v1'))")
        run_id = begin_run(connection, 'repair-filing-provenance') if args.apply else None
        result = repair_batch(connection, args.limit, args.apply)
        if run_id:
            end_run(connection, run_id, 'succeeded', result)
        else:
            connection.rollback()
    print(json.dumps(result))


if __name__ == '__main__':
    main()
