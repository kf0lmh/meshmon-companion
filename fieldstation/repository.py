import json
import os
from pathlib import Path
from datetime import datetime, timezone

from .channel_profile import channel_label
from .db import connect, init_db
from .models import MESSAGE_STATUSES, MESSAGE_STATUS_TONES
from .netlog import ENTRY_TYPES, EXPORT_FORMATS, EXPORT_TYPES, build_export, clean_entry_payload, clean_session_payload, export_filename
from .profile_io import profile_document, validate_profile_document
from .starter_bundle import DEFAULT_CATEGORIES, EXCLUDED_BY_DEFAULT, import_preview, metadata, normalize_categories
from .usb_writer import create_package, looks_removable, validate_target, verify_package
from .waypoints import LINCOLN_COUNTY_BOUNDS, WAYPOINT_STATUSES, WAYPOINT_TYPES, clean_waypoint_payload, parse_waypoint_message, waypoint_text


class FieldStationRepository:
    def __init__(self, db_path=None):
        self.db_path = db_path
        init_db(db_path)

    def _connect(self):
        return connect(self.db_path)

    def channels(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT channel_index, name, role, is_private
                FROM channels
                WHERE profile_id = 1
                ORDER BY channel_index
                """
            ).fetchall()
        return [
            {
                "index": row["channel_index"],
                "name": row["name"],
                "label": channel_label({"index": row["channel_index"], "name": row["name"]}),
                "role": row["role"],
                "is_private": bool(row["is_private"]),
            }
            for row in rows
        ]

    def channel_name(self, channel_index):
        if channel_index < 0 or channel_index > 7:
            raise ValueError("channel_index must be between 0 and 7")
        for channel in self.channels():
            if channel["index"] == channel_index:
                return channel["name"]
        raise ValueError(f"Channel {channel_index} is not configured")

    def channel_profiles(self):
        with self._connect() as conn:
            profiles = conn.execute(
                """
                SELECT id, name, description, created_at, updated_at
                FROM channel_profiles
                ORDER BY id
                """
            ).fetchall()
            channels = conn.execute(
                """
                SELECT profile_id, channel_index, name, role, is_private
                FROM channels
                ORDER BY profile_id, channel_index
                """
            ).fetchall()
        grouped = {}
        for row in channels:
            grouped.setdefault(row["profile_id"], []).append(
                {
                    "index": row["channel_index"],
                    "name": row["name"],
                    "label": channel_label({"index": row["channel_index"], "name": row["name"]}),
                    "role": row["role"],
                    "is_private": bool(row["is_private"]),
                }
            )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "channels": grouped.get(row["id"], []),
                "hardware_apply_supported": False,
            }
            for row in profiles
        ]

    def channel_profile(self, profile_id):
        for profile in self.channel_profiles():
            if int(profile["id"]) == int(profile_id):
                return profile
        return None

    def create_channel_profile(self, payload):
        document = {
            "schema": "fieldstation.channel_profile",
            "schema_version": 1,
            "profile": {
                "name": payload.get("name"),
                "description": payload.get("description", ""),
                "channels": payload.get("channels", []),
            },
        }
        data = validate_profile_document(document)
        if self._profile_name_exists(data["name"]):
            raise ValueError("A channel profile with this name already exists")
        return self._insert_channel_profile(data)

    def export_channel_profile(self, profile_id=1, include_sensitive=False):
        profile = self.channel_profile(profile_id)
        if not profile:
            raise KeyError("Channel profile not found")
        return profile_document(profile, include_sensitive=include_sensitive)

    def import_channel_profile(self, document, overwrite=False):
        data = validate_profile_document(document)
        exists = self._profile_name_exists(data["name"])
        if exists and not overwrite:
            raise ValueError("Channel profile already exists; choose a different name or set overwrite")
        if exists and overwrite:
            self._delete_profile_by_name(data["name"])
        return self._insert_channel_profile(data)

    def _profile_name_exists(self, name):
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM channel_profiles WHERE name = ?", (name,)).fetchone()
        return bool(row)

    def _delete_profile_by_name(self, name):
        with self._connect() as conn:
            conn.execute("DELETE FROM channel_profiles WHERE name = ?", (name,))

    def _insert_channel_profile(self, data):
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO channel_profiles (name, description)
                VALUES (?, ?)
                """,
                (data["name"], data["description"]),
            )
            profile_id = cursor.lastrowid
            for channel in data["channels"]:
                conn.execute(
                    """
                    INSERT INTO channels (profile_id, channel_index, name, role, is_private)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (profile_id, channel["index"], channel["name"], channel["role"], 1 if channel["is_private"] else 0),
                )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('channel_profile.saved', ?, ?)
                """,
                (f"Saved channel profile {data['name']}", json.dumps({"profile_id": profile_id})),
            )
        return self.channel_profile(profile_id)

    def messages(self, channel_index=None, limit=200):
        if channel_index is not None and (channel_index < 0 or channel_index > 7):
            raise ValueError("channel must be all or an index between 0 and 7")
        params = []
        where = ""
        if channel_index is not None:
            where = "WHERE m.channel_index = ?"
            params.append(channel_index)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                  m.id, m.timestamp, m.sender_node_id, m.sender_name, m.direction,
                  m.channel_index, m.channel_name, m.body, m.status, m.is_sample,
                  t.tactical_callsign
                FROM messages m
                LEFT JOIN node_tactical_callsigns t ON t.node_id = m.sender_node_id
                {where}
                ORDER BY m.id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [self._message_dict(row) for row in reversed(rows)]

    def create_outbound_message(self, channel_index, body):
        body = body.strip()
        if not body:
            raise ValueError("Message body is required")
        channel_name = self.channel_name(channel_index)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO messages
                  (sender_node_id, sender_name, direction, channel_index, channel_name, body, status)
                VALUES ('!fieldstation-local', 'Local operator', 'outbound', ?, ?, ?, 'queued_local')
                """,
                (channel_index, channel_name, body),
            )
            message_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO message_status_events (message_id, status, detail)
                VALUES (?, 'queued_local', 'Message is stored locally until a node adapter accepts it.')
                """,
                (message_id,),
            )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('message.queued', ?, ?)
                """,
                (
                    f"Queued local message on {channel_index} {channel_name}",
                    json.dumps({"message_id": message_id, "channel_index": channel_index}),
                ),
            )
        message = self.message(message_id)
        self.auto_log(
            "message sent",
            f"Queued local message on {message['channel_label']}: {body}",
            {
                "from_node_id": message["sender_node_id"],
                "from_node_name": message["sender_name"],
                "from_tactical_callsign": message["sender_tactical_callsign"] or "",
                "channel_index": channel_index,
                "channel_name": channel_name,
                "related_message_id": message_id,
                "source": "automatic",
            },
        )
        return message

    def transition_message(self, message_id, status, detail=""):
        if status not in MESSAGE_STATUSES:
            raise ValueError(f"Unknown message status: {status}")
        with self._connect() as conn:
            conn.execute("UPDATE messages SET status = ? WHERE id = ?", (status, message_id))
            conn.execute(
                """
                INSERT INTO message_status_events (message_id, status, detail)
                VALUES (?, ?, ?)
                """,
                (message_id, status, detail),
            )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('message.status', ?, ?)
                """,
                (
                    f"Message {message_id} changed to {MESSAGE_STATUSES[status]}",
                    json.dumps({"message_id": message_id, "status": status, "detail": detail}),
                ),
            )
        return self.message(message_id)

    def cancel_queued_message(self, message_id):
        message = self.message(message_id)
        if not message:
            raise KeyError("Message not found")
        if message["status"] not in ("queued_local", "retry_available"):
            raise ValueError("Only queued or retry-available messages can be removed from the queue")
        return self.transition_message(message_id, "canceled", "Removed from the local send queue by the operator.")

    def message_status_events(self, message_id):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, status, detail, created_at
                FROM message_status_events
                WHERE message_id = ?
                ORDER BY id
                """,
                (message_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "status": row["status"],
                "status_label": MESSAGE_STATUSES.get(row["status"], row["status"]),
                "detail": row["detail"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def message(self, message_id):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                  m.id, m.timestamp, m.sender_node_id, m.sender_name, m.direction,
                  m.channel_index, m.channel_name, m.body, m.status, m.is_sample,
                  t.tactical_callsign
                FROM messages m
                LEFT JOIN node_tactical_callsigns t ON t.node_id = m.sender_node_id
                WHERE m.id = ?
                """,
                (message_id,),
            ).fetchone()
        return self._message_dict(row) if row else None

    def nodes(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT n.*, t.tactical_callsign
                FROM known_nodes n
                LEFT JOIN node_tactical_callsigns t ON t.node_id = n.node_id
                ORDER BY n.is_local DESC, COALESCE(n.last_heard_at, n.created_at) DESC, n.node_id
                """
            ).fetchall()
        nodes = [self._node_dict(row) for row in rows]
        if any(node["is_local"] and node["node_id"] != "!fieldstation-local" for node in nodes):
            nodes = [node for node in nodes if node["node_id"] != "!fieldstation-local"]
        return nodes

    def set_tactical_callsign(self, node_id, tactical_callsign):
        tactical_callsign = tactical_callsign.strip()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO known_nodes (node_id, node_name)
                VALUES (?, ?)
                """,
                (node_id, node_id),
            )
            if tactical_callsign:
                conn.execute(
                    """
                    INSERT INTO node_tactical_callsigns (node_id, tactical_callsign, updated_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(node_id) DO UPDATE SET
                      tactical_callsign = excluded.tactical_callsign,
                      updated_at = CURRENT_TIMESTAMP
                    """,
                    (node_id, tactical_callsign),
                )
                summary = f"Set tactical callsign for {node_id}"
            else:
                conn.execute("DELETE FROM node_tactical_callsigns WHERE node_id = ?", (node_id,))
                summary = f"Cleared tactical callsign for {node_id}"
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('node.callsign.updated', ?, ?)
                """,
                (summary, json.dumps({"node_id": node_id})),
            )
        return self.nodes()

    def upsert_known_node(self, node):
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            raise ValueError("node_id is required")
        fields = {
            "node_id": node_id,
            "node_name": node.get("node_name") or node_id,
            "short_name": node.get("short_name") or "",
            "is_local": 1 if node.get("is_local") else 0,
            "is_sample": 1 if node.get("is_sample") else 0,
            "firmware_version": node.get("firmware_version"),
            "app_version": node.get("app_version"),
            "role": node.get("role"),
            "region": node.get("region"),
            "modem_preset": node.get("modem_preset"),
            "current_channel": node.get("current_channel"),
            "battery_level": node.get("battery_level"),
            "voltage": node.get("voltage"),
            "charging_state": node.get("charging_state"),
            "gps_status": node.get("gps_status"),
            "latitude": node.get("latitude"),
            "longitude": node.get("longitude"),
            "rssi": node.get("rssi"),
            "snr": node.get("snr"),
            "last_heard_at": node.get("last_heard_at"),
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO known_nodes (
                  node_id, node_name, short_name, is_local, is_sample,
                  firmware_version, app_version, role, region, modem_preset,
                  current_channel, battery_level, voltage, charging_state,
                  gps_status, latitude, longitude, rssi, snr, last_heard_at,
                  updated_at
                )
                VALUES (
                  :node_id, :node_name, :short_name, :is_local, :is_sample,
                  :firmware_version, :app_version, :role, :region, :modem_preset,
                  :current_channel, :battery_level, :voltage, :charging_state,
                  :gps_status, :latitude, :longitude, :rssi, :snr, :last_heard_at,
                  CURRENT_TIMESTAMP
                )
                ON CONFLICT(node_id) DO UPDATE SET
                  node_name = excluded.node_name,
                  short_name = excluded.short_name,
                  is_local = excluded.is_local,
                  is_sample = excluded.is_sample,
                  firmware_version = COALESCE(excluded.firmware_version, known_nodes.firmware_version),
                  app_version = COALESCE(excluded.app_version, known_nodes.app_version),
                  role = COALESCE(excluded.role, known_nodes.role),
                  region = COALESCE(excluded.region, known_nodes.region),
                  modem_preset = COALESCE(excluded.modem_preset, known_nodes.modem_preset),
                  current_channel = COALESCE(excluded.current_channel, known_nodes.current_channel),
                  battery_level = COALESCE(excluded.battery_level, known_nodes.battery_level),
                  voltage = COALESCE(excluded.voltage, known_nodes.voltage),
                  charging_state = COALESCE(excluded.charging_state, known_nodes.charging_state),
                  gps_status = COALESCE(excluded.gps_status, known_nodes.gps_status),
                  latitude = COALESCE(excluded.latitude, known_nodes.latitude),
                  longitude = COALESCE(excluded.longitude, known_nodes.longitude),
                  rssi = COALESCE(excluded.rssi, known_nodes.rssi),
                  snr = COALESCE(excluded.snr, known_nodes.snr),
                  last_heard_at = COALESCE(excluded.last_heard_at, known_nodes.last_heard_at),
                  updated_at = CURRENT_TIMESTAMP
                """,
                fields,
            )
        return self.node(node_id)

    def node(self, node_id):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT n.*, t.tactical_callsign
                FROM known_nodes n
                LEFT JOIN node_tactical_callsigns t ON t.node_id = n.node_id
                WHERE n.node_id = ?
                """,
                (node_id,),
            ).fetchone()
        return self._node_dict(row) if row else None

    def map_status(self):
        map_path = Path(os.environ.get("FIELDSTATION_OFFLINE_MAP_PATH", "/opt/meshmon-companion/data/fieldstation/maps"))
        manifest = self._offline_map_manifest(map_path)
        bounds = manifest.get("bounds") if manifest else LINCOLN_COUNTY_BOUNDS
        region = manifest.get("display_name") or manifest.get("location") if manifest else "Lincoln County, Missouri"
        tiles_downloaded = int(manifest.get("tiles_downloaded", 0) or 0) + int(manifest.get("tiles_reused", 0) or 0) if manifest else 0
        return {
            "region": region,
            "mode": "offline_tiles" if tiles_downloaded else "offline_placeholder",
            "tiles": "local_raster" if tiles_downloaded else "placeholder",
            "asset_path": str(map_path),
            "internet_required": False,
            "live_node_positions": False,
            "bounds": bounds,
            "map_package": manifest,
            "waypoint_types": list(WAYPOINT_TYPES),
            "waypoint_statuses": list(WAYPOINT_STATUSES),
            "detail": "Offline local map package is installed." if tiles_downloaded else "Offline placeholder map surface. Add/download a local map package for a basemap.",
        }

    def _offline_map_manifest(self, map_path):
        manifest_path = map_path / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        return data

    def positions(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT n.*, t.tactical_callsign
                FROM known_nodes n
                LEFT JOIN node_tactical_callsigns t ON t.node_id = n.node_id
                WHERE n.latitude IS NOT NULL AND n.longitude IS NOT NULL
                ORDER BY n.is_local DESC, COALESCE(n.last_heard_at, n.created_at) DESC, n.node_id
                """
            ).fetchall()
        return [self._position_dict(row) for row in rows]

    def waypoints(self, include_deleted=False):
        where = "" if include_deleted else "WHERE status != 'deleted'"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM waypoints
                {where}
                ORDER BY
                  CASE status
                    WHEN 'active' THEN 0
                    WHEN 'stale' THEN 1
                    WHEN 'resolved' THEN 2
                    ELSE 3
                  END,
                  updated_at DESC,
                  id DESC
                """
            ).fetchall()
        return [self._waypoint_dict(row) for row in rows]

    def waypoint(self, waypoint_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM waypoints WHERE id = ?", (int(waypoint_id),)).fetchone()
        return self._waypoint_dict(row) if row else None

    def create_waypoint(self, payload):
        data = clean_waypoint_payload(payload)
        local = self.node("!fieldstation-local") or {}
        created_by_node_id = str(payload.get("created_by_node_id") or local.get("node_id") or "!fieldstation-local")
        created_by_node_name = str(payload.get("created_by_node_name") or local.get("node_name") or "Local operator")
        created_by_tactical = str(payload.get("created_by_tactical_callsign") or local.get("tactical_callsign") or "")
        source = str(payload.get("source") or "manual").strip()[:32] or "manual"
        raw_payload = payload.get("raw_payload")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO waypoints (
                  name, type, latitude, longitude, notes, priority, status,
                  created_by_node_id, created_by_node_name, created_by_tactical_callsign,
                  source, raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["name"],
                    data["type"],
                    data["latitude"],
                    data["longitude"],
                    data["notes"],
                    data["priority"],
                    data["status"],
                    created_by_node_id,
                    created_by_node_name,
                    created_by_tactical,
                    source,
                    json.dumps(raw_payload) if isinstance(raw_payload, (dict, list)) else raw_payload,
                ),
            )
            waypoint_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.created', ?, ?)
                """,
                (f"Created waypoint {data['name']}", json.dumps({"waypoint_id": waypoint_id, "source": source})),
            )
        waypoint = self.waypoint(waypoint_id)
        self.auto_log(
            "waypoint created" if source != "received" else "waypoint received",
            f"Waypoint {waypoint['name']} recorded at {waypoint['latitude']:.5f},{waypoint['longitude']:.5f}",
            {
                "from_node_id": waypoint["created_by_node_id"],
                "from_node_name": waypoint["created_by_node_name"],
                "from_tactical_callsign": waypoint["created_by_tactical_callsign"],
                "related_waypoint_id": waypoint_id,
                "source": "automatic",
            },
        )
        return waypoint

    def update_waypoint(self, waypoint_id, payload):
        existing = self.waypoint(waypoint_id)
        if not existing:
            raise KeyError("Waypoint not found")
        data = clean_waypoint_payload({**existing, **payload})
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE waypoints
                SET name = ?, type = ?, latitude = ?, longitude = ?, notes = ?,
                    priority = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    data["name"],
                    data["type"],
                    data["latitude"],
                    data["longitude"],
                    data["notes"],
                    data["priority"],
                    data["status"],
                    int(waypoint_id),
                ),
            )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.updated', ?, ?)
                """,
                (
                    f"Updated waypoint {data['name']}",
                    json.dumps({"waypoint_id": int(waypoint_id), "status": data["status"]}),
                ),
            )
        return self.waypoint(waypoint_id)

    def share_waypoint(self, waypoint_id, channel_index):
        waypoint = self.waypoint(waypoint_id)
        if not waypoint or waypoint["status"] == "deleted":
            raise KeyError("Waypoint not found")
        channel_name = self.channel_name(int(channel_index))
        body = waypoint_text(waypoint)
        message = self.create_outbound_message(int(channel_index), body)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE waypoints
                SET shared_channel_index = ?, shared_channel_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(channel_index), channel_name, int(waypoint_id)),
            )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.share_attempt', ?, ?)
                """,
                (
                    f"Queued waypoint {waypoint['name']} for {channel_index} {channel_name}",
                    json.dumps({"waypoint_id": int(waypoint_id), "message_id": message["id"], "channel_index": int(channel_index)}),
                ),
            )
        waypoint = self.waypoint(waypoint_id)
        self.auto_log(
            "waypoint shared",
            f"Queued waypoint share for {waypoint['name']} on {channel_index} {channel_name}",
            {
                "from_node_id": message["sender_node_id"],
                "from_node_name": message["sender_name"],
                "from_tactical_callsign": message["sender_tactical_callsign"] or "",
                "channel_index": int(channel_index),
                "channel_name": channel_name,
                "related_message_id": message["id"],
                "related_waypoint_id": int(waypoint_id),
                "source": "automatic",
            },
        )
        return {"waypoint": waypoint, "message": message, "body": body}

    def pending_waypoints(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM pending_waypoints
                WHERE status = 'pending'
                ORDER BY id DESC
                """
            ).fetchall()
        return [self._pending_waypoint_dict(row) for row in rows]

    def create_pending_waypoint_from_message(self, payload):
        parsed = parse_waypoint_message(payload.get("body", ""))
        if not parsed:
            raise ValueError("Message body does not match waypoint format")
        raw_payload = {"parsed": parsed}
        channel_index = payload.get("channel_index")
        channel_name = None
        if channel_index is not None and str(channel_index).isdigit():
            channel_index = int(channel_index)
            channel_name = self.channel_name(channel_index)
        else:
            channel_index = None
        sender_node_id = str(payload.get("sender_node_id") or "").strip()
        sender_node_name = str(payload.get("sender_node_name") or sender_node_id).strip()
        sender_tactical = str(payload.get("sender_tactical_callsign") or "").strip()
        if sender_node_id and not sender_tactical:
            sender = self.node(sender_node_id)
            if sender:
                sender_tactical = sender.get("tactical_callsign") or ""
                sender_node_name = sender.get("node_name") or sender_node_name
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO pending_waypoints (
                  name, type, latitude, longitude, notes, priority, status,
                  sender_node_id, sender_node_name, sender_tactical_callsign,
                  channel_index, channel_name, raw_message_body, raw_payload
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    parsed["name"],
                    parsed["type"],
                    parsed["latitude"],
                    parsed["longitude"],
                    parsed["notes"],
                    parsed["priority"],
                    sender_node_id,
                    sender_node_name,
                    sender_tactical,
                    channel_index,
                    channel_name,
                    str(payload.get("body", "")),
                    json.dumps(raw_payload),
                ),
            )
            pending_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.pending.created', ?, ?)
                """,
                (f"Parsed pending waypoint {parsed['name']}", json.dumps({"pending_waypoint_id": pending_id})),
            )
        pending = self.pending_waypoint(pending_id)
        self.auto_log(
            "waypoint received",
            f"Parsed pending waypoint {pending['name']} from {pending['sender_display']}",
            {
                "from_node_id": pending["sender_node_id"],
                "from_node_name": pending["sender_node_name"],
                "from_tactical_callsign": pending["sender_tactical_callsign"],
                "channel_index": pending["channel_index"],
                "channel_name": pending["channel_name"],
                "source": "automatic",
            },
        )
        return pending

    def pending_waypoint(self, pending_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM pending_waypoints WHERE id = ?", (int(pending_id),)).fetchone()
        return self._pending_waypoint_dict(row) if row else None

    def save_pending_waypoint(self, pending_id):
        pending = self.pending_waypoint(pending_id)
        if not pending or pending["status"] != "pending":
            raise KeyError("Pending waypoint not found")
        waypoint = self.create_waypoint(
            {
                "name": pending["name"],
                "type": pending["type"],
                "latitude": pending["latitude"],
                "longitude": pending["longitude"],
                "notes": pending["notes"],
                "priority": pending["priority"],
                "status": "active",
                "created_by_node_id": pending["sender_node_id"],
                "created_by_node_name": pending["sender_node_name"],
                "created_by_tactical_callsign": pending["sender_tactical_callsign"],
                "source": "received",
                "raw_payload": {"pending_waypoint_id": pending["id"], "raw_message_body": pending["raw_message_body"]},
            }
        )
        with self._connect() as conn:
            conn.execute("UPDATE pending_waypoints SET status = 'saved' WHERE id = ?", (int(pending_id),))
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.pending.saved', ?, ?)
                """,
                (f"Saved pending waypoint {pending['name']}", json.dumps({"pending_waypoint_id": pending["id"], "waypoint_id": waypoint["id"]})),
            )
        self.auto_log(
            "waypoint received",
            f"Saved pending waypoint {pending['name']} from {pending['sender_display']}",
            {
                "from_node_id": pending["sender_node_id"],
                "from_node_name": pending["sender_node_name"],
                "from_tactical_callsign": pending["sender_tactical_callsign"],
                "channel_index": pending["channel_index"],
                "channel_name": pending["channel_name"],
                "related_waypoint_id": waypoint["id"],
                "source": "automatic",
            },
        )
        return {"pending": self.pending_waypoint(pending_id), "waypoint": waypoint}

    def ignore_pending_waypoint(self, pending_id):
        pending = self.pending_waypoint(pending_id)
        if not pending or pending["status"] != "pending":
            raise KeyError("Pending waypoint not found")
        with self._connect() as conn:
            conn.execute("UPDATE pending_waypoints SET status = 'ignored' WHERE id = ?", (int(pending_id),))
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('waypoint.pending.ignored', ?, ?)
                """,
                (f"Ignored pending waypoint {pending['name']}", json.dumps({"pending_waypoint_id": pending["id"]})),
            )
        self.auto_log(
            "operator note",
            f"Ignored pending waypoint {pending['name']} from {pending['sender_display']}",
            {
                "from_node_id": pending["sender_node_id"],
                "from_node_name": pending["sender_node_name"],
                "from_tactical_callsign": pending["sender_tactical_callsign"],
                "channel_index": pending["channel_index"],
                "channel_name": pending["channel_name"],
                "source": "automatic",
            },
        )
        return self.pending_waypoint(pending_id)

    def net_sessions(self):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM net_sessions
                ORDER BY status = 'active' DESC, COALESCE(end_time, start_time) DESC, id DESC
                """
            ).fetchall()
        return [self._net_session_dict(row) for row in rows]

    def active_net_session(self):
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT *
                FROM net_sessions
                WHERE status = 'active'
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return self._net_session_dict(row) if row else None

    def net_session(self, session_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM net_sessions WHERE id = ?", (int(session_id),)).fetchone()
        return self._net_session_dict(row) if row else None

    def create_net_session(self, payload):
        data = clean_session_payload(payload)
        channel_name = self.channel_name(data["active_channel_index"])
        local = self.node("!fieldstation-local") or {}
        station_id = data["station_id"] or local.get("node_id") or "!fieldstation-local"
        station_tactical = data["station_tactical_callsign"] or local.get("tactical_callsign") or ""
        start_time = str(payload.get("start_time") or utc_now())
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO net_sessions (
                  event_name, operational_period, net_name, operator_name,
                  operator_callsign, station_id, station_tactical_callsign,
                  active_channel_index, active_channel_name, start_time, status, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    data["event_name"],
                    data["operational_period"],
                    data["net_name"],
                    data["operator_name"],
                    data["operator_callsign"],
                    station_id,
                    station_tactical,
                    data["active_channel_index"],
                    channel_name,
                    start_time,
                    data["notes"],
                ),
            )
            session_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('net.session.started', ?, ?)
                """,
                (f"Started net session {data['net_name']}", json.dumps({"net_session_id": session_id})),
            )
        session = self.net_session(session_id)
        self.add_net_log_entry(
            {
                "net_session_id": session_id,
                "timestamp": start_time,
                "entry_type": "operator note",
                "channel_index": session["active_channel_index"],
                "message": f"Started net session {session['net_name']}",
                "source": "automatic",
            }
        )
        return session

    def close_net_session(self, session_id=None, notes=""):
        session = self.net_session(session_id) if session_id else self.active_net_session()
        if not session:
            raise KeyError("Net session not found")
        end_time = utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE net_sessions
                SET status = 'closed', end_time = ?, notes = CASE WHEN ? = '' THEN notes ELSE ? END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (end_time, notes, notes, session["id"]),
            )
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('net.session.closed', ?, ?)
                """,
                (f"Closed net session {session['net_name']}", json.dumps({"net_session_id": session["id"]})),
            )
        self.add_net_log_entry(
            {
                "net_session_id": session["id"],
                "timestamp": end_time,
                "entry_type": "operator note",
                "message": f"Closed net session {session['net_name']}",
                "source": "automatic",
            }
        )
        return self.net_session(session["id"])

    def net_log_entries(self, session_id=None):
        params = []
        where = ""
        if session_id:
            where = "WHERE net_session_id = ?"
            params.append(int(session_id))
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM net_log_entries
                {where}
                ORDER BY timestamp ASC, id ASC
                """,
                params,
            ).fetchall()
        return [self._net_log_entry_dict(row) for row in rows]

    def add_net_log_entry(self, payload):
        data = clean_entry_payload(payload)
        session_id = payload.get("net_session_id") or (self.active_net_session() or {}).get("id")
        if not session_id:
            raise KeyError("No active net session")
        session = self.net_session(session_id)
        if not session:
            raise KeyError("Net session not found")
        channel_index = payload.get("channel_index")
        channel_name = payload.get("channel_name")
        if channel_index not in (None, ""):
            channel_index = int(channel_index)
            channel_name = channel_name or self.channel_name(channel_index)
        else:
            channel_index = session["active_channel_index"]
            channel_name = session["active_channel_name"]
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO net_log_entries (
                  net_session_id, timestamp, entry_type,
                  from_node_id, from_node_name, from_tactical_callsign,
                  to_node_id, to_node_name, to_tactical_callsign,
                  channel_index, channel_name, message,
                  related_message_id, related_waypoint_id, source
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(session_id),
                    data["timestamp"],
                    data["entry_type"],
                    str(payload.get("from_node_id") or ""),
                    str(payload.get("from_node_name") or ""),
                    str(payload.get("from_tactical_callsign") or ""),
                    str(payload.get("to_node_id") or ""),
                    str(payload.get("to_node_name") or ""),
                    str(payload.get("to_tactical_callsign") or ""),
                    channel_index,
                    channel_name,
                    data["message"],
                    payload.get("related_message_id"),
                    payload.get("related_waypoint_id"),
                    data["source"],
                ),
            )
        return self.net_log_entry(cursor.lastrowid)

    def update_net_log_entry(self, entry_id, payload):
        entry = self.net_log_entry(entry_id)
        if not entry:
            raise KeyError("Net log entry not found")
        updates = {}
        if "entry_type" in payload:
            entry_type = str(payload.get("entry_type") or "").strip()
            if entry_type not in ENTRY_TYPES:
                raise ValueError(f"entry_type must be one of: {', '.join(ENTRY_TYPES)}")
            updates["entry_type"] = entry_type
        for key in ("from_node_name", "from_tactical_callsign", "to_node_name", "to_tactical_callsign"):
            if key in payload:
                updates[key] = str(payload.get(key) or "").strip()
        if "channel_index" in payload:
            channel_index = int(payload.get("channel_index"))
            updates["channel_index"] = channel_index
            updates["channel_name"] = self.channel_name(channel_index)
        if "message" in payload:
            message = str(payload.get("message") or "").strip()
            if not message:
                raise ValueError("message is required")
            updates["message"] = message[:1000]
        if not updates:
            return entry
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values())
        values.append(int(entry_id))
        with self._connect() as conn:
            conn.execute(
                f"""
                UPDATE net_log_entries
                SET {assignments}
                WHERE id = ?
                """,
                values,
            )
        return self.net_log_entry(entry_id)

    def net_log_entry(self, entry_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM net_log_entries WHERE id = ?", (int(entry_id),)).fetchone()
        return self._net_log_entry_dict(row) if row else None

    def auto_log(self, entry_type, message, payload=None):
        if entry_type not in ENTRY_TYPES:
            entry_type = "operator note"
        session = self.active_net_session()
        if not session:
            return None
        data = dict(payload or {})
        data.update({"net_session_id": session["id"], "entry_type": entry_type, "message": message, "source": data.get("source", "automatic")})
        try:
            return self.add_net_log_entry(data)
        except Exception:
            return None

    def export_net_log(self, export_type, export_format, session_id=None):
        if export_type not in EXPORT_TYPES:
            raise ValueError("export_type must be ics309 or ics214")
        if export_format not in EXPORT_FORMATS:
            raise ValueError("format must be csv or text")
        session = self.net_session(session_id) if session_id else self.active_net_session()
        if not session:
            raise KeyError("Net session not found")
        entries = self.net_log_entries(session["id"])
        content = build_export(export_type, export_format, session, entries)
        filename = export_filename(export_type, export_format, session)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ics_exports (net_session_id, export_type, export_format, filename)
                VALUES (?, ?, ?, ?)
                """,
                (session["id"], export_type, export_format, filename),
            )
            export_id = cursor.lastrowid
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES ('net.export.created', ?, ?)
                """,
                (f"Created {export_type.upper()}-style {export_format} export", json.dumps({"export_id": export_id, "net_session_id": session["id"]})),
            )
        return {"export": self.ics_export(export_id), "filename": filename, "content": content, "content_type": "text/csv" if export_format == "csv" else "text/plain"}

    def ics_export(self, export_id):
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ics_exports WHERE id = ?", (int(export_id),)).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "net_session_id": row["net_session_id"],
            "export_type": row["export_type"],
            "export_format": row["export_format"],
            "filename": row["filename"],
            "created_at": row["created_at"],
        }

    def starter_bundle_preview(self, payload=None):
        categories = normalize_categories((payload or {}).get("categories"))
        return {
            "included_categories": categories,
            "excluded_by_default": list(EXCLUDED_BY_DEFAULT),
            "not_a_clone": True,
            "local_identity_excluded": True,
            "message_history_excluded": True,
            "net_logs_excluded": True,
            "raw_events_excluded": True,
            "counts": self._starter_counts(categories),
        }

    def starter_bundle_export(self, payload=None):
        payload = payload or {}
        categories = normalize_categories(payload.get("categories"))
        bundle = metadata(categories, payload.get("source_label", "FieldStation starter data"))
        bundle["data"] = self._starter_data(categories)
        return bundle

    def starter_bundle_import_preview(self, document):
        return import_preview(document)

    def starter_bundle_import(self, document, confirm=False):
        preview = import_preview(document)
        if not confirm:
            raise ValueError("Starter bundle import requires confirm=true")
        data = document.get("data") or {}
        imported = {"channel_profiles": 0, "waypoints": 0, "known_remote_nodes": 0, "remote_tactical_callsigns": 0}
        skipped = {"channel_profiles": 0, "waypoints": 0}
        for profile_doc in data.get("channel_profiles", []):
            try:
                self.import_channel_profile(profile_doc, overwrite=False)
                imported["channel_profiles"] += 1
            except ValueError:
                skipped["channel_profiles"] += 1
                continue
        for node in data.get("known_remote_nodes", []):
            if node.get("node_id") == "!fieldstation-local" or node.get("is_local"):
                continue
            self.upsert_known_node({**node, "is_local": False})
            imported["known_remote_nodes"] += 1
        for item in data.get("remote_tactical_callsigns", []):
            node_id = item.get("node_id")
            if node_id and node_id != "!fieldstation-local":
                self.set_tactical_callsign(node_id, item.get("tactical_callsign", ""))
                imported["remote_tactical_callsigns"] += 1
        for waypoint in data.get("waypoints", []):
            if self._waypoint_import_exists(waypoint):
                skipped["waypoints"] += 1
                continue
            self.create_waypoint(
                {
                    **waypoint,
                    "created_by_node_id": waypoint.get("created_by_node_id") or "starter-bundle",
                    "created_by_node_name": waypoint.get("created_by_node_name") or "Starter Data Bundle",
                    "created_by_tactical_callsign": waypoint.get("created_by_tactical_callsign") or "",
                    "source": "starter_bundle",
                }
            )
            imported["waypoints"] += 1
        return {"preview": preview, "imported": imported, "skipped": skipped}

    def _waypoint_import_exists(self, waypoint):
        name = str(waypoint.get("name") or "").strip()
        if not name:
            return False
        try:
            latitude = float(waypoint.get("latitude"))
            longitude = float(waypoint.get("longitude"))
        except (TypeError, ValueError):
            return False
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id
                FROM waypoints
                WHERE name = ?
                  AND ABS(latitude - ?) < 0.000001
                  AND ABS(longitude - ?) < 0.000001
                  AND status != 'deleted'
                LIMIT 1
                """,
                (name, latitude, longitude),
            ).fetchone()
        return bool(row)

    def usb_writer_status(self):
        return {
            "mode": "folder_package_only",
            "raw_disk_writes": False,
            "formatting_supported": False,
            "bootable_usb_supported": False,
            "default_package_folder": "FieldStation-USB-YYYYMMDD-HHMMSS",
            "safe_target_required": True,
        }

    def usb_writer_preview(self, payload):
        target = validate_target(payload.get("target_path"), self.repo_root())
        include_bundle = bool(payload.get("include_starter_bundle"))
        categories = normalize_categories(payload.get("starter_categories")) if include_bundle else []
        files = self._usb_package_files(include_bundle, categories)
        return {
            "target_path": str(target),
            "target_looks_removable": looks_removable(target),
            "package_folder": "FieldStation-USB-YYYYMMDD-HHMMSS",
            "files": sorted(files.keys()),
            "included_categories": categories,
            "safe_eject_guidance": "After creation, use your OS file manager or shell to safely eject removable media if applicable.",
        }

    def usb_writer_create(self, payload):
        include_bundle = bool(payload.get("include_starter_bundle"))
        categories = normalize_categories(payload.get("starter_categories")) if include_bundle else []
        files = self._usb_package_files(include_bundle, categories)
        result = create_package(payload.get("target_path"), files, categories, self.repo_root())
        result["target_looks_removable"] = looks_removable(result["package_dir"])
        result["safe_eject_guidance"] = "When copying completes, safely eject removable media using the operating system."
        self.record_raw_event("usb_writer.package_created", "Created FieldStation USB package", {"package_dir": result["package_dir"]})
        return result

    def usb_writer_verify(self, payload):
        return verify_package(payload.get("package_dir"))

    def repo_root(self):
        return Path(__file__).resolve().parents[1]

    def _usb_package_files(self, include_starter_bundle=False, categories=None):
        default_profile = self.export_channel_profile(1)
        files = {
            "README.md": usb_readme(),
            "install/SETUP.md": usb_setup(),
            "assets/channel-profiles/fieldstation-default.json": json.dumps(default_profile, indent=2),
            "assets/maps/README.md": "Offline map placeholder. Add bundled PMTiles/MBTiles here in a future map asset phase.\n",
            "assets/ics/README.md": "ICS 309-style and ICS 214-style exports are generated from FieldStation Net Log mode.\n",
            "starter-data/README.md": "Starter Data Bundle files are optional and never clone local station identity by default.\n",
        }
        if include_starter_bundle:
            bundle = self.starter_bundle_export({"categories": categories or list(DEFAULT_CATEGORIES)})
            files["starter-data/starter-bundle.json"] = json.dumps(bundle, indent=2)
        return files

    def _starter_counts(self, categories):
        data = self._starter_data(categories)
        return {
            "channel_profiles": len(data.get("channel_profiles", [])),
            "waypoints": len(data.get("waypoints", [])),
            "known_remote_nodes": len(data.get("known_remote_nodes", [])),
            "remote_tactical_callsigns": len(data.get("remote_tactical_callsigns", [])),
        }

    def _starter_data(self, categories):
        data = {}
        if "channel_profiles" in categories or "default_channel_profile" in categories:
            data["channel_profiles"] = [self.export_channel_profile(profile["id"]) for profile in self.channel_profiles()]
        if "map_placeholder" in categories:
            data["map_placeholder"] = self.map_status()
        if "waypoints" in categories:
            data["waypoints"] = [
                {
                    "name": item["name"],
                    "type": item["type"],
                    "latitude": item["latitude"],
                    "longitude": item["longitude"],
                    "notes": item["notes"],
                    "priority": item["priority"],
                    "status": item["status"],
                    "created_by_node_id": item["created_by_node_id"] if item["created_by_node_id"] != "!fieldstation-local" else "",
                    "created_by_node_name": item["created_by_node_name"] if item["created_by_node_id"] != "!fieldstation-local" else "",
                    "created_by_tactical_callsign": item["created_by_tactical_callsign"] if item["created_by_node_id"] != "!fieldstation-local" else "",
                }
                for item in self.waypoints()
            ]
        if "known_remote_nodes" in categories:
            data["known_remote_nodes"] = [
                {key: value for key, value in node.items() if key not in ("display_name", "tactical_callsign")}
                for node in self.nodes()
                if not node["is_local"]
            ]
        if "remote_tactical_callsigns" in categories:
            data["remote_tactical_callsigns"] = [
                {"node_id": node["node_id"], "tactical_callsign": node["tactical_callsign"]}
                for node in self.nodes()
                if not node["is_local"] and node.get("tactical_callsign")
            ]
        if "ics_templates" in categories:
            data["ics_templates"] = {"formats": ["ics309_csv", "ics309_text", "ics214_csv", "ics214_text"]}
        if "documentation" in categories:
            data["documentation"] = {"setup_guide": "See README.md and install/SETUP.md in the USB package."}
        return data

    def set_setting(self, key, value):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                  value = excluded.value,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value)),
            )

    def get_setting(self, key, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return default

    def record_adapter_status(self, status):
        previous = self.get_setting("adapter.status", {})
        self.set_setting("adapter.status", status)
        if previous.get("state") != status.get("state"):
            self.record_raw_event(
                "adapter.state",
                f"Adapter state changed to {status.get('state', 'unknown')}",
                {
                    "previous_state": previous.get("state"),
                    "state": status.get("state"),
                    "selected_port": status.get("selected_port"),
                    "error": status.get("error"),
                },
            )
            state = status.get("state", "unknown")
            if state == "connected":
                entry_type = "node connected"
            elif state in ("disconnected", "degraded", "reconnecting"):
                entry_type = "node disconnected" if state == "disconnected" else "notable error"
            else:
                entry_type = "operator note"
            self.auto_log(
                entry_type,
                f"Adapter state changed to {state}: {status.get('detail') or status.get('error') or ''}".strip(),
                {"source": "automatic"},
            )

    def record_raw_event(self, event_type, summary, payload=None):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO raw_events (event_type, summary, payload_json)
                VALUES (?, ?, ?)
                """,
                (event_type, summary, json.dumps(payload or {})),
            )

    def recent_events(self, limit=25):
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, event_type, summary, payload_json, created_at
                FROM raw_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "summary": row["summary"],
                "payload": json.loads(row["payload_json"] or "{}"),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def status_counts(self):
        with self._connect() as conn:
            message_count = conn.execute("SELECT COUNT(*) AS count FROM messages").fetchone()["count"]
            node_count = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM known_nodes
                WHERE node_id != '!fieldstation-local'
                   OR NOT EXISTS (
                     SELECT 1 FROM known_nodes
                     WHERE is_local = 1 AND node_id != '!fieldstation-local'
                   )
                """
            ).fetchone()["count"]
            waypoint_count = conn.execute("SELECT COUNT(*) AS count FROM waypoints WHERE status != 'deleted'").fetchone()["count"]
            pending_count = conn.execute("SELECT COUNT(*) AS count FROM pending_waypoints WHERE status = 'pending'").fetchone()["count"]
            net_session_count = conn.execute("SELECT COUNT(*) AS count FROM net_sessions").fetchone()["count"]
            active_net_count = conn.execute("SELECT COUNT(*) AS count FROM net_sessions WHERE status = 'active'").fetchone()["count"]
            net_entry_count = conn.execute("SELECT COUNT(*) AS count FROM net_log_entries").fetchone()["count"]
        return {
            "messages": message_count,
            "known_nodes": node_count,
            "waypoints": waypoint_count,
            "pending_waypoints": pending_count,
            "net_sessions": net_session_count,
            "active_net_sessions": active_net_count,
            "net_log_entries": net_entry_count,
        }

    def _message_dict(self, row):
        identity = display_identity(row["tactical_callsign"], row["sender_name"], row["sender_node_id"])
        return {
            "id": row["id"],
            "timestamp": row["timestamp"],
            "sender_node_id": row["sender_node_id"],
            "sender_name": row["sender_name"],
            "sender_tactical_callsign": row["tactical_callsign"],
            "sender_display": identity,
            "direction": row["direction"],
            "channel_index": row["channel_index"],
            "channel_name": row["channel_name"],
            "channel_label": channel_label({"index": row["channel_index"], "name": row["channel_name"]}),
            "body": row["body"],
            "status": row["status"],
            "status_label": MESSAGE_STATUSES.get(row["status"], row["status"]),
            "status_tone": MESSAGE_STATUS_TONES.get(row["status"], "unknown"),
            "is_sample": bool(row["is_sample"]),
            "offline": row["status"] in ("queued_local", "retry_available", "failed"),
        }

    def _node_dict(self, row):
        return {
            "node_id": row["node_id"],
            "node_name": row["node_name"],
            "short_name": row["short_name"],
            "tactical_callsign": row["tactical_callsign"],
            "display_name": display_identity(row["tactical_callsign"], row["node_name"], row["node_id"]),
            "is_local": bool(row["is_local"]),
            "is_sample": bool(row["is_sample"]),
            "firmware_version": row["firmware_version"],
            "app_version": row["app_version"],
            "role": row["role"],
            "region": row["region"],
            "modem_preset": row["modem_preset"],
            "current_channel": row["current_channel"],
            "battery_level": row["battery_level"],
            "voltage": row["voltage"],
            "charging_state": row["charging_state"],
            "gps_status": row["gps_status"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "rssi": row["rssi"],
            "snr": row["snr"],
            "last_heard_at": row["last_heard_at"],
            "freshness": freshness(row["last_heard_at"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _position_dict(self, row):
        return {
            "node_id": row["node_id"],
            "node_name": row["node_name"],
            "tactical_callsign": row["tactical_callsign"],
            "display_name": display_identity(row["tactical_callsign"], row["node_name"], row["node_id"]),
            "is_local": bool(row["is_local"]),
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "freshness": freshness(row["last_heard_at"]),
            "last_heard_at": row["last_heard_at"],
            "source": "stored",
        }

    def _waypoint_dict(self, row):
        created_display = display_identity(
            row["created_by_tactical_callsign"],
            row["created_by_node_name"],
            row["created_by_node_id"],
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "notes": row["notes"],
            "priority": row["priority"],
            "status": row["status"],
            "created_by_node_id": row["created_by_node_id"],
            "created_by_node_name": row["created_by_node_name"],
            "created_by_tactical_callsign": row["created_by_tactical_callsign"],
            "created_by_display": created_display,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "shared_channel_index": row["shared_channel_index"],
            "shared_channel_name": row["shared_channel_name"],
            "shared_channel_label": channel_label({"index": row["shared_channel_index"], "name": row["shared_channel_name"]}) if row["shared_channel_index"] is not None else "",
            "source": row["source"],
            "raw_payload": safe_json(row["raw_payload"]),
            "share_text": waypoint_text(row),
        }

    def _pending_waypoint_dict(self, row):
        sender_display = display_identity(
            row["sender_tactical_callsign"],
            row["sender_node_name"],
            row["sender_node_id"],
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "type": row["type"],
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "notes": row["notes"],
            "priority": row["priority"],
            "status": row["status"],
            "sender_node_id": row["sender_node_id"],
            "sender_node_name": row["sender_node_name"],
            "sender_tactical_callsign": row["sender_tactical_callsign"],
            "sender_display": sender_display,
            "channel_index": row["channel_index"],
            "channel_name": row["channel_name"],
            "channel_label": channel_label({"index": row["channel_index"], "name": row["channel_name"]}) if row["channel_index"] is not None else "",
            "received_at": row["received_at"],
            "raw_message_body": row["raw_message_body"],
            "raw_payload": safe_json(row["raw_payload"]),
        }

    def _net_session_dict(self, row):
        return {
            "id": row["id"],
            "event_name": row["event_name"],
            "operational_period": row["operational_period"],
            "net_name": row["net_name"],
            "operator_name": row["operator_name"],
            "operator_callsign": row["operator_callsign"],
            "station_id": row["station_id"],
            "station_tactical_callsign": row["station_tactical_callsign"],
            "station_display": display_identity(row["station_tactical_callsign"], "", row["station_id"]),
            "active_channel_index": row["active_channel_index"],
            "active_channel_name": row["active_channel_name"],
            "active_channel_label": channel_label({"index": row["active_channel_index"], "name": row["active_channel_name"]}) if row["active_channel_index"] is not None else "",
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "status": row["status"],
            "notes": row["notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def _net_log_entry_dict(self, row):
        return {
            "id": row["id"],
            "net_session_id": row["net_session_id"],
            "timestamp": row["timestamp"],
            "entry_type": row["entry_type"],
            "from_node_id": row["from_node_id"],
            "from_node_name": row["from_node_name"],
            "from_tactical_callsign": row["from_tactical_callsign"],
            "from_display": display_identity(row["from_tactical_callsign"], row["from_node_name"], row["from_node_id"]) if (row["from_node_id"] or row["from_node_name"] or row["from_tactical_callsign"]) else "",
            "to_node_id": row["to_node_id"],
            "to_node_name": row["to_node_name"],
            "to_tactical_callsign": row["to_tactical_callsign"],
            "to_display": display_identity(row["to_tactical_callsign"], row["to_node_name"], row["to_node_id"]) if (row["to_node_id"] or row["to_node_name"] or row["to_tactical_callsign"]) else "",
            "channel_index": row["channel_index"],
            "channel_name": row["channel_name"],
            "channel_label": channel_label({"index": row["channel_index"], "name": row["channel_name"]}) if row["channel_index"] is not None else "",
            "message": row["message"],
            "related_message_id": row["related_message_id"],
            "related_waypoint_id": row["related_waypoint_id"],
            "source": row["source"],
            "created_at": row["created_at"],
        }


def display_identity(tactical_callsign, node_name, node_id):
    real = node_name or node_id
    if tactical_callsign:
        return f"{tactical_callsign} / {real}"
    return real


def safe_json(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def freshness(timestamp):
    if not timestamp:
        return "stale"
    try:
        normalized = timestamp.replace("Z", "+00:00")
        heard = datetime.fromisoformat(normalized)
        if heard.tzinfo is None:
            heard = heard.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - heard).total_seconds()
        if age <= 900:
            return "recent"
        if age <= 3600:
            return "aging"
        return "stale"
    except ValueError:
        return "unknown"


def usb_readme():
    return """# FieldStation USB Package

This folder is an offline FieldStation setup/package folder. It is not a
bootable USB image and it was created without formatting or raw disk writes.

Contents may include setup notes, local channel profile templates, map
placeholder metadata, ICS export notes, checksums, and an optional Starter Data
Bundle. Channel profiles are local templates only and are not applied to radio
hardware in this phase.

Real Meshtastic send/receive still requires future adapter integration.
"""


def usb_setup():
    return """# Setup

1. Copy this package to the target computer if needed.
2. Review README.md and manifest.json.
3. Verify checksums with the included checksums.txt.
4. Use the main project installer flow for FieldStation installation.
5. Import channel profiles or Starter Data Bundle data only after review.

The Starter Data Bundle is not a clone. It excludes local station identity,
local tactical callsign, serial paths, machine settings, message history, net
logs, raw events, and secrets by default.
"""
