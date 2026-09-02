#!/usr/bin/env bash
set -euo pipefail

source /etc/value-investment-agent/postgres.env
manifest_path="$(find /opt/value-investment-agent/backups -name '*.manifest.json' -printf '%T@ %p\n' | sort -nr | head -n1 | cut -d' ' -f2-)"
if [[ -z "$manifest_path" ]]; then
  echo "No backup manifest available" >&2
  exit 1
fi
test_dir="$(mktemp -d)"
trap 'podman rm -f value-investment-restore-postgres >/dev/null 2>&1 || true; rm -rf "$test_dir"' EXIT

podman rm -f value-investment-restore-postgres >/dev/null 2>&1 || true
podman run -d --name value-investment-restore-postgres \
  --memory=256m --memory-reservation=128m --memory-swap=384m \
  -p 127.0.0.1:5433:5432 \
  -e POSTGRES_DB=value_agent_restore \
  -e POSTGRES_USER=value_agent_admin \
  -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  -v value_investment_restore_postgres:/var/lib/postgresql/data:Z \
  docker.io/library/postgres:16-alpine \
  -c shared_buffers=64MB -c max_connections=10 >/dev/null
until podman exec value-investment-restore-postgres pg_isready -U value_agent_admin -d value_agent_restore >/dev/null; do sleep 1; done
manifest_name="$(basename "$manifest_path")"
dump_name="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["database_dump"])' "$manifest_path")"

printf 'isolated official evidence smoke test\n' > "$test_dir/filing.pdf"
python3 -c 'import json,sys; json.dump({"source_name":"Test Exchange","source_url":"https://example.test/official-filing","evidence_file":"filing.pdf","published_at":"2026-09-01T00:00:00+00:00","validation_status":"verified","human_reviewed":True,"points":[{"symbol":"600519","field_name":"fair_value","period_label":"2026-09-01","value":"1600","unit":"CNY/share"}]},open(sys.argv[1],"w"))' "$test_dir/evidence.json"

DATABASE_URL="postgresql://value_agent_admin:${POSTGRES_PASSWORD}@127.0.0.1:5433/value_agent_restore"
restore_output="$(podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  -e "RESTORE_DATABASE_URL=$DATABASE_URL" \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest sh -c 'pg_restore --clean --if-exists --no-owner --no-acl --dbname "$RESTORE_DATABASE_URL" "/app/backups/$1"' -- "$dump_name" 2>&1)" || restore_status=$?
if [[ "${restore_status:-0}" -ne 0 && "$restore_output" != *'unrecognized configuration parameter "transaction_timeout"'* ]]; then
  printf '%s\n' "$restore_output" >&2
  exit "$restore_status"
fi
import_result="$(podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env -e "DATABASE_URL=$DATABASE_URL" \
  -v "$test_dir":/app/evidence:ro,Z \
  value-investment-agent:latest python -m value_investment_agent import-evidence --manifest /app/evidence/evidence.json)"
printf 'Evidence import result: %s\n' "$import_result"
podman exec value-investment-restore-postgres psql -At -U value_agent_admin -d value_agent_restore \
  -c "SELECT current_database(), count(*) FROM data_points WHERE field_name = 'fair_value' GROUP BY current_database()"
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env -e "DATABASE_URL=$DATABASE_URL" \
  value-investment-agent:latest python -m value_investment_agent update --no-sync-excel >/dev/null
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env -e "DATABASE_URL=$DATABASE_URL" \
  value-investment-agent:latest python -m value_investment_agent init-db >/dev/null
monthly_result="$(podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env -e "DATABASE_URL=$DATABASE_URL" \
  value-investment-agent:latest python -m value_investment_agent snapshot-month --month 2026-09)"
printf 'Monthly snapshot result: %s\n' "$monthly_result"

evidence_count="$(podman exec value-investment-restore-postgres psql -At -U value_agent_admin -d value_agent_restore -c "SELECT count(*) FROM data_points WHERE symbol = '600519' AND field_name = 'fair_value' AND validation_status = 'verified' AND human_reviewed")"
hash_count="$(podman exec value-investment-restore-postgres psql -At -U value_agent_admin -d value_agent_restore -c "SELECT count(*) FROM raw_documents WHERE source_url = 'https://example.test/official-filing' AND sha256 <> ''")"
valuation_state="$(podman exec value-investment-restore-postgres psql -At -U value_agent_admin -d value_agent_restore -c "SELECT data_status FROM valuation_results WHERE symbol = '600519'")"
monthly_count="$(podman exec value-investment-restore-postgres psql -At -U value_agent_admin -d value_agent_restore -c "SELECT count(*) FROM monthly_snapshots WHERE snapshot_month = '2026-09'")"
if [[ "$evidence_count" != "1" || "$hash_count" != "1" || "$monthly_count" != "10" ]]; then
  echo "Evidence smoke test failed: evidence=$evidence_count hashes=$hash_count monthly=$monthly_count" >&2
  exit 1
fi
printf '{"status":"passed","verified_fair_values":%s,"source_hashes":%s,"monthly_snapshots":%s,"valuation_state":"%s"}\n' "$evidence_count" "$hash_count" "$monthly_count" "$valuation_state"
