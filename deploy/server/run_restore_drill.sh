#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /opt/value-investment-agent/backups/<manifest>.manifest.json" >&2
  exit 2
fi

source /etc/value-investment-agent/restore-postgres.env
: "${RESTORE_POSTGRES_PASSWORD:?Dedicated restore database password is required}"
attempt_started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
manifest_name="$(basename "$1")"
# The drill database is disposable. Remove its stopped container so a passed
# or failed drill cannot accumulate stale container metadata between months.
trap 'podman rm -f value-investment-restore-postgres >/dev/null 2>&1 || true' EXIT
podman rm -f value-investment-restore-postgres 2>/dev/null || true
podman run -d --name value-investment-restore-postgres \
  --memory=256m --memory-reservation=128m --memory-swap=384m --cpus=0.5 \
  -p 127.0.0.1:5433:5432 \
  -e POSTGRES_DB=value_agent_restore \
  -e POSTGRES_USER=value_agent_admin \
  -e POSTGRES_PASSWORD="$RESTORE_POSTGRES_PASSWORD" \
  -v value_investment_restore_postgres:/var/lib/postgresql/data:Z \
  docker.io/library/postgres:16-alpine \
  -c shared_buffers=64MB -c max_connections=10
ready=false
for attempt in {1..60}; do
  if podman exec value-investment-restore-postgres pg_isready -U value_agent_admin -d value_agent_restore >/dev/null; then
    ready=true
    break
  fi
  sleep 1
done
if [[ "$ready" != true ]]; then
  echo "Restore database did not become ready within 60 attempts" >&2
  exit 1
fi
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --cpus=0.5 -e PYTHONPATH=/app/src \
  -e M6_RESTORE_ATTEMPT_STARTED_AT="$attempt_started_at" \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  localhost/value-investment-agent:pg16-tools python -m value_investment_agent restore-verify --manifest "/app/backups/$manifest_name"
