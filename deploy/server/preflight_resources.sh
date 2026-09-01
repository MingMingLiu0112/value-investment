#!/usr/bin/env bash
set -euo pipefail

minimum_available_kb=1258291
available_kb="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
swap_free_kb="$(awk '/SwapFree:/ {print $2}' /proc/meminfo)"

if (( available_kb < minimum_available_kb )); then
  printf 'Refusing deployment: only %s MiB RAM is available; at least 1228 MiB is required.\n' "$((available_kb / 1024))" >&2
  printf 'Free swap: %s MiB. Existing services are protected by this gate.\n' "$((swap_free_kb / 1024))" >&2
  exit 75
fi

printf 'Resource preflight passed: %s MiB RAM and %s MiB swap available.\n' "$((available_kb / 1024))" "$((swap_free_kb / 1024))"
