#!/usr/bin/env bash
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"

mode="${1:-daily}"
# Avoid concurrent market snapshots and initializer lock queues.
exec 9>/opt/value-investment-agent/exports/market-screen.lock
flock -w 30 9 || {
  printf '%s\n' 'SKIPPED_LOCK_BUSY: full market screening did not run' >&2
  exit 75
}
args=(--without-industry)
if [[ "$mode" == "weekly" ]]; then
  args=()
fi

# The host does not provide working DNS to short-lived collection containers.
# Keep the workaround local to this process; do not alter global DNS settings.
EASTMONEY_82_PUSH2_IP="${EASTMONEY_82_PUSH2_IP:-117.184.33.102}"
EASTMONEY_PUSH2_IP="${EASTMONEY_PUSH2_IP:-61.129.129.196}"
TENCENT_FINANCE_IP="${TENCENT_FINANCE_IP:-117.62.241.183}"
SINA_FINANCE_IP="${SINA_FINANCE_IP:-116.133.8.236}"
EASTMONEY_17_PUSH2_IP="${EASTMONEY_17_PUSH2_IP:-43.144.251.121}"
EASTMONEY_29_PUSH2_IP="${EASTMONEY_29_PUSH2_IP:-101.226.30.206}"

# An unavailable official endpoint must not stop quote collection. Exports will
# mark different-day or missing official evidence as unreconciled.
podman run --rm --network host --dns=223.5.5.5 --memory=256m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  value-investment-agent:latest python -m value_investment_agent refresh-security-universe \
  || printf '%s\n' 'Official list refresh failed; retain the failure audit and continue quotes.' >&2

# Schema initialization belongs to deployment, not daily collection: DDL can
# wait behind an in-flight filing transaction and block the whole update.
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e PYTHONPATH=/app/src \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= -e NO_PROXY='*' \
  --env-file /etc/value-investment-agent/agent.env \
  --add-host="82.push2.eastmoney.com:${EASTMONEY_82_PUSH2_IP}" \
  --add-host="push2.eastmoney.com:${EASTMONEY_PUSH2_IP}" \
  --add-host="17.push2.eastmoney.com:${EASTMONEY_17_PUSH2_IP}" \
  --add-host="29.push2.eastmoney.com:${EASTMONEY_29_PUSH2_IP}" \
  --add-host="proxy.finance.qq.com:${TENCENT_FINANCE_IP}" \
  --add-host="vip.stock.finance.sina.com.cn:${SINA_FINANCE_IP}" \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  -v /opt/value-investment-agent/evidence:/app/evidence:Z \
  value-investment-agent:latest python -m value_investment_agent screen-market "${args[@]}"

# Re-evaluate every current candidate against the newly cross-checked closing
# price. This only reads the local database and does not place an order.
podman run --rm --network host --memory=256m --memory-reservation=128m --memory-swap=384m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent refresh-valuations

# Publish the coherent post-screening state for the Excel synchronizer.
mkdir -p /opt/value-investment-agent/exports
podman run --rm --network host --memory=384m --memory-reservation=128m --memory-swap=512m \
  --env-file /etc/value-investment-agent/agent.env \
  -e PYTHONPATH=/app/src \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  value-investment-agent:latest python -m value_investment_agent export-payload \
  > /opt/value-investment-agent/exports/.latest.json
mv /opt/value-investment-agent/exports/.latest.json /opt/value-investment-agent/exports/latest.json
