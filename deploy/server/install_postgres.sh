#!/usr/bin/env bash
set -euo pipefail

# This proxy is reachable only from the host and is used for image and package
# downloads. PostgreSQL still binds exclusively to 127.0.0.1.
export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7890}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7890}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

APP_DIR=/opt/value-investment-agent
CONFIG_DIR=/etc/value-investment-agent
DATA_VOLUME=value_investment_postgres
RESTORE_VOLUME=value_investment_restore_postgres
PRIMARY_CONTAINER=value-investment-postgres
RESTORE_CONTAINER=value-investment-restore-postgres

bash "$(dirname "$0")/preflight_resources.sh"

install -d -m 700 "$CONFIG_DIR" "$APP_DIR/backups"

if [[ ! -f "$CONFIG_DIR/postgres.env" ]]; then
  admin_password="$(openssl rand -hex 24)"
  writer_password="$(openssl rand -hex 24)"
  reader_password="$(openssl rand -hex 24)"
  cat > "$CONFIG_DIR/postgres.env" <<EOF
POSTGRES_DB=value_agent
POSTGRES_USER=value_agent_admin
POSTGRES_PASSWORD=$admin_password
EOF
  chmod 600 "$CONFIG_DIR/postgres.env"
  cat > "$CONFIG_DIR/agent.env" <<EOF
DATABASE_URL=postgresql://value_agent_writer:$writer_password@127.0.0.1:5432/value_agent
RESTORE_DATABASE_URL=postgresql://value_agent_admin:$admin_password@127.0.0.1:5433/value_agent_restore
BACKUP_DIRECTORY=/app/backups
OUTPUT_DIRECTORY=$APP_DIR/runtime
DATA_MAX_AGE_HOURS=30
PRICE_CONFLICT_TOLERANCE=0.03
CONTAINER_RUNTIME=podman
POSTGRES_CONTAINER_NAME=$PRIMARY_CONTAINER
RESTORE_CONTAINER_NAME=$RESTORE_CONTAINER
EOF
  chmod 600 "$CONFIG_DIR/agent.env"
  cat > "$CONFIG_DIR/reader-credentials.txt" <<EOF
DATABASE_URL=postgresql://value_agent_reader:$reader_password@YOUR_SERVER.tailnet.ts.net:5432/value_agent
EOF
  chmod 600 "$CONFIG_DIR/reader-credentials.txt"
fi

set -a
source "$CONFIG_DIR/postgres.env"
set +a

podman volume exists "$DATA_VOLUME" || podman volume create "$DATA_VOLUME"
podman volume exists "$RESTORE_VOLUME" || podman volume create "$RESTORE_VOLUME"
podman rm -f "$PRIMARY_CONTAINER" 2>/dev/null || true
podman rm -f "$RESTORE_CONTAINER" 2>/dev/null || true
podman run -d --name "$PRIMARY_CONTAINER" --restart=always \
  --memory=256m --memory-reservation=128m --memory-swap=384m \
  -p 127.0.0.1:5432:5432 \
  --env-file "$CONFIG_DIR/postgres.env" \
  -v "$DATA_VOLUME":/var/lib/postgresql/data:Z \
  docker.io/library/postgres:16-alpine \
  -c shared_buffers=64MB -c effective_cache_size=128MB -c work_mem=2MB \
  -c maintenance_work_mem=32MB -c max_connections=15

until podman exec "$PRIMARY_CONTAINER" pg_isready -U value_agent_admin -d value_agent >/dev/null; do sleep 1; done

podman build --network host --http-proxy -t value-investment-agent:latest -f "$APP_DIR/deploy/server/Containerfile" "$APP_DIR"

writer_password="$(sed -n 's#^DATABASE_URL=postgresql://value_agent_writer:\([^@]*\)@.*#\1#p' "$CONFIG_DIR/agent.env")"
reader_password="$(sed -n 's#^DATABASE_URL=postgresql://value_agent_reader:\([^@]*\)@.*#\1#p' "$CONFIG_DIR/reader-credentials.txt")"
podman exec -i "$PRIMARY_CONTAINER" psql -v ON_ERROR_STOP=1 -v writer_password="$writer_password" -v reader_password="$reader_password" -U value_agent_admin -d value_agent <<'SQL'
SELECT format('CREATE ROLE value_agent_writer LOGIN PASSWORD %L', :'writer_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'value_agent_writer')
\gexec
SELECT format('ALTER ROLE value_agent_writer PASSWORD %L', :'writer_password')
\gexec
SELECT format('CREATE ROLE value_agent_reader LOGIN PASSWORD %L', :'reader_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'value_agent_reader')
\gexec
SELECT format('ALTER ROLE value_agent_reader PASSWORD %L', :'reader_password')
\gexec
GRANT CONNECT ON DATABASE value_agent TO value_agent_writer, value_agent_reader;
GRANT USAGE ON SCHEMA public TO value_agent_writer, value_agent_reader;
GRANT CREATE ON SCHEMA public TO value_agent_writer;
SQL

echo "PostgreSQL is running only on 127.0.0.1. The restore container is created only during a recovery drill. Configure Tailscale Serve before distributing reader credentials."
