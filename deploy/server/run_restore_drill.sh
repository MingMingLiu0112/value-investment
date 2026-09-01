#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /opt/value-investment-agent/backups/<manifest>.manifest.json" >&2
  exit 2
fi

source /etc/value-investment-agent/postgres.env
podman rm -f value-investment-restore-postgres 2>/dev/null || true
podman run -d --name value-investment-restore-postgres \
  --memory=256m --memory-reservation=128m --memory-swap=384m \
  -p 127.0.0.1:5433:5432 \
  -e POSTGRES_DB=value_agent_restore \
  -e POSTGRES_USER=value_agent_admin \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -v value_investment_restore_postgres:/var/lib/postgresql/data:Z \
  docker.io/library/postgres:16-alpine \
  -c shared_buffers=64MB -c max_connections=10
until podman exec value-investment-restore-postgres pg_isready -U value_agent_admin -d value_agent_restore >/dev/null; do sleep 1; done
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent restore-verify --manifest "$1"
podman stop value-investment-restore-postgres
