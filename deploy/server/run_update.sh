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

run_data_stages() {
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent init-db || return $?
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent update --prices --financials --no-sync-excel || return $?
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  -e PYTHONPATH=/app/src \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent quality || return $?
}

# A market-data failure must not suppress the database backup attempt.
data_status=0
backup_status=0
run_data_stages || data_status=$?
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  -e PYTHONPATH=/app/src -e EVIDENCE_DIRECTORY=/app/evidence \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  localhost/value-investment-agent:pg16-tools python -m value_investment_agent backup || backup_status=$?
printf 'daily_update data_exit=%s backup_exit=%s\n' "$data_status" "$backup_status"
if [[ "$backup_status" != 0 ]]; then exit "$backup_status"; fi
exit "$data_status"
