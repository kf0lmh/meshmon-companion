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
        cmd = ["sudo", *cmd]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)


def health():
    result = run_script("healthcheck.sh", "--json", timeout=15, sudo=True)
    if result.returncode != 0:
        return {"overall": "critical", "errors": [result.stderr or result.stdout], "warnings": []}
    return json.loads(result.stdout)


def esc(value):
    import html
    return html.escape(str(value if value is not None else "Unknown"))


def page(body):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MeshMonCompanion</title>
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
            actions = """
              <form class='actions' method='post'>
                <button formaction='/action/restart-meshmonitor'>Restart MeshMonitor</button>
                <button formaction='/action/restart-serial-bridge'>Restart serial bridge</button>
                <button formaction='/action/restart-control-panel'>Restart control panel</button>
                <button formaction='/action/restart-mesh-stack' onclick="return confirm('Restart the full mesh stack?')">Restart full mesh stack</button>
                <button formaction='/action/restart-tailscale' onclick="return confirm('Restart Tailscale? This may interrupt remote access.')">Restart Tailscale</button>
                <button formaction='/action/reboot-pi' onclick="return confirm('Reboot this Pi now?')">Reboot Pi</button>
              </form>
            """
            body = f"<h1>MeshMonCompanion</h1><p class='status {esc(data.get('overall'))}'>{esc(data.get('overall')).title()}</p><pre>{esc(json.dumps(data, indent=2))}</pre><nav><a href='/backups'>Backups</a></nav>{actions}"
            self.send_html(page(body))
        elif path == "/api/status":
            self.send_json(health())
        elif path == "/backups":
            result = run_script("list-backups.sh", timeout=15, sudo=True)
            latest = latest_backup()
            download = "<p>No backup is available to download.</p>" if latest is None else "<p><a href='/backup/latest'>Download latest backup</a></p>"
            body = f"<h1>Backups</h1><form method='post' action='/backup/create'><label>Backup name <input name='label' maxlength='48' autocomplete='off'></label><button>Create Backup</button></form>{download}<pre>{esc(result.stdout or 'No backups found')}</pre><p><a href='/'>Back</a></p>"
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
    print(f"MeshMonCompanion listening on http://{BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
