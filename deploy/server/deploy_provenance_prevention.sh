#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
stage="$root/exports/market-deploy"
source="$root/src/value_investment_agent"
test "$(sha256sum "$source/cli.py" | cut -d ' ' -f 1)" = 0a4b0efd1618613cca8b126f097d275da5886759ef5f10993cda0bd9d7380ad5
test "$(sha256sum "$source/candidate_review.py" | cut -d ' ' -f 1)" = f0d2c6d32a8814f24518990cb29ca1810e510315ba9049e1bd86496ef14ab927
backup=$(mktemp -d "$root/exports/provenance-code-backup-XXXXXXXX")
cp "$source/cli.py" "$source/candidate_review.py" "$backup/"
# New CLI accepts both the old list and new iterator, so deploy it first.
cp "$stage/cli.py" "$source/.cli-provenance.tmp"
mv "$source/.cli-provenance.tmp" "$source/cli.py"
cp "$stage/candidate_review.py" "$source/.candidate-provenance.tmp"
mv "$source/.candidate-provenance.tmp" "$source/candidate_review.py"
printf 'Code backup: %s\n' "$backup"
podman run --rm --network host --memory=256m --memory-swap=384m --cpus=0.5 \
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src \
  -v "$root/src:/app/src:ro,Z" -v "$root/evidence:/app/evidence:ro,Z" \
  value-investment-agent:latest python -m value_investment_agent auto-verify-filings --limit 1
bash "$stage/publish_export.sh"
