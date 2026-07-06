#!/usr/bin/env bash
set -u

ROOT="/opt/meshmon-companion"
CONFIG="${MESHMON_COMPANION_CONFIG:-/etc/meshmon-companion/config.yaml}"
privacy=0
[[ "${1:-}" == "--privacy" ]] && privacy=1

redact() {
  sed -E \
    -e 's/(password|passwd|psk|authkey|token|secret)([[:space:]]*:[[:space:]]*)[^[:space:]]+/\1\2REDACTED/Ig' \
    -e 's/(Password for '\''https:\/\/)[^'\'']+/\1REDACTED/Ig' \
    -e 's/([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}/REDACTED-MAC/g' \
    -e 's/[0-9]{1,3}(\.[0-9]{1,3}){3}/REDACTED-IP/g'
}

section() {
  printf '\n===== %s =====\n' "$1"
}

config_value() {
  local key="$1"
  awk -F': *' -v key="$key" '$1 == key {gsub(/^"|"$/, "", $2); print $2; exit}' "$CONFIG" 2>/dev/null
}

config_section_value() {
  local section="$1" key="$2"
  awk -v section="$section" -v key="$key" '
    $0 ~ "^[^[:space:]].*:$" { current=$1; sub(/:$/, "", current) }
    current == section && $1 == key ":" { print $2; exit }
  ' "$CONFIG" 2>/dev/null
}

curl_check() {
  local url="$1"
  printf -- '--- %s\n' "$url"
  curl -sv --max-time 6 "$url" 2>&1 | head -80 || true
  printf '\n'
}

run_report() {
  section "MeshMonCompanion Doctor"
  date -Is

  section "Identity"
  whoami
  hostname
  hostname -I 2>/dev/null || true

  section "Disk"
  df -h / || true
  lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS 2>/dev/null || true

  section "Tailscale"
  command -v tailscale >/dev/null 2>&1 && tailscale ip -4 || echo "tailscale not installed/found"

  section "Config"
  cat "$CONFIG" 2>&1 || true

  section "Services"
  systemctl --no-pager status docker meshmon-companion 2>&1 || true

  section "Health"
  "$ROOT/scripts/healthcheck.sh" --json 2>&1 || true

  section "Docker Containers"
  docker ps -a 2>&1 || true

  section "Listening Ports"
  ss -ltnp 2>&1 | grep -E ':8080|:8090|:4404|:3001|:4403' || true

  section "Generated Compose"
  cat "$ROOT/docker-compose.yml" 2>&1 || true

  local mesh_port control_port control_bind ts_ip lan_ip
  mesh_port="$(config_section_value ports meshmonitor)"
  control_port="$(config_section_value ports control_panel)"
  control_bind="$(config_value control_bind)"
  mesh_port="${mesh_port:-8080}"
  control_port="${control_port:-8090}"

  section "Local URL Checks"
  curl_check "http://127.0.0.1:${control_port}/"
  curl_check "http://127.0.0.1:${mesh_port}/"
  curl_check "http://127.0.0.1:${mesh_port}/api/status"

  if [[ -n "$control_bind" && "$control_bind" != "0.0.0.0" && "$control_bind" != "127.0.0.1" ]]; then
    section "Configured URL Checks"
    curl_check "http://${control_bind}:${control_port}/"
    curl_check "http://${control_bind}:${mesh_port}/"
    curl_check "http://${control_bind}:${mesh_port}/api/status"
  fi

  section "Tailscale URL Checks"
  ts_ip="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
  if [[ -n "$ts_ip" ]]; then
    curl_check "http://${ts_ip}:${control_port}/"
    curl_check "http://${ts_ip}:${mesh_port}/"
    curl_check "http://${ts_ip}:${mesh_port}/api/status"
  else
    echo "No Tailscale IP found"
  fi

  section "LAN URL Checks"
  lan_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -n "$lan_ip" ]]; then
    curl_check "http://${lan_ip}:${control_port}/"
    curl_check "http://${lan_ip}:${mesh_port}/"
    curl_check "http://${lan_ip}:${mesh_port}/api/status"
  else
    echo "No LAN IP found"
  fi

  section "Recent Companion Logs"
  journalctl -u meshmon-companion --no-pager -n 120 2>&1 || true

  section "Recent MeshMonitor Logs"
  docker logs --tail 120 meshmonitor 2>&1 || true

  section "Recent Serial Bridge Logs"
  docker logs --tail 120 meshmon-serial-bridge 2>&1 || true

  section "Done"
}

if [[ "$privacy" == "1" ]]; then
  run_report | redact
else
  run_report
fi
