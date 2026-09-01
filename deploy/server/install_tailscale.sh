#!/usr/bin/env bash
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
systemctl enable --now tailscaled
tailscale up --ssh
echo "After authorizing the URL above, run: tailscale serve --tcp=5432 tcp://127.0.0.1:5432"
