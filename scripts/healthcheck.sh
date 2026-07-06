#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--json" ]] || { echo "Usage: $0 --json" >&2; exit 2; }

python3 - <<'PY'
import json, os, shutil, socket, subprocess, urllib.request

def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except Exception as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))

def out(cmd):
    return run(cmd).stdout.strip()

errors, warnings = [], []
docker = out(["systemctl", "is-active", "docker"])
control = out(["systemctl", "is-active", "meshmon-companion"])
ts_ip = out(["bash", "-lc", "command -v tailscale >/dev/null && tailscale ip -4 | head -1 || true"])
serial_present = any(os.path.exists(p) for p in ["/dev/serial/by-id"] + [f"/dev/ttyACM{i}" for i in range(4)] + [f"/dev/ttyUSB{i}" for i in range(4)])
api = "unknown"
try:
    with urllib.request.urlopen("http://127.0.0.1:8080/api/status", timeout=4) as resp:
        data = json.loads(resp.read().decode())
    api = "ok" if data.get("status") == "ok" else "failed"
except Exception:
    api = "failed"

if docker != "active": errors.append("Docker is not active")
if control != "active": errors.append("MeshMonCompanion service is not active")
if not serial_present: warnings.append("No serial device detected")
if api != "ok": warnings.append("MeshMonitor API is not responding on localhost:8080")

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
    "errors": errors,
    "warnings": warnings,
    "system": {"hostname": socket.gethostname(), "uptime": out(["uptime", "-p"]), "load": out(["bash", "-lc", "cut -d' ' -f1-3 /proc/loadavg"])},
    "network": {"tailscale_ip": ts_ip or None},
    "services": {"docker": docker, "control_panel": control, "meshmonitor_api": api},
    "serial": {"present": serial_present},
    "power": {"temperature": temp, "throttled": throttled},
    "storage": {"root_used_percent": disk_pct},
}, indent=2))
PY
