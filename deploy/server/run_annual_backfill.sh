#!/usr/bin/env bash
set -euo pipefail

ROOT=/opt/value-investment-agent
LIMIT=${1:-20}
if [[ ! "$LIMIT" =~ ^([1-9]|1[0-9]|20)$ ]] || (( $# > 1 )); then
  echo 'Usage: run_annual_backfill.sh [1-20]' >&2
  exit 2
fi
test -d "$ROOT/evidence"
test -f "$ROOT/exports/market-deploy/run_annual_batch.py"

# Preserve headroom for PostgreSQL, PTA and evidence already on disk.
AVAILABLE_KB=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
DISK_KB=$(df -Pk "$ROOT" | awk 'END {print $4}')
if [[ ! "$AVAILABLE_KB" =~ ^[0-9]+$ || ! "$DISK_KB" =~ ^[0-9]+$ ]]; then
  echo '{"status":"resource_check_failed"}' >&2
  exit 1
fi
if (( AVAILABLE_KB < 1048576 || DISK_KB < 2097152 )); then
  printf '{"status":"resource_deferred","available_memory_kb":%s,"available_disk_kb":%s}\n' "$AVAILABLE_KB" "$DISK_KB"
  exit 1
fi
FILINGS_STATE=$(systemctl show value-investment-agent-filings.service --property=ActiveState --value)
if [[ "$FILINGS_STATE" != inactive && "$FILINGS_STATE" != failed ]]; then
  echo '{"status":"filings_running_deferred"}'
  exit 1
fi

# The Python runner holds a host-shared lock across the entire batch.
exec podman --cgroup-manager=cgroupfs run --rm --network host --dns=223.5.5.5 \
  --memory=512m --memory-swap=640m --cpus=0.5 \
  --env-file /etc/value-investment-agent/agent.env \
  -e EVIDENCE_DIRECTORY=/app/evidence -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -v "$ROOT/src:/app/src:ro,Z" \
  -v "$ROOT/evidence:/app/evidence:Z" \
  -v "$ROOT/exports/market-deploy:/audit:Z" \
  value-investment-agent:latest python /audit/run_annual_batch.py --limit "$LIMIT"
