#!/usr/bin/env bash
set -euo pipefail

# Use a proxy only when the server configuration explicitly provides one. This
# keeps PostgreSQL local and confines any proxy use to public data collection.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"
if [[ -n "${COLLECTOR_PROXY_URL:-}" ]]; then
  export HTTP_PROXY="$COLLECTOR_PROXY_URL"
  export HTTPS_PROXY="$COLLECTOR_PROXY_URL"
fi

podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent init-db
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent update --prices --financials --no-sync-excel
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  -e PYTHONPATH=/app/src \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent quality
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  -e PYTHONPATH=/app/src \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent backup
