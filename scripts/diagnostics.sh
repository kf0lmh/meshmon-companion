#!/usr/bin/env bash
set -euo pipefail

privacy=0
[[ "${1:-}" == "--privacy" ]] && privacy=1
out="/tmp/meshmon-companion-diagnostics-$(date +%F_%H%M%S).txt"

redact() {
  sed -E \
    -e 's/(password|passwd|psk|authkey|token|secret):[^[:space:]]+/\1: REDACTED/Ig' \
    -e 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/REDACTED-MAC/g' \
    -e 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/REDACTED-IP/g'
}

{
  echo "MeshMonCompanion diagnostics"
  date -Is
  hostnamectl || true
  ip -br addr || true
  systemctl status meshmon-companion --no-pager || true
  /opt/meshmon-companion/scripts/healthcheck.sh --json || true
  docker ps || true
} | { [[ "$privacy" == "1" ]] && redact || cat; } > "$out"

echo "$out"
