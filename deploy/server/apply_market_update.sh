#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
stage="$root/exports/market-deploy"
bash -n "$stage/run_market_screen.sh"
for file in market.py db.py cli.py financial_quality.py derived_financials.py official_universe.py; do
  mv "$stage/$file" "$root/src/value_investment_agent/$file"
done
chmod 755 "$stage/run_market_screen.sh"
mv "$stage/run_market_screen.sh" "$root/deploy/server/run_market_screen.sh"
