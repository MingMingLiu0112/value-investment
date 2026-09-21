#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/value-investment-agent
run_agent() {
  podman run --rm --network host --memory=384m --memory-swap=512m \
    --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src \
    -v "$ROOT/src:/app/src:ro,Z" -v "$ROOT/evidence:/app/evidence:ro,Z" \
    value-investment-agent:latest python -m value_investment_agent "$@"
}
run_agent collect-institution-metrics --limit 1
run_agent auto-verify-filings --limit 500
run_agent refresh-valuations
run_agent export-payload > "$ROOT/exports/.refresh.json"
mv "$ROOT/exports/.refresh.json" "$ROOT/exports/latest.json"
sha256sum "$ROOT/exports/latest.json"
