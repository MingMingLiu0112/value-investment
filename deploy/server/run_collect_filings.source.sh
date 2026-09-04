#!/usr/bin/env bash
set -euo pipefail

# CNINFO is a first-party statutory disclosure source. Direct server DNS is not
# available on this host and the general proxy may reject CNINFO. These mappings
# and proxy overrides apply only to the short-lived filing collector container.
CNINFO_WEB_IP="${CNINFO_WEB_IP:-171.109.111.148}"
CNINFO_STATIC_IP="${CNINFO_STATIC_IP:-124.225.115.71}"

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

# Keep official-PDF collection bounded. Ten candidates per trading day keep the
# container below its memory limit while clearing the review queue in one quarter.
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
  value-investment-agent:latest python -m value_investment_agent enrich-financials --limit 10

# Extract page-level candidates. They remain outside verified facts until the
# automatic cross-source validator confirms page, period, unit and value.
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/evidence:/app/evidence:ro,Z \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent extract-filing-candidates-batch --limit 10

# Promote only filings that agree with an independently collected structured
# source on field, report period, unit and value tolerance. No manual action is
# needed, and unmatched candidates remain blocked for the next scheduled retry.
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --add-host="money.finance.sina.com.cn:116.133.8.236" \
  --add-host="vip.stock.finance.sina.com.cn:116.133.8.236" \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= \
  -e NO_PROXY='*' -e no_proxy='*' \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent collect-secondary-financials --limit 25

podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent auto-verify-filings --limit 200
