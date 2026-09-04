#!/usr/bin/env bash
set -euo pipefail

unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
export NO_PROXY="127.0.0.1,localhost"
if [[ -z "${COLLECTOR_PROXY_URL:-}" && -r /etc/value-investment-agent/agent.env ]]; then
  COLLECTOR_PROXY_URL="$(sed -n 's/^COLLECTOR_PROXY_URL=//p' /etc/value-investment-agent/agent.env | head -n1)"
fi
if [[ -n "${COLLECTOR_PROXY_URL:-}" ]]; then
  export HTTP_PROXY="$COLLECTOR_PROXY_URL"
  export HTTPS_PROXY="$COLLECTOR_PROXY_URL"
fi

mode="${1:-daily}"
args=(--without-industry)
if [[ "$mode" == "weekly" ]]; then
  args=()
fi

# The host does not provide working DNS to short-lived collection containers.
# Keep the workaround local to this process; do not alter global DNS settings.
EASTMONEY_82_PUSH2_IP="${EASTMONEY_82_PUSH2_IP:-117.184.33.102}"
EASTMONEY_PUSH2_IP="${EASTMONEY_PUSH2_IP:-61.129.129.196}"
TENCENT_FINANCE_IP="${TENCENT_FINANCE_IP:-183.47.125.78}"

podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  --add-host="82.push2.eastmoney.com:${EASTMONEY_82_PUSH2_IP}" \
  --add-host="push2.eastmoney.com:${EASTMONEY_PUSH2_IP}" \
  --add-host="proxy.finance.qq.com:${TENCENT_FINANCE_IP}" \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  value-investment-agent:latest python -m value_investment_agent init-db
podman run --rm --network host --memory=512m --memory-reservation=192m --memory-swap=768m \
  -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY \
  --env-file /etc/value-investment-agent/agent.env \
  --add-host="82.push2.eastmoney.com:${EASTMONEY_82_PUSH2_IP}" \
  --add-host="push2.eastmoney.com:${EASTMONEY_PUSH2_IP}" \
  --add-host="proxy.finance.qq.com:${TENCENT_FINANCE_IP}" \
  -v /opt/value-investment-agent/src:/app/src:ro,Z \
  -v /opt/value-investment-agent/sql:/app/sql:ro,Z \
  value-investment-agent:latest python -m value_investment_agent screen-market "${args[@]}"
