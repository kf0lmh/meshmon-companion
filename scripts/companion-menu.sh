#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/meshmon-companion"
SCRIPTS="$ROOT/scripts"
CONFIG="${MESHMON_COMPANION_CONFIG:-/etc/meshmon-companion/config.yaml}"

if command -v whiptail >/dev/null 2>&1; then
  UI="whiptail"
elif command -v dialog >/dev/null 2>&1; then
  UI="dialog"
else
  echo "whiptail or dialog is required for companion-menu." >&2
  exit 1
fi

tmpfile() {
  mktemp /tmp/companion-menu.XXXXXX
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

display_host() {
  local host
  host="$(config_value control_bind)"
  if [[ -z "$host" || "$host" == "0.0.0.0" || "$host" == "::" ]]; then
    host="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s\n' "${host:-127.0.0.1}"
}

mesh_port() {
  config_section_value ports meshmonitor | awk '{print $1}'
}

control_port() {
  config_section_value ports control_panel | awk '{print $1}'
}

serial_device() {
  awk '/serial:/ {s=1} s && /device:/ {print $2; exit}' "$CONFIG" 2>/dev/null
}

show_text() {
  local title="$1" file="$2"
  if [[ "$UI" == "whiptail" ]]; then
    whiptail --title "$title" --scrolltext --textbox "$file" 24 90
  else
    dialog --title "$title" --textbox "$file" 24 90
  fi
}

show_message() {
  local title="$1" message="$2"
  if [[ "$UI" == "whiptail" ]]; then
    whiptail --title "$title" --msgbox "$message" 12 78
  else
    dialog --title "$title" --msgbox "$message" 12 78
  fi
}

confirm() {
  local message="$1"
  if [[ "$UI" == "whiptail" ]]; then
    whiptail --title "Confirm" --yesno "$message" 10 76
  else
    dialog --title "Confirm" --yesno "$message" 10 76
  fi
}

run_capture() {
  local title="$1"
  shift
  local out
  out="$(tmpfile)"
  {
    echo "$ $*"
    echo
    "$@"
  } >"$out" 2>&1 || true
  show_text "$title" "$out"
  rm -f "$out"
}

run_shell() {
  local title="$1"
  shift
  local out
  out="$(tmpfile)"
  {
    echo "$ $*"
    echo
    bash -lc "$*"
  } >"$out" 2>&1 || true
  show_text "$title" "$out"
  rm -f "$out"
}

health_check() {
  run_shell "Health Check" "sudo '$SCRIPTS/healthcheck.sh' --json | python3 -m json.tool"
}

doctor_report() {
  run_capture "Doctor Report" sudo "$SCRIPTS/doctor.sh" --privacy
}

system_status() {
  run_shell "System Status" "hostnamectl; echo; uptime; echo; free -h; echo; df -h / /boot/firmware 2>/dev/null || df -h /; echo; command -v vcgencmd >/dev/null && { sudo vcgencmd get_throttled; sudo vcgencmd measure_temp; } || true; echo; systemctl --failed --no-pager"
}

network_status() {
  run_shell "Network / Tailscale" "ip -br addr; echo; ip route; echo; command -v nmcli >/dev/null && nmcli -t -f DEVICE,TYPE,STATE,CONNECTION device status || true; echo; command -v tailscale >/dev/null && { tailscale status; echo; tailscale ip -4; } || echo 'Tailscale not installed/found'"
}

meshmonitor_status() {
  local port host
  port="$(mesh_port)"
  host="$(display_host)"
  port="${port:-8080}"
  run_shell "MeshMonitor Status" "cd '$ROOT' && docker compose ps meshmonitor; echo; curl -sS --max-time 10 'http://$host:$port/api/status' | python3 -m json.tool"
}

serial_bridge_status() {
  local device
  device="$(serial_device)"
  run_shell "Serial Bridge Status" "cd '$ROOT' && docker compose ps serial-bridge; echo; test -n '$device' && ls -l '$device' 2>/dev/null || true; ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null || true; echo; docker logs --tail 80 meshmon-serial-bridge 2>&1"
}

create_backup() {
  local label
  label=""
  if [[ "$UI" == "whiptail" ]]; then
    label="$(whiptail --title "Create Backup" --inputbox "Optional backup name" 10 76 3>&1 1>&2 2>&3)" || return 0
  else
    label="$(dialog --title "Create Backup" --inputbox "Optional backup name" 10 76 3>&1 1>&2 2>&3)" || return 0
  fi
  run_capture "Create Backup" sudo "$SCRIPTS/backup-now.sh" --label "$label"
}

list_backups() {
  run_capture "Backups" sudo "$SCRIPTS/list-backups.sh"
}

docker_logs() {
  run_shell "Recent Docker Logs" "echo '=== meshmonitor ==='; docker logs --tail 120 meshmonitor 2>&1; echo; echo '=== meshmon-serial-bridge ==='; docker logs --tail 120 meshmon-serial-bridge 2>&1"
}

main_menu() {
  local host cport mport control_url mesh_url prompt choice
  while true; do
    host="$(display_host)"
    cport="$(control_port)"
    mport="$(mesh_port)"
    cport="${cport:-8090}"
    mport="${mport:-8080}"
    control_url="http://$host:$cport/"
    mesh_url="http://$host:$mport/"
    prompt="Control panel: $control_url\nMeshMonitor: $mesh_url"

    if [[ "$UI" == "whiptail" ]]; then
      choice="$(
        whiptail --title "MeshMonCompanion" --menu "$prompt" 24 86 15 \
          health "Run health check" \
          doctor "Show privacy-redacted doctor report" \
          system "Show system status" \
          network "Show network/Tailscale status" \
          mesh "Show MeshMonitor status" \
          serial "Show serial bridge status" \
          restart_mesh "Restart MeshMonitor" \
          restart_serial "Restart serial bridge" \
          restart_stack "Restart full mesh stack" \
          restart_tailscale "Restart Tailscale" \
          backup "Create backup now" \
          list_backups "List backups" \
          docker_logs "Show recent Docker logs" \
          reboot "Reboot Pi" \
          exit "Exit" \
          3>&1 1>&2 2>&3
      )" || exit 0
    else
      choice="$(
        dialog --title "MeshMonCompanion" --menu "$prompt" 24 86 15 \
          health "Run health check" \
          doctor "Show privacy-redacted doctor report" \
          system "Show system status" \
          network "Show network/Tailscale status" \
          mesh "Show MeshMonitor status" \
          serial "Show serial bridge status" \
          restart_mesh "Restart MeshMonitor" \
          restart_serial "Restart serial bridge" \
          restart_stack "Restart full mesh stack" \
          restart_tailscale "Restart Tailscale" \
          backup "Create backup now" \
          list_backups "List backups" \
          docker_logs "Show recent Docker logs" \
          reboot "Reboot Pi" \
          exit "Exit" \
          3>&1 1>&2 2>&3
      )" || exit 0
    fi

    case "$choice" in
      health) health_check ;;
      doctor) doctor_report ;;
      system) system_status ;;
      network) network_status ;;
      mesh) meshmonitor_status ;;
      serial) serial_bridge_status ;;
      restart_mesh) run_capture "Restart MeshMonitor" sudo "$SCRIPTS/restart-meshmonitor.sh" ;;
      restart_serial) run_capture "Restart Serial Bridge" sudo "$SCRIPTS/restart-serial-bridge.sh" ;;
      restart_stack)
        confirm "Restart the full mesh stack? MeshMonitor and the serial bridge will reconnect." && run_capture "Restart Full Mesh Stack" sudo "$SCRIPTS/restart-mesh-stack.sh"
        ;;
      restart_tailscale)
        confirm "Restart Tailscale? Your SSH session may briefly disconnect." && run_capture "Restart Tailscale" sudo "$SCRIPTS/restart-tailscale.sh"
        ;;
      backup) create_backup ;;
      list_backups) list_backups ;;
      docker_logs) docker_logs ;;
      reboot)
        confirm "Reboot this Pi now? This will disconnect SSH." && run_capture "Reboot Pi" sudo "$SCRIPTS/reboot-pi.sh"
        ;;
      exit) exit 0 ;;
    esac
  done
}

if [[ "$UI" != "whiptail" ]]; then
  show_message "MeshMonCompanion" "dialog is installed, but this menu is optimized for whiptail."
fi

main_menu
