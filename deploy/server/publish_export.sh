#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
temporary=$(mktemp "$root/exports/.export-XXXXXXXX.json")
trap 'rm -f "$temporary"' EXIT
podman run --rm --network host --memory=384m --memory-swap=512m \
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src \
  -v "$root/src:/app/src:ro,Z" \
  value-investment-agent:latest python -m value_investment_agent export-payload > "$temporary"
mv "$temporary" "$root/exports/latest.json"
sha256sum "$root/exports/latest.json"
