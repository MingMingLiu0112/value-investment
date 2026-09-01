#!/usr/bin/env bash
set -euo pipefail

export HTTP_PROXY="${HTTP_PROXY:-http://127.0.0.1:7890}"
export HTTPS_PROXY="${HTTPS_PROXY:-http://127.0.0.1:7890}"
export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"

podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  value-investment-agent:latest python -m value_investment_agent init-db
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
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
