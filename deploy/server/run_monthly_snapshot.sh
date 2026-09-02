#!/usr/bin/env bash
set -euo pipefail

# At the start of a month, freeze the preceding month's final collected values.
snapshot_month="$(date -d 'last month' +%Y-%m)"
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  value-investment-agent:latest python -m value_investment_agent snapshot-month --month "$snapshot_month"
