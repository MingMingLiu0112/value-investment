#!/usr/bin/env bash
set -euo pipefail
root=/opt/value-investment-agent
stage="$root/exports/market-deploy"
podman build --network host --dns=223.5.5.5 --memory=512m --memory-swap=768m \
  --cpu-period=100000 --cpu-quota=100000 \
  -f "$stage/Containerfile.pdf-text" -t localhost/value-investment-agent:pdfium "$stage"
podman run --rm --memory=128m localhost/value-investment-agent:pdfium \
  python -c 'import pypdfium2; print("PDFium import verified")'
podman tag localhost/value-investment-agent:latest localhost/value-investment-agent:before-pdfium
podman tag localhost/value-investment-agent:pdfium localhost/value-investment-agent:latest
for file in pdf_text.py disclosures.py institution_metrics.py; do
  mv "$stage/$file" "$root/src/value_investment_agent/$file"
done
