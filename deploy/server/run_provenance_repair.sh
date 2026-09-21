#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
for batch in 1 2 3 4 5 6; do
  printf 'Repair batch %s\n' "$batch"
  podman run --rm --network host --memory=256m --memory-swap=384m --cpus=0.5 \
    --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src:/audit \
    -v "$root/src:/app/src:ro,Z" -v "$root/evidence:/app/evidence:ro,Z" \
    -v "$root/exports/market-deploy:/audit:ro,Z" \
    value-investment-agent:latest python /audit/rehearse_provenance_repair.py --apply --limit 500
done
podman run --rm --network host --memory=256m --memory-swap=384m --cpus=0.5 \
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src:/audit \
  -v "$root/src:/app/src:ro,Z" -v "$root/evidence:/app/evidence:ro,Z" \
  -v "$root/exports/market-deploy:/audit:ro,Z" \
  value-investment-agent:latest python /audit/audit_filing_provenance.py \
  > "$root/exports/provenance-audit-after.json"
