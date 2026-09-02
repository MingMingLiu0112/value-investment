#!/usr/bin/env bash
set -euo pipefail

# Market data is fetched directly. A stale host proxy must not break the scheduled update.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"

podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent init-db
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent update --prices --financials --no-sync-excel
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent quality
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent backup
