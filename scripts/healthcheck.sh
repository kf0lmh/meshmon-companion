#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--json" ]] || { echo "Usage: $0 --json" >&2; exit 2; }

python3 - <<'PY'
import json, os, shutil, socket, subprocess, urllib.request

CONFIG = os.environ.get("MESHMON_COMPANION_CONFIG", "/etc/meshmon-companion/config.yaml")

def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))

def out(cmd):
    return run(cmd).stdout.strip()

def safe_device_path(path):
    if not path:
        return None
    if "/dev/serial/by-id/" in path:
        return "/dev/serial/by-id/REDACTED"
    return path

def read_config():
    values = {
        "control_bind": "127.0.0.1",
        "meshmonitor_port": "8080",
        "fieldstation_bind": "",
        "fieldstation_port": "8091",
        "fieldstation_enabled": "true",
        "fieldstation_database": "/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3",
        "fieldstation_read_timeout_seconds": "12",
        "compatibility_optional_stack_enabled": "false",
        "serial_connection_type": "usb",
        "serial_device": "",
        "serial_tcp_host": "",
        "serial_tcp_port": "4403",
    }
    section = None
    try:
        with open(CONFIG, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = raw.rstrip()
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not raw.startswith((" ", "\t")) and stripped.endswith(":"):
                    section = stripped[:-1]
                    continue
                if not raw.startswith((" ", "\t")) and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    if key == "control_bind":
                        values["control_bind"] = value.strip().strip('"')
                    section = None
                    continue
                if section == "ports" and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    if key == "meshmonitor":
                        values["meshmonitor_port"] = value.strip().strip('"')
                    elif key == "fieldstation":
                        values["fieldstation_port"] = value.strip().strip('"')
                elif section == "fieldstation" and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    value = value.strip().strip('"')
                    if key == "bind":
                        values["fieldstation_bind"] = value
                    elif key == "port":
                        values["fieldstation_port"] = value
                    elif key == "enabled":
                        values["fieldstation_enabled"] = value
                    elif key == "database":
                        values["fieldstation_database"] = value
                    elif key == "read_timeout_seconds":
                        values["fieldstation_read_timeout_seconds"] = value
                elif section == "serial" and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    value = value.strip().strip('"')
                    if key == "connection_type":
                        values["serial_connection_type"] = value
                    elif key == "device":
                        values["serial_device"] = value
                    elif key == "tcp_host":
                        values["serial_tcp_host"] = value
                    elif key == "tcp_port":
                        values["serial_tcp_port"] = value
                elif section == "compatibility" and ":" in stripped:
                    key, value = stripped.split(":", 1)
                    value = value.strip().strip('"')
                    if key == "optional_stack_enabled":
                        values["compatibility_optional_stack_enabled"] = value
    except FileNotFoundError:
        pass
    return values

errors, warnings = [], []
docker = out(["systemctl", "is-active", "docker"])
control = out(["systemctl", "is-active", "meshmon-companion"])
fieldstation_service = out(["systemctl", "is-active", "fieldstation"])
ts_ip = out(["bash", "-lc", "command -v tailscale >/dev/null && tailscale ip -4 | head -1 || true"])
serial_present = any(os.path.exists(p) for p in ["/dev/serial/by-id"] + [f"/dev/ttyACM{i}" for i in range(4)] + [f"/dev/ttyUSB{i}" for i in range(4)])
config = read_config()
compatibility_enabled = str(config["compatibility_optional_stack_enabled"]).lower() in ("true", "1", "yes", "on")
install_mode = "compatibility-enabled" if compatibility_enabled else "fieldstation-only"
optional_compatibility_stack_present = docker == "active"
mesh_host = config["control_bind"]
if mesh_host in ("", "0.0.0.0", "::"):
    mesh_host = "127.0.0.1"
mesh_url = f"http://{mesh_host}:{config['meshmonitor_port']}/api/status"
api = "unknown"
try:
    with urllib.request.urlopen(mesh_url, timeout=4) as resp:
        data = json.loads(resp.read().decode())
    api = "ok" if data.get("status") == "ok" else "failed"
except Exception:
    api = "failed"

fieldstation_enabled = str(config["fieldstation_enabled"]).lower() not in ("false", "0", "no")
fieldstation_host = config["fieldstation_bind"] or config["control_bind"]
if fieldstation_host in ("", "0.0.0.0", "::"):
    fieldstation_host = "127.0.0.1"
fieldstation_url = f"http://{fieldstation_host}:{config['fieldstation_port']}/api/status"
try:
    fieldstation_api_timeout = max(6, int(config["fieldstation_read_timeout_seconds"]) + 4)
except ValueError:
    fieldstation_api_timeout = 16
fieldstation_api = "disabled" if not fieldstation_enabled else "unknown"
fieldstation_db = config["fieldstation_database"]
fieldstation_db_exists = os.path.exists(fieldstation_db)
fieldstation_port_open = False
fieldstation_adapter_state = None
fieldstation_adapter_reason = None
fieldstation_adapter_error = None
fieldstation_live_mode_available = None
fieldstation_read_only_live_available = None
fieldstation_telemetry_live = None
fieldstation_tx_available = None
fieldstation_message_receipts_available = None
fieldstation_database_ok = None
fieldstation_selected_serial_path = None
fieldstation_meshtastic_dependency_available = None
fieldstation_meshtastic_version = None
fieldstation_last_successful_read = None
fieldstation_last_error = None
if fieldstation_enabled:
    try:
        with socket.create_connection((fieldstation_host, int(config["fieldstation_port"])), timeout=2):
            fieldstation_port_open = True
    except Exception:
        fieldstation_port_open = False
    try:
        with urllib.request.urlopen(fieldstation_url, timeout=fieldstation_api_timeout) as resp:
            data = json.loads(resp.read().decode())
        fieldstation_api = data.get("status") if data.get("status") in ("ok", "degraded") else "failed"
        connection = data.get("connection") or {}
        adapter_health = data.get("adapter_health") or {}
        fieldstation_adapter_state = connection.get("state")
        fieldstation_adapter_reason = connection.get("reason")
        fieldstation_adapter_error = connection.get("error")
        fieldstation_selected_serial_path = adapter_health.get("selected_port", connection.get("selected_port"))
        fieldstation_live_mode_available = adapter_health.get("live_mode_available", connection.get("live_mode_available"))
        fieldstation_read_only_live_available = adapter_health.get("read_only_live_available", connection.get("read_only_live_available"))
        fieldstation_telemetry_live = adapter_health.get("telemetry_live", connection.get("telemetry_live"))
        fieldstation_tx_available = adapter_health.get("tx_available", connection.get("tx_available"))
        fieldstation_message_receipts_available = adapter_health.get("message_receipts_available", connection.get("message_receipts_available"))
        dependency = connection.get("dependency") or {}
        fieldstation_meshtastic_dependency_available = dependency.get("available")
        fieldstation_meshtastic_version = dependency.get("version")
        fieldstation_last_successful_read = adapter_health.get("last_successful_read_at", connection.get("last_successful_read_at"))
        fieldstation_last_error = adapter_health.get("last_error", connection.get("last_error"))
        fieldstation_database_ok = (data.get("database") or {}).get("ok")
    except Exception:
        fieldstation_api = "failed"

if compatibility_enabled and docker != "active": warnings.append("Optional compatibility Docker service is not active")
if control != "active": warnings.append("FieldStation host control service is not active")
if fieldstation_enabled and fieldstation_service != "active": errors.append("FieldStation service is not active")
if not serial_present: warnings.append("No serial device detected")
if compatibility_enabled and api != "ok": warnings.append(f"Optional compatibility dashboard API is not responding at {mesh_url}")
if fieldstation_enabled and fieldstation_api == "failed": errors.append(f"FieldStation API is not responding at {fieldstation_url}")
if fieldstation_enabled and fieldstation_database_ok is False: errors.append("FieldStation database is not healthy")

disk = shutil.disk_usage("/")
disk_pct = round((disk.used / disk.total) * 100, 1)
if disk_pct >= 95: errors.append("Root disk is nearly full")
elif disk_pct >= 90: warnings.append("Root disk usage is high")

temp = out(["bash", "-lc", "command -v vcgencmd >/dev/null && vcgencmd measure_temp || true"])
throttled = out(["bash", "-lc", "command -v vcgencmd >/dev/null && vcgencmd get_throttled || true"])
if throttled and throttled != "throttled=0x0": errors.append("Power throttling/undervoltage detected")

overall = "critical" if errors else ("warning" if warnings else "healthy")
print(json.dumps({
    "overall": overall,
    "install_mode": install_mode,
    "errors": errors,
    "warnings": warnings,
    "system": {"hostname": socket.gethostname(), "uptime": out(["uptime", "-p"]), "load": out(["bash", "-lc", "cut -d' ' -f1-3 /proc/loadavg"])},
    "network": {"tailscale_ip": ts_ip or None},
    "services": {
        "docker": docker,
        "control_panel": control,
        "meshmonitor_api": api,
        "meshmonitor_url": mesh_url,
        "fieldstation": fieldstation_service,
        "fieldstation_api": fieldstation_api,
        "fieldstation_url": fieldstation_url,
    },
    "serial": {"present": serial_present},
    "fieldstation": {
        "enabled": fieldstation_enabled,
        "install_mode": install_mode,
        "fieldstation_service_ok": fieldstation_service == "active",
        "bind": config["fieldstation_bind"] or config["control_bind"],
        "port": config["fieldstation_port"],
        "port_open": fieldstation_port_open,
        "fieldstation_api_ok": fieldstation_api in ("ok", "degraded"),
        "fieldstation_db_ok": fieldstation_database_ok,
        "database": fieldstation_db,
        "database_exists": fieldstation_db_exists,
        "database_ok": fieldstation_database_ok,
        "read_only_adapter_available": bool(fieldstation_read_only_live_available),
        "adapter_state": fieldstation_adapter_state,
        "adapter_reason": fieldstation_adapter_reason,
        "adapter_error": fieldstation_adapter_error,
        "adapter_transport": config["serial_connection_type"],
        "configured_node_host": config["serial_tcp_host"] if config["serial_connection_type"] == "tcp" else None,
        "configured_node_port": config["serial_tcp_port"] if config["serial_connection_type"] == "tcp" else None,
        "configured_serial_path": safe_device_path(config["serial_device"]),
        "selected_serial_path": safe_device_path(fieldstation_selected_serial_path),
        "serial_access_rw": os.access(fieldstation_selected_serial_path or config["serial_device"], os.R_OK | os.W_OK) if (fieldstation_selected_serial_path or config["serial_device"]) else False,
        "meshtastic_dependency_available": fieldstation_meshtastic_dependency_available,
        "meshtastic_version": fieldstation_meshtastic_version,
        "live_mode_available": fieldstation_live_mode_available,
        "read_only_live_available": fieldstation_read_only_live_available,
        "telemetry_live": fieldstation_telemetry_live,
        "tx_available": fieldstation_tx_available,
        "message_receipts_available": fieldstation_message_receipts_available,
        "last_successful_read": fieldstation_last_successful_read,
        "last_error": fieldstation_last_error,
    },
    "compatibility": {
        "optional_stack_enabled": compatibility_enabled,
        "install_mode": install_mode,
        "optional_compatibility_stack_enabled": compatibility_enabled,
        "optional_compatibility_stack_present": optional_compatibility_stack_present,
        "optional_compatibility_stack_ok": (api == "ok") if compatibility_enabled else None,
        "dashboard_api": api if compatibility_enabled else "disabled",
        "dashboard_url": mesh_url if compatibility_enabled else None,
    },
    "power": {"temperature": temp, "throttled": throttled},
    "storage": {"root_used_percent": disk_pct},
}, indent=2))
PY
