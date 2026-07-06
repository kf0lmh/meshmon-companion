#!/usr/bin/env bash
set -euo pipefail

if ! systemctl list-unit-files tailscaled.service >/dev/null 2>&1; then
  echo "tailscaled.service is not installed"
  exit 0
fi

systemctl restart tailscaled.service
echo "Tailscale restarted"
