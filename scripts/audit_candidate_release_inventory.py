"""Read-only production inventory for the reviewed parser release cohort."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess


def inventory():
    from value_investment_agent.db import connect
    from value_investment_agent.settings import get_settings
    symbols = ['000027', '000049', '000065', '000088', '000301', '000411',
               '000422', '000429', '000550', '000551', '000568', '000630',
               '000680', '000682', '000700', '000703', '000708', '000729',
               '000733', '000786']
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        db.execute("SET LOCAL statement_timeout='20s'")
        reports = db.execute('''SELECT disclosure_id, symbol, report_period, sha256,
            source_url, local_path, extraction_parser_version, extraction_status
            FROM official_disclosures
            WHERE (symbol=ANY(%s) AND report_period='2026-06-30')
               OR (symbol=ANY(%s) AND report_period BETWEEN '2014-12-31' AND '2024-12-31'
                   AND report_kind='annual') ORDER BY symbol, report_period''',
            (symbols, ['600519', '000333', '601088'])).fetchall()
        ids = [row['disclosure_id'] for row in reports]
        candidates = db.execute('''SELECT c.* FROM filing_candidates c
            WHERE c.disclosure_id=ANY(%s) ORDER BY disclosure_id, field_name, page_number''',
            (ids,)).fetchall()
        facts = db.execute('''SELECT p.data_point_id, p.source_id, p.symbol, p.field_name,
            p.period_label, p.value, p.unit, p.validation_status, p.metadata
            FROM data_points p WHERE p.metadata->>'candidate_id' IN (
                SELECT candidate_id::text FROM filing_candidates WHERE disclosure_id=ANY(%s))''',
            (ids,)).fetchall()
        dependencies = db.execute('''SELECT data_point_id, source_id, symbol, field_name,
            period_label, validation_status, metadata FROM data_points
            WHERE metadata ?| ARRAY['secondary_data_point_id', 'input_source_ids',
                                     'input_facts', 'input_data_point_ids']''').fetchall()
    return dict(captured_at=datetime.now(timezone.utc).isoformat(), reports=reports,
                candidates=candidates, facts=facts, dependency_points=dependencies,
                production_updated=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    if not args.capture:
        print(json.dumps(inventory(), default=str, ensure_ascii=False))
        return
    command = ['ssh', '-i', str(Path.home() / '.ssh/id_ed25519_value_investment'),
               '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'root@47.100.97.88',
               'podman run --rm -i --network host --cpus=0.5 --memory=192m --memory-swap=256m '
               '-e PYTHONPATH=/app/src --env-file /etc/value-investment-agent/agent.env '
               '-v /opt/value-investment-agent/src:/app/src:ro '
               'value-investment-agent:latest python -']
    completed = subprocess.run(command, input=Path(__file__).read_bytes(),
                               capture_output=True, timeout=90, check=True)
    packet = json.loads(completed.stdout)
    target = Path('runtime') / ('candidate-release-inventory-' +
             datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(packet, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'report': str(target), 'disclosures': len(packet['reports']),
                      'candidates': len(packet['candidates']), 'fact_references': len(packet['facts'])}))


if __name__ == '__main__':
    main()
