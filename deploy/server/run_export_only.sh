#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
exec 9>"$root/exports/market-screen.lock"
flock -n 9 || exit 1
temporary=$(mktemp "$root/exports/.recovery-export-XXXXXXXX.json")
trap 'rm -f "$temporary"' EXIT
podman --cgroup-manager=cgroupfs run --rm --network host --cpus=0.5 \
  --memory=384m --memory-swap=512m \
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src \
  -v "$root/src:/app/src:ro,Z" --entrypoint python \
  value-investment-agent:latest -m value_investment_agent export-payload > "$temporary"
test -s "$temporary"
mv "$temporary" "$root/exports/latest.json"
sha256sum "$root/exports/latest.json"
