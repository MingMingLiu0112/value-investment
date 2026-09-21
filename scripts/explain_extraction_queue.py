"""Plan the actual staged queue SQL without claiming or changing disclosures."""
import argparse
import importlib.util
import json

from value_investment_agent.db import connect
from value_investment_agent.settings import get_settings


class Capture:
    def execute(self, sql, params):
        self.sql, self.params = sql, params
        return self

    def fetchall(self):
        return []

    def commit(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('module_path')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('value_investment_agent.queue_plan_target', args.module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    capture = Capture()
    module.claim_disclosures_for_extraction(capture, 20)
    with connect(get_settings().database_url) as db:
        db.execute('SET TRANSACTION READ ONLY')
        db.execute("SET statement_timeout='15s'")
        result = db.execute('EXPLAIN (FORMAT JSON) ' + capture.sql, capture.params).fetchone()
        plan = next(iter(result.values()))[0]['Plan']
    nodes = []

    def visit(node):
        nodes.append({key: node[key] for key in ('Node Type', 'Relation Name', 'Plan Rows', 'Total Cost') if key in node})
        for child in node.get('Plans', []):
            visit(child)

    visit(plan)
    print(json.dumps({'read_only': True, 'executed': False, 'nodes': nodes}))


if __name__ == '__main__':
    main()
