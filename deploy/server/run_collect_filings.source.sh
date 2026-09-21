#!/usr/bin/env bash
set -euo pipefail

# CNINFO is a first-party statutory disclosure source. Direct server DNS is not
# available on this host and the general proxy may reject CNINFO. These mappings
# and proxy overrides apply only to the short-lived filing collector container.
CNINFO_WEB_IP="${CNINFO_WEB_IP:-171.109.111.148}"
CNINFO_STATIC_IP="${CNINFO_STATIC_IP:-124.225.115.71}"

# Keep at least 2 GiB available for PostgreSQL/WAL and the co-hosted application.
AVAILABLE_KB=$(df -Pk /opt/value-investment-agent | awk 'NR==2 {print $4}')
ALLOW_DOWNLOADS=1
if (( AVAILABLE_KB < 2097152 )); then
  ALLOW_DOWNLOADS=0
  echo "Low disk: ${AVAILABLE_KB} KiB available; skip new PDFs, process archived evidence only." >&2
fi

podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  --add-host="www.cninfo.com.cn:${CNINFO_WEB_IP}" \
  --add-host="static.cninfo.com.cn:${CNINFO_STATIC_IP}" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -v /opt/value-investment-agent/backups:/app/backups:Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  value-investment-agent:latest python -m value_investment_agent init-db

if (( ALLOW_DOWNLOADS )); then
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  --add-host="www.cninfo.com.cn:${CNINFO_WEB_IP}" \
  --add-host="static.cninfo.com.cn:${CNINFO_STATIC_IP}" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent collect-filings

# Process a deliberately bounded batch. The filings timer runs twice per business
# hour, so 40 issuers per run clears the all-A queue materially faster without
# raising the short-lived container's 512 MiB memory limit or competing with
# the PTA app. Issuers are still handled sequentially inside this container.
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  --add-host="www.cninfo.com.cn:${CNINFO_WEB_IP}" \
  --add-host="static.cninfo.com.cn:${CNINFO_STATIC_IP}" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent enrich-financials --limit 40
fi

# Extract page-level candidates. They remain outside verified facts until the
# automatic cross-source validator confirms page, period, unit and value.
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent extract-filing-candidates-batch --limit 40

# Promote only filings that agree with an independently collected structured
# source on field, report period, unit and value tolerance. This is local
# PostgreSQL evidence matching, so processing 300 rows improves backlog drain
# without increasing the network/PDF containers' memory ceilings.
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --add-host="money.finance.sina.com.cn:116.133.8.236" \
  --add-host="vip.stock.finance.sina.com.cn:116.133.8.236" \
  --add-host="quotes.sina.cn:116.133.8.236" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent collect-secondary-financials --limit 120

# Retain consecutive-year inputs before promotion. The collector keeps facts
# pending, isolates issuer failures, and suppresses repeat attempts for six hours.
podman run --rm --network host --memory=256m --memory-swap=384m --cpus=0.5 \
  --add-host="money.finance.sina.com.cn:116.133.8.236" \
  --add-host="vip.stock.finance.sina.com.cn:116.133.8.236" \
  --add-host="quotes.sina.cn:116.133.8.236" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src -e EVIDENCE_DIRECTORY=/app/evidence \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  value-investment-agent:latest python -m value_investment_agent collect-growth-evidence --limit 5

podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent auto-verify-filings --limit 300

# Recalculate the entire current screen after official facts are promoted. This
# is local PostgreSQL work only; it never calls a market source or executes a trade.
podman run --rm --network host --memory=512m --memory-swap=768m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  value-investment-agent:latest python -m value_investment_agent collect-institution-metrics --limit 10

podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent refresh-valuations

# Publish one complete payload atomically for the local Excel synchronizer.
mkdir -p /opt/value-investment-agent/exports
podman run --rm --network host --memory=384m --memory-reservation=128m --memory-swap=512m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent export-payload \
  > /opt/value-investment-agent/exports/.latest.json
mv /opt/value-investment-agent/exports/.latest.json /opt/value-investment-agent/exports/latest.json
