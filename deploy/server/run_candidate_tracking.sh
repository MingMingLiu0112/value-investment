#!/usr/bin/env bash
set -euo pipefail
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
root=/opt/value-investment-agent
exec 9>"$root/exports/market-screen.lock"
flock -w 30 9 || {
  printf '%s\n' 'SKIPPED_LOCK_BUSY: candidate tracking did not run' >&2
  exit 75
}
runtime=(podman --cgroup-manager=cgroupfs run --rm --network host --cpus=0.5
  --env-file /etc/value-investment-agent/agent.env -e PYTHONPATH=/app/src
  -v "$root/src:/app/src:ro,Z")
status=0
"${runtime[@]}" --memory=512m --memory-swap=768m \
  -e EVIDENCE_DIRECTORY=/app/evidence \
  -e HTTP_PROXY= -e HTTPS_PROXY= -e ALL_PROXY= \
  -e http_proxy= -e https_proxy= -e all_proxy= -e NO_PROXY='*' \
  --add-host="82.push2.eastmoney.com:${EASTMONEY_82_PUSH2_IP:-117.184.33.102}" \
  --add-host="push2.eastmoney.com:${EASTMONEY_PUSH2_IP:-61.129.129.196}" \
  --add-host="proxy.finance.qq.com:${TENCENT_FINANCE_IP:-117.62.241.183}" \
  --add-host="vip.stock.finance.sina.com.cn:${SINA_FINANCE_IP:-116.133.8.236}" \
  -v "$root/evidence:/app/evidence:Z" --entrypoint python \
  value-investment-agent:latest -m value_investment_agent track-candidates || status=$?
if [[ "$status" == 0 ]]; then
  "${runtime[@]}" --memory=256m --memory-swap=384m --entrypoint python \
    value-investment-agent:latest -m value_investment_agent refresh-valuations || status=$?
fi
# Even a failed collection must reach the workbook as a blocking observation.
temporary=$(mktemp "$root/exports/.tracking-export-XXXXXXXX.json")
trap 'rm -f "$temporary"' EXIT
"${runtime[@]}" --memory=384m --memory-swap=512m --entrypoint python \
  value-investment-agent:latest -m value_investment_agent export-payload > "$temporary"
mv "$temporary" "$root/exports/latest.json"
exit "$status"
