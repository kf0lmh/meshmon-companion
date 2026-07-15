#!/usr/bin/env bash
set -euo pipefail

CONFIG="${MESHMON_COMPANION_CONFIG:-/etc/meshmon-companion/config.yaml}"
OUT="${FIELDSTATION_ENV_OUT:-/etc/default/fieldstation}"

section_value() {
  local section="$1" key="$2" default="$3"
  local value
  value="$(awk -v section="$section" -v key="$key" '
    $0 ~ "^[^[:space:]].*:$" { current=$1; sub(/:$/, "", current) }
    current == section && $1 == key ":" { print $2; exit }
  ' "$CONFIG" 2>/dev/null | tr -d '"')"
  printf '%s\n' "${value:-$default}"
}

top_value() {
  local key="$1" default="$2"
  local value
  value="$(awk -F': *' -v key="$key" '$1 == key {print $2; exit}' "$CONFIG" 2>/dev/null | tr -d '"')"
  printf '%s\n' "${value:-$default}"
}

port_value() {
  local key="$1" default="$2"
  section_value ports "$key" "$default"
}

control_bind="$(top_value control_bind "127.0.0.1")"
fieldstation_bind="$(section_value fieldstation bind "$control_bind")"
fieldstation_port="$(section_value fieldstation port "$(port_value fieldstation "8091")")"
fieldstation_db="$(section_value fieldstation database "/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3")"
read_only_usb_enabled="$(section_value fieldstation read_only_usb_enabled "true")"
serial_autodetect="$(section_value fieldstation serial_autodetect "true")"
adapter_cache_seconds="$(section_value fieldstation adapter_cache_seconds "30")"
read_timeout_seconds="$(section_value fieldstation read_timeout_seconds "12")"
serial_device="$(section_value serial device "")"

mkdir -p "$(dirname "$OUT")"
cat > "$OUT" <<EOF
FIELDSTATION_BIND=$fieldstation_bind
FIELDSTATION_PORT=$fieldstation_port
FIELDSTATION_DB=$fieldstation_db
FIELDSTATION_SERIAL_PORT=$serial_device
FIELDSTATION_ENABLE_MESHTASTIC=$read_only_usb_enabled
FIELDSTATION_SERIAL_AUTODETECT=$serial_autodetect
FIELDSTATION_ADAPTER_CACHE_SECONDS=$adapter_cache_seconds
FIELDSTATION_MESHTASTIC_READ_TIMEOUT=$read_timeout_seconds
EOF
