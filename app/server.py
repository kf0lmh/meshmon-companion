#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(os.environ.get("MESHMON_COMPANION_ROOT", "/opt/meshmon-companion"))
SCRIPTS = ROOT / "scripts"
PORT = int(os.environ.get("MESHMON_COMPANION_PORT", "8090"))
BIND = os.environ.get("MESHMON_COMPANION_BIND", "127.0.0.1")


def run_script(name, *args, timeout=60, sudo=False):
    cmd = [str(SCRIPTS / name), *args]
    if sudo:
        cmd = ["sudo", "-n", *cmd]
    try:
        return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(cmd, 124, exc.stdout or "", exc.stderr or "Command timed out")


def health():
    result = run_script("healthcheck.sh", "--json", timeout=15, sudo=True)
    if result.returncode != 0 and "sudo:" in (result.stderr or ""):
        result = run_script("healthcheck.sh", "--json", timeout=15, sudo=False)
    if result.returncode != 0:
        return {"overall": "critical", "errors": [result.stderr or result.stdout], "warnings": []}
    return json.loads(result.stdout)


def esc(value):
    import html
    return html.escape(str(value if value is not None else "Unknown"))


def nested(data, *keys, default=None):
    value = data
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def service_label(value):
    return "Online" if value == "ok" or value == "active" else str(value or "Unknown").title()


def metric_card(label, value, tone=""):
    tone_class = f" {tone}" if tone else ""
    return f"<article class='metric{tone_class}'><span>{esc(label)}</span><strong>{esc(value)}</strong></article>"


def host_without_port(value):
    if not value:
        return ""
    return value.rsplit(":", 1)[0] if ":" in value and not value.startswith("[") else value


def default_fieldstation_link(request_host=""):
    host = host_without_port(request_host) or BIND
    if host in ("", "0.0.0.0", "::"):
        host = "127.0.0.1"
    return f"http://{host}:8091"


def fieldstation_link_for(data, request_host=""):
    fieldstation_url = nested(data, "services", "fieldstation_url", default="")
    if not fieldstation_url:
        return default_fieldstation_link(request_host)
    parsed = urllib.parse.urlparse(fieldstation_url)
    host = parsed.hostname or ""
    request_name = host_without_port(request_host)
    if host in ("127.0.0.1", "localhost") and request_name and request_name not in ("127.0.0.1", "localhost"):
        host = request_name
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme or 'http'}://{host}{port}"


def render_home(data, request_host=""):
    overall = str(data.get("overall", "unknown"))
    mesh_url = nested(data, "services", "meshmonitor_url", default="")
    mesh_link = mesh_url.rsplit("/api/status", 1)[0] if mesh_url else ""
    warnings = data.get("warnings") or []
    errors = data.get("errors") or []
    docker = nested(data, "services", "docker", default="unknown")
    control = nested(data, "services", "control_panel", default="unknown")
    mesh_api = nested(data, "services", "meshmonitor_api", default="unknown")
    fieldstation = nested(data, "services", "fieldstation", default="unknown")
    fieldstation_api = nested(data, "services", "fieldstation_api", default="unknown")
    fieldstation_link = fieldstation_link_for(data, request_host)
    serial = "Present" if nested(data, "serial", "present", default=False) else "Not detected"
    throttled = nested(data, "power", "throttled", default="")
    power = "Good" if throttled in ("", "throttled=0x0") else "Check power"
    disk = nested(data, "storage", "root_used_percent", default="Unknown")
    disk_label = f"{disk}% used" if isinstance(disk, (int, float)) else disk

    issue_items = ""
    if errors or warnings:
        items = "".join(f"<li>{esc(item)}</li>" for item in [*errors, *warnings])
        issue_items = f"<section class='notice'><h2>Needs Attention</h2><ul>{items}</ul></section>"

    fieldstation_button = f"<a class='button primary' href='{esc(fieldstation_link)}'>Open FieldStation</a>" if fieldstation_link else ""
    mesh_button = f"<a class='button' href='{esc(mesh_link)}'>Open Compatibility Dashboard</a>" if mesh_link else ""
    raw_status = esc(json.dumps(data, indent=2))

    return f"""
      <section class='hero'>
        <div>
          <p class='eyebrow'>FieldStation Host</p>
          <h1>{esc(nested(data, "system", "hostname", default="Node"))}</h1>
          <p class='subtle'>Local service and health monitor for this FieldStation host.</p>
        </div>
        <p class='status {esc(overall)}'>{esc(overall).title()}</p>
      </section>

      <section class='metrics'>
        {metric_card("Compatibility Dashboard", service_label(mesh_api), "good" if mesh_api == "ok" else "bad")}
        {metric_card("FieldStation", service_label(fieldstation_api), "good" if fieldstation_api == "ok" else "warn")}
        {metric_card("FieldStation Service", service_label(fieldstation), "good" if fieldstation == "active" else "warn")}
        {metric_card("Serial Node", serial, "good" if serial == "Present" else "warn")}
        {metric_card("Docker", service_label(docker), "good" if docker == "active" else "bad")}
        {metric_card("Control Panel", service_label(control), "good" if control == "active" else "bad")}
        {metric_card("Tailscale", nested(data, "network", "tailscale_ip", default="Not found"))}
        {metric_card("Temperature", nested(data, "power", "temperature", default="Unknown"))}
        {metric_card("Power", power, "good" if power == "Good" else "warn")}
        {metric_card("Disk", disk_label)}
      </section>

      {issue_items}

      <section class='actions-panel'>
        <div class='section-title'>
          <h2>Open</h2>
          <a href='/api/status'>Raw status</a>
        </div>
        <nav class='quick-links'>
          {fieldstation_button}
          {mesh_button}
          <a class='button' href='/backups'>Backups</a>
        </nav>
      </section>

      <section class='actions-panel'>
        <h2>Controls</h2>
        <form class='actions' method='post'>
          <button formaction='/action/restart-meshmonitor'>Restart Compatibility Dashboard</button>
          <button formaction='/action/restart-serial-bridge'>Restart Compatibility Serial Bridge</button>
          <button formaction='/action/restart-control-panel'>Restart Control Panel</button>
          <button formaction='/action/restart-mesh-stack' onclick="return confirm('Restart the compatibility stack?')">Restart Compatibility Stack</button>
          <button formaction='/action/restart-tailscale' onclick="return confirm('Restart Tailscale? This may interrupt remote access.')">Restart Tailscale</button>
          <button class='danger' formaction='/action/reboot-pi' onclick="return confirm('Reboot this Pi now?')">Reboot Pi</button>
        </form>
      </section>

      <details class='raw'>
        <summary>Technical Details</summary>
        <pre>{raw_status}</pre>
      </details>
    """


def page(body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FieldStation Host</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body><main>{body}</main></body>
</html>"""


def latest_backup():
    backup_dir = ROOT / "backups"
    candidates = sorted(backup_dir.glob("meshmon-companion-backup-*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


class Handler(BaseHTTPRequestHandler):
    def send_html(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value, status=200):
        data = json.dumps(value, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, path):
        self.send_response(303)
        self.send_header("Location", path)
        self.end_headers()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/":
            data = health()
            self.send_html(page(render_home(data, self.headers.get("Host", ""))))
        elif path == "/api/status":
            self.send_json(health())
        elif path == "/backups":
            result = run_script("list-backups.sh", timeout=15, sudo=True)
            latest = latest_backup()
            if latest is None:
                download = "<p>No backup is available to download.</p>"
            else:
                download = "<p><a href='/backup/latest'>Download latest backup</a></p>"
            body = (
                "<h1>Backups</h1>"
                "<form method='post' action='/backup/create'>"
                "<label>Backup name "
                "<input name='label' maxlength='48' autocomplete='off'>"
                "</label>"
                "<button>Create Backup</button>"
                "</form>"
                f"{download}"
                f"<pre>{esc(result.stdout or 'No backups found')}</pre>"
                "<p><a href='/'>Back</a></p>"
            )
            self.send_html(page(body))
        elif path == "/backup/latest":
            latest = latest_backup()
            if latest is None:
                self.send_html(page("<h1>No backup found</h1>"), 404)
                return
            data = latest.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/gzip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f"attachment; filename={latest.name}")
            self.end_headers()
            self.wfile.write(data)
        elif path == "/static/style.css":
            css = (ROOT / "app/static/style.css").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/css")
            self.send_header("Content-Length", str(len(css)))
            self.end_headers()
            self.wfile.write(css)
        else:
            self.send_html(page("<h1>Not found</h1>"), 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/backup/create":
            length = int(self.headers.get("Content-Length", "0") or "0")
            fields = urllib.parse.parse_qs(self.rfile.read(length).decode() if length else "")
            label = fields.get("label", [""])[0]
            run_script("backup-now.sh", "--label", label, timeout=180, sudo=True)
            self.redirect("/backups")
        elif path.startswith("/action/"):
            actions = {
                "/action/restart-meshmonitor": ("restart-meshmonitor.sh", 60),
                "/action/restart-serial-bridge": ("restart-serial-bridge.sh", 60),
                "/action/restart-mesh-stack": ("restart-mesh-stack.sh", 120),
                "/action/restart-control-panel": ("restart-control-panel.sh", 60),
                "/action/restart-tailscale": ("restart-tailscale.sh", 60),
                "/action/reboot-pi": ("reboot-pi.sh", 10),
            }
            if path not in actions:
                self.send_html(page("<h1>Not found</h1>"), 404)
                return
            script, timeout = actions[path]
            run_script(script, timeout=timeout, sudo=True)
            self.redirect("/")
        else:
            self.send_html(page("<h1>Not found</h1>"), 404)


def main():
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"FieldStation host control listening on http://{BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
