#!/usr/bin/env python3
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

if __package__ in (None, ""):
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fieldstation.adapter import NodeAdapter
from fieldstation.db import database_path
from fieldstation.render import page
from fieldstation.repository import FieldStationRepository

ROOT = Path(os.environ.get("FIELDSTATION_ROOT", "/opt/meshmon-companion"))
PORT = int(os.environ.get("FIELDSTATION_PORT", "8091"))
BIND = os.environ.get("FIELDSTATION_BIND", "127.0.0.1")
CONFIGURED_PORT = os.environ.get("FIELDSTATION_SERIAL_PORT", "")
OFFLINE_MAP_PATH = Path(os.environ.get("FIELDSTATION_OFFLINE_MAP_PATH", "/opt/meshmon-companion/data/fieldstation/maps"))


def esc(value):
    import html

    return html.escape(str(value if value is not None else ""))


def db_error_payload(exc):
    return {
        "app": "FieldStation",
        "status": "degraded",
        "database": {
            "path": str(database_path()),
            "exists": database_path().exists(),
            "ok": False,
            "error": str(exc),
        },
        "connection": NodeAdapter(CONFIGURED_PORT).status(),
        "counts": {"messages": 0, "known_nodes": 0},
    }


def vector_feature_detail(feature):
    kind = feature.get("kind")
    priority = int(feature.get("priority") or 0)
    if kind == "place":
        return "base"
    if kind in ("rail", "water", "waterway"):
        return "mid"
    if priority >= 6:
        return "base"
    if priority >= 4:
        return "mid"
    return "high"


def vector_feature_visible_at_detail(feature, detail):
    levels = {"base": 0, "mid": 1, "high": 2, "max": 3}
    requested = levels.get(detail, 0)
    required = levels.get(vector_feature_detail(feature), 0)
    return required <= requested


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def send_html(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, value, status=200, compact=False):
        if compact:
            data = json.dumps(value, separators=(",", ":")).encode()
        else:
            data = json.dumps(value, indent=2).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_static(self, relative_path, content_type):
        path = Path(__file__).resolve().parent / "static" / relative_path
        if not path.exists():
            self.send_html("<h1>Not found</h1>", 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_map_tile(self, query):
        try:
            z = int(query.get("z", [""])[0])
            x = int(query.get("x", [""])[0])
            y = int(query.get("y", [""])[0])
        except (TypeError, ValueError):
            self.send_html("<h1>Bad tile request</h1>", 400)
            return
        if z < 0 or x < 0 or y < 0:
            self.send_html("<h1>Bad tile request</h1>", 400)
            return
        path = OFFLINE_MAP_PATH / "tiles" / "osm" / str(z) / str(x) / f"{y}.png"
        try:
            resolved = path.resolve()
            root = OFFLINE_MAP_PATH.resolve()
        except OSError:
            self.send_html("<h1>Not found</h1>", 404)
            return
        if root not in resolved.parents or not resolved.exists():
            self.send_html("<h1>Not found</h1>", 404)
            return
        data = resolved.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(data)

    def send_map_vector(self, query):
        path = OFFLINE_MAP_PATH / "vector_map.json"
        try:
            resolved = path.resolve()
            root = OFFLINE_MAP_PATH.resolve()
        except OSError:
            self.send_json({"error": "Map vector package not found"}, 404)
            return
        if root not in resolved.parents or not resolved.exists():
            self.send_json({"error": "Map vector package not found"}, 404)
            return
        try:
            data = json.loads(resolved.read_text())
        except (OSError, json.JSONDecodeError):
            self.send_json({"error": "Map vector package is unreadable"}, 500)
            return
        detail = query.get("detail", ["base"])[0]
        data["features"] = [
            feature for feature in data.get("features", [])
            if vector_feature_visible_at_detail(feature, detail)
        ]
        self.send_json(data, compact=True)

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def repo(self):
        return FieldStationRepository()

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if path == "/":
            self.send_html(page())
        elif path == "/api/status":
            self.send_json(self.status_payload())
        elif path == "/api/channels":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"channels": repo.channels()})
        elif path == "/api/channel-profiles":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"channel_profiles": repo.channel_profiles()})
        elif path == "/api/messages":
            try:
                channel = query.get("channel", ["all"])[0]
                if channel == "all":
                    channel_index = None
                elif channel.isdigit():
                    channel_index = int(channel)
                else:
                    raise ValueError("channel must be all or an index between 0 and 7")
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"messages": repo.messages(channel_index=channel_index)})
            except ValueError as exc:
                self.send_json({"error": str(exc)}, 400)
        elif path == "/api/nodes":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"nodes": repo.nodes()})
        elif path == "/api/events":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"events": repo.recent_events()})
        elif path == "/api/map/status":
            repo = self.repo_or_503()
            if repo:
                self.send_json(repo.map_status())
        elif path == "/api/map/tile":
            self.send_map_tile(query)
        elif path == "/api/map/vector":
            self.send_map_vector(query)
        elif path == "/api/positions":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"positions": repo.positions()})
        elif path == "/api/waypoints":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"waypoints": repo.waypoints()})
        elif path == "/api/pending-waypoints":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"pending_waypoints": repo.pending_waypoints()})
        elif path == "/api/net-sessions":
            repo = self.repo_or_503()
            if repo:
                self.send_json({"net_sessions": repo.net_sessions(), "active_net_session": repo.active_net_session()})
        elif path == "/api/net-log-entries":
            repo = self.repo_or_503()
            if repo:
                session_id = query.get("session_id", [""])[0]
                self.send_json({"entries": repo.net_log_entries(session_id if session_id else None)})
        elif path == "/api/usb-writer/status":
            repo = self.repo_or_503()
            if repo:
                self.send_json(repo.usb_writer_status())
        elif path == "/static/fieldstation.css":
            self.send_static("fieldstation.css", "text/css")
        elif path == "/static/fieldstation.js":
            self.send_static("fieldstation.js", "application/javascript")
        else:
            self.send_html("<h1>Not found</h1>", 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        try:
            payload = self.read_json_body()
            if path == "/api/send-message":
                raw_channel = payload.get("channel_index", 0)
                if isinstance(raw_channel, int) or str(raw_channel).isdigit():
                    channel_index = int(raw_channel)
                else:
                    raise ValueError("channel_index must be between 0 and 7")
                body = str(payload.get("body", ""))
                repo = self.repo_or_503()
                if repo:
                    message = repo.create_outbound_message(channel_index, body)
                    adapter = self.adapter(repo)
                    send_result = adapter.send_text(channel_index, body)
                    repo.record_adapter_status(send_result["adapter_status"])
                    repo.record_raw_event(
                        "message.send_attempt",
                        send_result["detail"],
                        {
                            "message_id": message["id"],
                            "channel_index": channel_index,
                            "accepted": send_result["accepted"],
                            "adapter_state": send_result["adapter_status"]["state"],
                        },
                    )
                    if send_result["status"] != message["status"]:
                        message = repo.transition_message(message["id"], send_result["status"], send_result["detail"])
                    self.send_json(
                        {
                            "message": message,
                            "send_result": {
                                "accepted": send_result["accepted"],
                                "detail": send_result["detail"],
                                "adapter_state": send_result["adapter_status"]["state"],
                            },
                            "offline": send_result["adapter_status"]["offline"] or not send_result["accepted"],
                        },
                        201,
                    )
            elif path == "/api/tactical-callsigns":
                node_id = str(payload.get("node_id", "")).strip()
                if not node_id:
                    self.send_json({"error": "node_id is required"}, 400)
                    return
                tactical = str(payload.get("tactical_callsign", ""))
                repo = self.repo_or_503()
                if repo:
                    nodes = repo.set_tactical_callsign(node_id, tactical)
                    self.send_json({"nodes": nodes})
            elif path == "/api/message-cancel":
                message_id = payload.get("id")
                if message_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"message": repo.cancel_queued_message(message_id)})
            elif path == "/api/channel-profiles":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"channel_profile": repo.create_channel_profile(payload)}, 201)
            elif path == "/api/channel-profile-export":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.export_channel_profile(payload.get("id", 1), bool(payload.get("include_sensitive"))))
            elif path == "/api/channel-profile-import":
                repo = self.repo_or_503()
                if repo:
                    document = payload.get("document", payload)
                    self.send_json({"channel_profile": repo.import_channel_profile(document, bool(payload.get("overwrite")))}, 201)
            elif path == "/api/waypoints":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"waypoint": repo.create_waypoint(payload)}, 201)
            elif path == "/api/waypoint-update":
                waypoint_id = payload.get("id")
                if waypoint_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"waypoint": repo.update_waypoint(waypoint_id, payload)})
            elif path == "/api/waypoint-share":
                waypoint_id = payload.get("id")
                channel_index = payload.get("channel_index")
                if waypoint_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                if channel_index is None:
                    self.send_json({"error": "channel_index is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.share_waypoint(waypoint_id, int(channel_index)), 201)
            elif path == "/api/pending-waypoint-parse":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"pending_waypoint": repo.create_pending_waypoint_from_message(payload)}, 201)
            elif path == "/api/pending-waypoint-save":
                pending_id = payload.get("id")
                if pending_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.save_pending_waypoint(pending_id))
            elif path == "/api/pending-waypoint-ignore":
                pending_id = payload.get("id")
                if pending_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"pending_waypoint": repo.ignore_pending_waypoint(pending_id)})
            elif path == "/api/net-sessions":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"net_session": repo.create_net_session(payload)}, 201)
            elif path == "/api/net-session-close":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"net_session": repo.close_net_session(payload.get("id"), str(payload.get("notes", "")))})
            elif path == "/api/net-log-entries":
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"entry": repo.add_net_log_entry(payload)}, 201)
            elif path == "/api/net-log-entry-update":
                entry_id = payload.get("id")
                if entry_id is None:
                    self.send_json({"error": "id is required"}, 400)
                    return
                repo = self.repo_or_503()
                if repo:
                    self.send_json({"entry": repo.update_net_log_entry(entry_id, payload)})
            elif path == "/api/ics309-export":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.export_net_log("ics309", str(payload.get("format", "csv")), payload.get("session_id")))
            elif path == "/api/ics214-export":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.export_net_log("ics214", str(payload.get("format", "csv")), payload.get("session_id")))
            elif path == "/api/usb-writer/preview":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.usb_writer_preview(payload))
            elif path == "/api/usb-writer/create":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.usb_writer_create(payload), 201)
            elif path == "/api/usb-writer/verify":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.usb_writer_verify(payload))
            elif path == "/api/starter-bundle/preview":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.starter_bundle_preview(payload))
            elif path == "/api/starter-bundle/export":
                repo = self.repo_or_503()
                if repo:
                    self.send_json(repo.starter_bundle_export(payload))
            elif path == "/api/starter-bundle/import-preview":
                repo = self.repo_or_503()
                if repo:
                    document = payload.get("document", payload)
                    self.send_json(repo.starter_bundle_import_preview(document))
            elif path == "/api/starter-bundle/import":
                repo = self.repo_or_503()
                if repo:
                    document = payload.get("document", payload)
                    self.send_json(repo.starter_bundle_import(document, bool(payload.get("confirm"))))
            else:
                self.send_html("<h1>Not found</h1>", 404)
        except KeyError as exc:
            self.send_json({"error": str(exc).strip("'")}, 404)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, 400)
        except json.JSONDecodeError:
            self.send_json({"error": "Invalid JSON body"}, 400)

    def status_payload(self):
        try:
            repo = self.repo()
            adapter = self.adapter(repo)
            adapter_status = adapter.status()
            repo.record_adapter_status(adapter_status)
            repo.upsert_known_node(adapter_status["local_node"])
            for node in adapter_status.get("known_nodes", []):
                if node.get("node_id") != adapter_status["local_node"].get("node_id"):
                    repo.upsert_known_node(node)
            counts = repo.status_counts()
            nodes = repo.nodes()
        except Exception as exc:
            return db_error_payload(exc)
        local = next((node for node in nodes if node["is_local"]), None)
        if local:
            adapter_status["local_node"]["tactical_callsign"] = local.get("tactical_callsign") or ""
            adapter_status["local_node"]["display_name"] = local["display_name"]
        return {
            "app": "FieldStation",
            "status": "ok",
            "database": {"path": str(database_path()), "exists": database_path().exists(), "ok": True},
            "connection": adapter_status,
            "adapter_health": {
                "state": adapter_status["state"],
                "reason": adapter_status.get("reason"),
                "adapter_state": adapter_status["state"],
                "adapter_reason": adapter_status.get("reason"),
                "live_mode_available": adapter_status.get("live_mode_available", False),
                "read_only_adapter_available": adapter_status.get("read_only_live_available", False),
                "telemetry_live": adapter_status.get("telemetry_live", False),
                "tx_available": adapter_status.get("tx_available", False),
                "message_receipts_available": adapter_status.get("message_receipts_available", False),
                "read_only_live_available": adapter_status.get("read_only_live_available", False),
                "configured_serial_path": CONFIGURED_PORT or None,
                "selected_port": adapter_status.get("selected_port"),
                "selected_serial_path": adapter_status.get("selected_port"),
                "last_successful_read_at": adapter_status.get("last_successful_read_at"),
                "last_successful_read": adapter_status.get("last_successful_read_at"),
                "last_error": adapter_status.get("last_error"),
            },
            "counts": counts,
        }

    def adapter(self, repo):
        return NodeAdapter(CONFIGURED_PORT, previous_status=repo.get_setting("adapter.status", {}))

    def repo_or_503(self):
        try:
            return self.repo()
        except Exception as exc:
            self.send_json(db_error_payload(exc), 503)
            return None


def main():
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"FieldStation listening on http://{BIND}:{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
