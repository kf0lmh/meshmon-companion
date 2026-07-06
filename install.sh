#!/usr/bin/env bash
set -euo pipefail

PROJECT_NAME="MeshMonCompanion"
INSTALL_DIR="/opt/meshmon-companion"
CONFIG_DIR="/etc/meshmon-companion"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SERVICE_USER="meshmon"
OWNER="${MESHMON_COMPANION_OWNER:-kf0lmh}"
REPO_URL="https://github.com/${OWNER}/meshmon-companion"
SOURCE_DIR=""
LOG_FILE="${MESHMON_COMPANION_LOG:-/tmp/meshmon-companion-install-$(date +%F_%H%M%S).log}"

DRY_RUN=0
MODE="install"
WIZARD=1

start_logging() {
  if [[ "${MESHMON_COMPANION_NO_LOG:-0}" == "1" || -n "${MESHMON_COMPANION_LOG_ACTIVE:-}" ]]; then
    return
  fi
  export MESHMON_COMPANION_LOG_ACTIVE=1
  touch "$LOG_FILE"
  chmod 600 "$LOG_FILE" 2>/dev/null || true
  exec > >(tee -a "$LOG_FILE") 2>&1
  printf '[%s] Install log: %s\n' "$PROJECT_NAME" "$LOG_FILE"
}

start_logging

usage() {
  cat <<'EOF'
MeshMonCompanion installer

Usage:
  ./install.sh [--help] [--dry-run] [--uninstall] [--update] [--non-interactive]

Options:
  --help       Show this help
  --dry-run    Print planned actions without changing the system
  --uninstall  Remove services and installed application files
  --update     Reinstall application files and restart services
  --non-interactive  Use conservative defaults and skip optional setup prompts

Review-first install:
  curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh -o install.sh
  less install.sh
  sudo bash install.sh

Logged one-command install:
  curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh -o /tmp/meshmon-companion-install.sh && sudo bash /tmp/meshmon-companion-install.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1 ;;
    --uninstall) MODE="uninstall" ;;
    --update) MODE="update" ;;
    --non-interactive) WIZARD=0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

log() { printf '[%s] %s\n' "$PROJECT_NAME" "$*"; }
run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run]'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

ask() {
  local prompt="$1" default="${2:-}" answer
  if [[ "$WIZARD" != "1" || ! -t 0 ]]; then
    printf '%s\n' "$default"
    return
  fi
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " answer
    printf '%s\n' "${answer:-$default}"
  else
    read -r -p "$prompt: " answer
    printf '%s\n' "$answer"
  fi
}

ask_yes_no() {
  local prompt="$1" default="${2:-no}" answer
  if [[ "$WIZARD" != "1" || ! -t 0 ]]; then
    [[ "$default" == "yes" ]] && return 0 || return 1
  fi
  while true; do
    read -r -p "$prompt [${default}]: " answer
    answer="${answer:-$default}"
    case "$answer" in
      y|Y|yes|YES) return 0 ;;
      n|N|no|NO) return 1 ;;
      *) echo "Please answer yes or no." ;;
    esac
  done
}

ask_secret() {
  local prompt="$1" answer
  if [[ "$WIZARD" != "1" || ! -t 0 ]]; then
    printf '\n'
    return
  fi
  read -r -s -p "$prompt: " answer
  printf '\n' >&2
  printf '%s\n' "$answer"
}

port_available() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ! ss -H -ltn "sport = :$port" | grep -q .
  else
    ! python3 - "$port" <<'PY'
import socket, sys
port = int(sys.argv[1])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sys.exit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
  fi
}

choose_port() {
  local label="$1" default="$2" port
  port="$(ask "$label" "$default")"
  if ! [[ "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "Invalid port: $port" >&2
    exit 1
  fi
  if ! port_available "$port"; then
    echo "Port $port is already in use. Free it or rerun the installer and choose another port." >&2
    exit 1
  fi
  printf '%s\n' "$port"
}

need_root() {
  [[ "$DRY_RUN" == "1" ]] && return 0
  if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "Please run as root, for example: sudo ./install.sh" >&2
    exit 1
  fi
}

detect_os() {
  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    OS_NAME="${PRETTY_NAME:-unknown}"
    OS_ID="${ID:-unknown}"
    OS_LIKE="${ID_LIKE:-}"
  else
    OS_NAME="unknown"; OS_ID="unknown"; OS_LIKE=""
  fi
  ARCH="$(uname -m)"
  if [[ "$OS_ID" != "debian" && "$OS_ID" != "raspbian" && "$OS_LIKE" != *debian* ]]; then
    echo "Unsupported OS: $OS_NAME. Raspberry Pi OS or Debian-based systems are expected." >&2
    exit 1
  fi
  case "$ARCH" in
    aarch64|armv7l|armv6l|x86_64) ;;
    *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
  esac
  command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
}

install_packages() {
  if ! command -v docker >/dev/null 2>&1; then
    log "Docker not found. Installing Docker using the official convenience script."
    run sh -c 'curl -fsSL https://get.docker.com | sh'
  else
    log "Docker already installed."
  fi
  if ! docker compose version >/dev/null 2>&1; then
    log "Docker Compose plugin missing. Installing docker-compose-plugin if available."
    run apt-get update
    run apt-get install -y docker-compose-plugin
  else
    log "Docker Compose plugin already installed."
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    run apt-get update
    run apt-get install -y python3
  fi
  if ! command -v rsync >/dev/null 2>&1; then
    run apt-get update
    run apt-get install -y rsync
  fi
  if ! command -v whiptail >/dev/null 2>&1 && ! command -v dialog >/dev/null 2>&1; then
    run apt-get update
    run apt-get install -y whiptail
  fi
}

prepare_source() {
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [[ -f "$script_dir/app/server.py" && -d "$script_dir/scripts" ]]; then
    SOURCE_DIR="$script_dir"
    return
  fi
  SOURCE_DIR="/tmp/meshmon-companion-src"
  log "Local project files not found beside installer. Fetching source archive from $REPO_URL"
  run rm -rf "$SOURCE_DIR"
  run mkdir -p "$SOURCE_DIR"
  if [[ "$DRY_RUN" == "1" ]]; then
    return
  fi
  curl -fsSL "$REPO_URL/archive/refs/heads/main.tar.gz" -o /tmp/meshmon-companion-main.tar.gz
  tar -xzf /tmp/meshmon-companion-main.tar.gz -C "$SOURCE_DIR" --strip-components=1
}

choose_serial_device() {
  local discover="$INSTALL_DIR/scripts/discover.sh"
  [[ -x "$discover" ]] || discover="$SOURCE_DIR/scripts/discover.sh"
  mapfile -t devices < <("$discover" --paths-only 2>/dev/null || true)
  if [[ "${#devices[@]}" -eq 0 ]]; then
    echo "No USB serial Meshtastic candidate found." >&2
    echo "Connect the node, check USB cable/data mode, then rerun the installer." >&2
    exit 1
  elif [[ "${#devices[@]}" -eq 1 ]]; then
    SERIAL_DEVICE="${devices[0]}"
  else
    echo "Multiple serial devices found:"
    select dev in "${devices[@]}"; do
      [[ -n "$dev" ]] && SERIAL_DEVICE="$dev" && break
    done
  fi
}

choose_connection() {
  CONNECTION_TYPE="usb"
  TCP_HOST=""
  TCP_PORT="4403"
  if [[ "$WIZARD" == "1" && -t 0 ]]; then
    echo
    echo "Connection type:"
    echo "  1. USB serial node connected to this Pi - recommended"
    echo "  2. Existing TCP serial bridge"
    echo "  3. Skip detection for now"
    choice="$(ask "Choose connection type" "1")"
    case "$choice" in
      1) CONNECTION_TYPE="usb" ;;
      2) CONNECTION_TYPE="tcp" ;;
      3) CONNECTION_TYPE="skip" ;;
      *) CONNECTION_TYPE="usb" ;;
    esac
  fi

  case "$CONNECTION_TYPE" in
    usb)
      choose_serial_device
      ;;
    tcp)
      SERIAL_DEVICE=""
      TCP_HOST="$(ask "TCP serial bridge host" "")"
      TCP_PORT="$(ask "TCP serial bridge port" "4403")"
      if [[ -z "$TCP_HOST" ]]; then
        echo "TCP host is required for TCP mode." >&2
        exit 1
      fi
      if command -v nc >/dev/null 2>&1; then
        nc -zvw5 "$TCP_HOST" "$TCP_PORT" </dev/null || echo "Warning: TCP bridge validation failed; continuing with saved config." >&2
      fi
      ;;
    skip)
      SERIAL_DEVICE=""
      ;;
  esac
}

choose_access_mode() {
  local ts_ip=""
  ACCESS_MODE="localhost"
  CONTROL_BIND="127.0.0.1"
  if command -v tailscale >/dev/null 2>&1; then
    ts_ip="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  fi
  if [[ -n "$ts_ip" ]]; then
    ACCESS_MODE="tailscale"
    CONTROL_BIND="$ts_ip"
  fi

  if [[ "$WIZARD" == "1" && -t 0 ]]; then
    echo
    echo "Access mode:"
    echo "  1. Tailscale only - recommended when Tailscale is installed"
    echo "  2. Localhost only - safest default without Tailscale"
    echo "  3. LAN only"
    echo "  4. All interfaces - not recommended"
    default_choice="2"
    [[ -n "$ts_ip" ]] && default_choice="1"
    choice="$(ask "Choose access mode" "$default_choice")"
    case "$choice" in
      1)
        if [[ -z "$ts_ip" ]]; then
          echo "Tailscale IP not detected. Falling back to localhost." >&2
          ACCESS_MODE="localhost"; CONTROL_BIND="127.0.0.1"
        else
          ACCESS_MODE="tailscale"; CONTROL_BIND="$ts_ip"
        fi
        ;;
      2) ACCESS_MODE="localhost"; CONTROL_BIND="127.0.0.1" ;;
      3) ACCESS_MODE="lan"; CONTROL_BIND="0.0.0.0" ;;
      4)
        if ask_yes_no "All interfaces may expose admin tools beyond trusted networks. Continue?" "no"; then
          ACCESS_MODE="all"; CONTROL_BIND="0.0.0.0"
        else
          ACCESS_MODE="localhost"; CONTROL_BIND="127.0.0.1"
        fi
        ;;
      *) ;;
    esac
  fi
  TAILSCALE_ENABLED="false"
  TAILSCALE_IP="$ts_ip"
  [[ -n "$ts_ip" ]] && TAILSCALE_ENABLED="true"
}

optional_tailscale_setup() {
  if command -v tailscale >/dev/null 2>&1 && tailscale ip -4 >/dev/null 2>&1; then
    return
  fi
  if ask_yes_no "Install/configure Tailscale now?" "no"; then
    log "Installing Tailscale. Follow the official login URL shown by tailscale up."
    run sh -c 'curl -fsSL https://tailscale.com/install.sh | sh'
    run tailscale up
  fi
}

optional_wifi_setup() {
  if ! ask_yes_no "Configure Wi-Fi now?" "no"; then
    return
  fi
  if ! command -v nmcli >/dev/null 2>&1; then
    echo "NetworkManager/nmcli not found. Wi-Fi setup is not implemented for this backend yet." >&2
    return
  fi
  ssid="$(ask "Wi-Fi SSID" "")"
  pass="$(ask_secret "Wi-Fi password (input hidden)")"
  if [[ -z "$ssid" || -z "$pass" ]]; then
    echo "SSID and password are required; skipping Wi-Fi setup." >&2
    return
  fi
  echo "Changing Wi-Fi can disconnect SSH."
  if ask_yes_no "Type yes to continue with Wi-Fi change" "no"; then
    run nmcli dev wifi connect "$ssid" password "$pass"
  fi
}

optional_mqtt_setup() {
  MQTT_ENABLED="false"
  MQTT_REBROADCAST="false"
  MQTT_BROKER=""
  MQTT_USERNAME=""
  MQTT_PASSWORD_FILE="/etc/meshmon-companion/secrets/mqtt-password"

  if ask_yes_no "Enable MQTT support?" "no"; then
    MQTT_ENABLED="true"
    MQTT_BROKER="$(ask "MQTT broker URL" "")"
    MQTT_USERNAME="$(ask "MQTT username (blank if none)" "")"
    mqtt_password="$(ask_secret "MQTT password/token (blank if none)")"
    if [[ -n "$mqtt_password" && "$DRY_RUN" != "1" ]]; then
      install -d -m 700 "$CONFIG_DIR/secrets"
      printf '%s\n' "$mqtt_password" > "$MQTT_PASSWORD_FILE"
      chmod 600 "$MQTT_PASSWORD_FILE"
    fi
    echo "MQTT may send mesh-related data outside the local node."
    if ask_yes_no "Enable MQTT rebroadcasting?" "no"; then
      echo "MQTT rebroadcasting may increase mesh traffic and can affect battery/solar nodes."
      if ask_yes_no "Confirm MQTT rebroadcasting" "no"; then
        MQTT_REBROADCAST="true"
      fi
    fi
  fi
}

write_config() {
  if [[ -f "$CONFIG_FILE" ]]; then
    log "Existing config preserved: $CONFIG_FILE"
    return
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    log "Would run setup wizard and write generated config to $CONFIG_FILE"
    return
  fi
  optional_tailscale_setup
  choose_connection
  choose_access_mode
  optional_wifi_setup
  optional_mqtt_setup
  HOSTNAME_LABEL="$(ask "Display name for this Pi" "example-node")"
  MESH_PORT="$(choose_port "MeshMonitor port" "8080")"
  CONTROL_PORT="$(choose_port "MeshMonCompanion control panel port" "8090")"
  VIRTUAL_PORT="$(choose_port "MeshMonitor virtual node port" "4404")"
  run mkdir -p "$CONFIG_DIR"
  cat > "$CONFIG_FILE" <<EOF
hostname_label: $HOSTNAME_LABEL
access_mode: $ACCESS_MODE
control_bind: $CONTROL_BIND
ports:
  meshmonitor: $MESH_PORT
  control_panel: $CONTROL_PORT
  virtual_node: $VIRTUAL_PORT
serial:
  connection_type: $CONNECTION_TYPE
  device: $SERIAL_DEVICE
  baud: 115200
  tcp_host: "$TCP_HOST"
  tcp_port: $TCP_PORT
tailscale:
  enabled: $TAILSCALE_ENABLED
  ip: "$TAILSCALE_IP"
meshmonitor:
  image: ghcr.io/yeraze/meshmonitor:latest
  allowed_origins:
    - http://$CONTROL_BIND:$MESH_PORT
serial_bridge:
  image: ghcr.io/yeraze/meshtastic-serial-bridge:latest
mqtt:
  enabled: $MQTT_ENABLED
  rebroadcast_enabled: $MQTT_REBROADCAST
  broker: "$MQTT_BROKER"
  username: "$MQTT_USERNAME"
  password_file: $MQTT_PASSWORD_FILE
backups:
  include_secret_paths: false
  schedule: daily
  max_mb: 500
EOF
  chmod 600 "$CONFIG_FILE"
}

install_files() {
  run useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER" 2>/dev/null || true
  run mkdir -p "$INSTALL_DIR" "$CONFIG_DIR"
  run rsync -a --delete --exclude '.git' "$SOURCE_DIR"/ "$INSTALL_DIR"/
  run chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
  run chown root:root "$INSTALL_DIR"/scripts/*.sh
  run chmod 755 "$INSTALL_DIR"/scripts/*.sh
  run install -o root -g root -m 0755 "$INSTALL_DIR/scripts/meshmon-companion.sh" /usr/local/bin/meshmon-companion
  run install -o root -g root -m 0755 "$INSTALL_DIR/scripts/companion-menu.sh" /usr/local/bin/companion-menu
  run install -o root -g root -m 0644 "$INSTALL_DIR/systemd/meshmon-companion.service" /etc/systemd/system/meshmon-companion.service
  run install -o root -g root -m 0644 "$INSTALL_DIR/systemd/meshmon-companion-backup.service" /etc/systemd/system/meshmon-companion-backup.service
  run install -o root -g root -m 0644 "$INSTALL_DIR/systemd/meshmon-companion-backup.timer" /etc/systemd/system/meshmon-companion-backup.timer
  run install -o root -g root -m 0440 "$INSTALL_DIR/sudoers/meshmon-companion" /etc/sudoers.d/meshmon-companion
}

render_compose() {
  run "$INSTALL_DIR/scripts/render-compose.sh"
}

start_stack() {
  run sh -c "cd '$INSTALL_DIR' && docker compose up -d --remove-orphans"
}

enable_services() {
  run systemctl daemon-reload
  run systemctl enable meshmon-companion.service
  run systemctl restart meshmon-companion.service
  run systemctl enable --now meshmon-companion-backup.timer
}

config_value() {
  local key="$1"
  awk -F': *' -v key="$key" '$1 == key {gsub(/^"|"$/, "", $2); print $2; exit}' "$CONFIG_FILE" 2>/dev/null
}

config_section_value() {
  local section="$1" key="$2"
  awk -v section="$section" -v key="$key" '
    $0 ~ "^[^[:space:]].*:$" { current=$1; sub(/:$/, "", current) }
    current == section && $1 == key ":" { print $2; exit }
  ' "$CONFIG_FILE" 2>/dev/null
}

warn_disk_size() {
  local size_gb used avail pct
  [[ "$DRY_RUN" == "1" ]] && return
  read -r size_gb used avail pct < <(df -BG / | awk 'NR == 2 {gsub("G", "", $2); print $2, $3, $4, $5}')
  if [[ -n "${size_gb:-}" && "$size_gb" =~ ^[0-9]+$ && "$size_gb" -lt 12 ]]; then
    echo
    echo "Warning: root filesystem is only ${size_gb}G. 16G minimum is recommended; 32G or larger is better for Docker logs, updates, and backups."
    echo "Current root usage: used ${used}, free ${avail}, ${pct} full."
  fi
}

print_install_summary() {
  local control_bind access_mode mesh_port control_port display_host
  [[ "$DRY_RUN" == "1" ]] && return
  control_bind="$(config_value control_bind)"
  access_mode="$(config_value access_mode)"
  mesh_port="$(config_section_value ports meshmonitor)"
  control_port="$(config_section_value ports control_panel)"
  mesh_port="${mesh_port:-8080}"
  control_port="${control_port:-8090}"
  display_host="$control_bind"
  if [[ -z "$display_host" || "$display_host" == "0.0.0.0" ]]; then
    display_host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  display_host="${display_host:-127.0.0.1}"

  echo
  log "Install/update summary"
  echo "Access mode: ${access_mode:-unknown}"
  echo "Control panel: http://${display_host}:${control_port}"
  echo "MeshMonitor:   http://${display_host}:${mesh_port}"
  echo "SSH menu:      companion-menu"
  echo
  echo "Docker stack:"
  run sh -c "cd '$INSTALL_DIR' && docker compose ps"
  echo
  echo "Health:"
  run "$INSTALL_DIR/scripts/healthcheck.sh" --json || true
  warn_disk_size
}

uninstall() {
  need_root
  log "Uninstalling services. Backups and config are left in place unless removed manually."
  run sh -c "cd '$INSTALL_DIR' && docker compose down" 2>/dev/null || true
  run systemctl disable --now meshmon-companion.service meshmon-companion-backup.timer 2>/dev/null || true
  run rm -f /etc/systemd/system/meshmon-companion.service /etc/systemd/system/meshmon-companion-backup.service /etc/systemd/system/meshmon-companion-backup.timer
  run rm -f /etc/sudoers.d/meshmon-companion /usr/local/bin/meshmon-companion /usr/local/bin/companion-menu
  run systemctl daemon-reload
}

main() {
  need_root
  detect_os
  if [[ "$MODE" == "uninstall" ]]; then
    uninstall
    exit 0
  fi
  install_packages
  prepare_source
  install_files
  write_config
  render_compose
  start_stack
  enable_services
  print_install_summary
  log "Install complete. Run: meshmon-companion doctor for a full diagnostic report."
}

main
