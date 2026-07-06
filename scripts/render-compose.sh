#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/meshmon-companion"
CONFIG="${MESHMON_COMPANION_CONFIG:-/etc/meshmon-companion/config.yaml}"
OUT="$ROOT/docker-compose.yml"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE="$ROOT/compose/docker-compose.yml.template"
if [[ ! -f "$TEMPLATE" ]]; then
  TEMPLATE="$(cd "$SCRIPT_DIR/.." && pwd)/compose/docker-compose.yml.template"
fi

get_value() {
  key="$1"
  awk -F': *' -v key="$key" '$1 == key {print $2; exit}' "$CONFIG" | sed 's/^"//;s/"$//'
}

serial_connection="$(awk '/serial:/ {s=1} s && /connection_type:/ {print $2; exit}' "$CONFIG")"
serial_device="$(awk '/serial:/ {s=1} s && /device:/ {print $2; exit}' "$CONFIG")"
serial_baud="$(awk '/serial:/ {s=1} s && /baud:/ {print $2; exit}' "$CONFIG")"
tcp_host="$(awk '/serial:/ {s=1} s && /tcp_host:/ {print $2; exit}' "$CONFIG" | tr -d '\"')"
tcp_port="$(awk '/serial:/ {s=1} s && /tcp_port:/ {print $2; exit}' "$CONFIG")"
mesh_port="$(awk '/ports:/ {s=1} s && /meshmonitor:/ {print $2; exit}' "$CONFIG")"
virtual_port="$(awk '/ports:/ {s=1} s && /virtual_node:/ {print $2; exit}' "$CONFIG")"
control_port="$(awk '/ports:/ {s=1} s && /control_panel:/ {print $2; exit}' "$CONFIG")"
access_mode="$(get_value access_mode)"
control_bind="$(get_value control_bind)"
mesh_image="$(awk '/meshmonitor:/ {s=1} s && /image:/ {print $2; exit}' "$CONFIG")"
bridge_image="$(awk '/serial_bridge:/ {s=1} s && /image:/ {print $2; exit}' "$CONFIG")"

serial_baud="${serial_baud:-115200}"
mesh_port="${mesh_port:-8080}"
virtual_port="${virtual_port:-4404}"
control_port="${control_port:-8090}"
mesh_image="${mesh_image:-ghcr.io/yeraze/meshmonitor:latest}"
bridge_image="${bridge_image:-ghcr.io/yeraze/meshtastic-serial-bridge:latest}"
serial_connection="${serial_connection:-usb}"

bind_ip="127.0.0.1"
if [[ "$access_mode" == "tailscale" ]] && command -v tailscale >/dev/null 2>&1; then
  bind_ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  bind_ip="${bind_ip:-127.0.0.1}"
elif [[ "$access_mode" == "lan" ]]; then
  bind_ip="0.0.0.0"
elif [[ "$access_mode" == "all" ]]; then
  bind_ip="0.0.0.0"
fi

mkdir -p "$ROOT"
export SERIAL_DEVICE="$serial_device"
export SERIAL_BAUD="$serial_baud"
export MESHMONITOR_IMAGE="$mesh_image"
export SERIAL_BRIDGE_IMAGE="$bridge_image"
export ALLOWED_ORIGINS="http://${bind_ip}:${mesh_port}"
export MESH_PORT="$mesh_port"
export VIRTUAL_PORT="$virtual_port"
export BIND_IP="$bind_ip"
export TEMPLATE
export SERIAL_CONNECTION="$serial_connection"
export TCP_HOST="$tcp_host"
export TCP_PORT="${tcp_port:-4403}"

python3 - <<'PY' > "$OUT"
import os

serial_connection = os.environ["SERIAL_CONNECTION"]
bind_ip = os.environ["BIND_IP"]
mesh_port = os.environ["MESH_PORT"]
virtual_port = os.environ["VIRTUAL_PORT"]
mesh_image = os.environ["MESHMONITOR_IMAGE"]
bridge_image = os.environ["SERIAL_BRIDGE_IMAGE"]
allowed = os.environ["ALLOWED_ORIGINS"]

print("services:")
if serial_connection == "usb":
    serial_device = os.environ["SERIAL_DEVICE"]
    serial_baud = os.environ["SERIAL_BAUD"]
    print(f"""  serial-bridge:
    image: {bridge_image}
    container_name: meshmon-serial-bridge
    devices:
      - {serial_device}:/dev/ttyACM0
    expose:
      - "4403"
    environment:
      SERIAL_DEVICE: /dev/ttyACM0
      BAUD_RATE: {serial_baud}
      TCP_PORT: 4403
    restart: unless-stopped
    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"
""")
    node_host = "serial-bridge"
    node_port = "4403"
    depends = "    depends_on:\n      - serial-bridge\n"
elif serial_connection == "tcp":
    node_host = os.environ["TCP_HOST"]
    node_port = os.environ["TCP_PORT"]
    depends = ""
else:
    node_host = ""
    node_port = "4403"
    depends = ""

env_lines = f"""      ALLOWED_ORIGINS: {allowed}"""
if node_host:
    env_lines = f"""      MESHTASTIC_NODE_IP: {node_host}
      MESHTASTIC_TCP_PORT: {node_port}
{env_lines}"""

print(f"""  meshmonitor:
    image: {mesh_image}
    container_name: meshmonitor
    ports:
      - {bind_ip}:{mesh_port}:3001
      - {bind_ip}:{virtual_port}:4404
    volumes:
      - /opt/meshmon-companion/data/meshmonitor:/data
    environment:
{env_lines}
    restart: unless-stopped
{depends}    logging:
      driver: json-file
      options:
        max-size: 10m
        max-file: "3"
""")
PY

mkdir -p /etc/default
cat > /etc/default/meshmon-companion <<EOF
MESHMON_COMPANION_BIND=${control_bind:-$bind_ip}
MESHMON_COMPANION_PORT=$control_port
EOF
