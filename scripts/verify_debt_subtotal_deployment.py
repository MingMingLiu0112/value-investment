"""Read-only smoke check of deployed derivations against current annual facts."""
import json
from collections import Counter

from value_investment_agent.db import connect, current_market_candidate_symbols, latest_points
from value_investment_agent.derived_financials import DERIVATION_VERSION, build_verified_derivations
from value_investment_agent.settings import get_settings


with connect(get_settings().database_url) as connection:
    connection.execute('SET TRANSACTION READ ONLY')
    symbols = current_market_candidate_symbols(connection)
    points = latest_points(connection, annual_only=True)
records = build_verified_derivations(points, symbols)
assert not any(row.field_name == 'interest_bearing_debt' for row in records)
print(json.dumps({'parser_version': DERIVATION_VERSION, 'companies': len(symbols),
                  'would_create': dict(Counter(row.field_name for row in records)),
                  'database_modified': False}))
