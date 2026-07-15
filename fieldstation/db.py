import os
import sqlite3
from pathlib import Path

from .channel_profile import DEFAULT_CHANNELS

DEFAULT_DB_PATH = "/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3"


def database_path():
    return Path(os.environ.get("FIELDSTATION_DB", DEFAULT_DB_PATH))


def connect(path=None):
    db_path = Path(path) if path else database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=None):
    with connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channel_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL UNIQUE,
              description TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channels (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              profile_id INTEGER NOT NULL REFERENCES channel_profiles(id) ON DELETE CASCADE,
              channel_index INTEGER NOT NULL,
              name TEXT NOT NULL,
              role TEXT NOT NULL,
              is_private INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(profile_id, channel_index)
            );

            CREATE TABLE IF NOT EXISTS known_nodes (
              node_id TEXT PRIMARY KEY,
              node_name TEXT NOT NULL DEFAULT '',
              short_name TEXT NOT NULL DEFAULT '',
              is_local INTEGER NOT NULL DEFAULT 0,
              is_sample INTEGER NOT NULL DEFAULT 0,
              firmware_version TEXT,
              app_version TEXT,
              role TEXT,
              region TEXT,
              modem_preset TEXT,
              current_channel INTEGER,
              battery_level REAL,
              voltage REAL,
              charging_state TEXT,
              gps_status TEXT,
              latitude REAL,
              longitude REAL,
              rssi REAL,
              snr REAL,
              last_heard_at TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS node_tactical_callsigns (
              node_id TEXT PRIMARY KEY REFERENCES known_nodes(node_id) ON DELETE CASCADE,
              tactical_callsign TEXT NOT NULL,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              sender_node_id TEXT NOT NULL,
              sender_name TEXT NOT NULL DEFAULT '',
              direction TEXT NOT NULL,
              channel_index INTEGER NOT NULL,
              channel_name TEXT NOT NULL,
              body TEXT NOT NULL,
              status TEXT NOT NULL,
              is_sample INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS message_status_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
              status TEXT NOT NULL,
              detail TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS raw_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_type TEXT NOT NULL,
              summary TEXT NOT NULL,
              payload_json TEXT NOT NULL DEFAULT '{}',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS waypoints (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              latitude REAL NOT NULL,
              longitude REAL NOT NULL,
              notes TEXT NOT NULL DEFAULT '',
              priority TEXT NOT NULL DEFAULT 'Normal',
              status TEXT NOT NULL DEFAULT 'active',
              created_by_node_id TEXT NOT NULL,
              created_by_node_name TEXT NOT NULL DEFAULT '',
              created_by_tactical_callsign TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              shared_channel_index INTEGER,
              shared_channel_name TEXT,
              source TEXT NOT NULL DEFAULT 'manual',
              raw_payload TEXT
            );

            CREATE TABLE IF NOT EXISTS pending_waypoints (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              type TEXT NOT NULL,
              latitude REAL NOT NULL,
              longitude REAL NOT NULL,
              notes TEXT NOT NULL DEFAULT '',
              priority TEXT NOT NULL DEFAULT 'Normal',
              status TEXT NOT NULL DEFAULT 'pending',
              sender_node_id TEXT NOT NULL DEFAULT '',
              sender_node_name TEXT NOT NULL DEFAULT '',
              sender_tactical_callsign TEXT NOT NULL DEFAULT '',
              channel_index INTEGER,
              channel_name TEXT,
              received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              raw_message_body TEXT NOT NULL,
              raw_payload TEXT
            );

            CREATE TABLE IF NOT EXISTS net_sessions (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_name TEXT NOT NULL,
              operational_period TEXT NOT NULL DEFAULT '',
              net_name TEXT NOT NULL,
              operator_name TEXT NOT NULL,
              operator_callsign TEXT NOT NULL DEFAULT '',
              station_id TEXT NOT NULL DEFAULT '',
              station_tactical_callsign TEXT NOT NULL DEFAULT '',
              active_channel_index INTEGER,
              active_channel_name TEXT,
              start_time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              end_time TEXT,
              status TEXT NOT NULL DEFAULT 'active',
              notes TEXT NOT NULL DEFAULT '',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS net_log_entries (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              net_session_id INTEGER NOT NULL REFERENCES net_sessions(id) ON DELETE CASCADE,
              timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              entry_type TEXT NOT NULL,
              from_node_id TEXT NOT NULL DEFAULT '',
              from_node_name TEXT NOT NULL DEFAULT '',
              from_tactical_callsign TEXT NOT NULL DEFAULT '',
              to_node_id TEXT NOT NULL DEFAULT '',
              to_node_name TEXT NOT NULL DEFAULT '',
              to_tactical_callsign TEXT NOT NULL DEFAULT '',
              channel_index INTEGER,
              channel_name TEXT,
              message TEXT NOT NULL,
              related_message_id INTEGER,
              related_waypoint_id INTEGER,
              source TEXT NOT NULL DEFAULT 'manual',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS ics_exports (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              net_session_id INTEGER NOT NULL REFERENCES net_sessions(id) ON DELETE CASCADE,
              export_type TEXT NOT NULL,
              export_format TEXT NOT NULL,
              filename TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        migrate_schema(conn)
        seed_defaults(conn)


def migrate_schema(conn):
    ensure_columns(
        conn,
        "known_nodes",
        {
            "firmware_version": "TEXT",
            "app_version": "TEXT",
            "role": "TEXT",
            "region": "TEXT",
            "modem_preset": "TEXT",
            "current_channel": "INTEGER",
        },
    )


def ensure_columns(conn, table, columns):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def seed_defaults(conn):
    conn.execute(
        """
        INSERT OR IGNORE INTO channel_profiles (id, name, description)
        VALUES (1, 'FieldStation Default', 'Eight-slot FieldStation messaging profile')
        """
    )
    for channel in DEFAULT_CHANNELS:
        conn.execute(
            """
            INSERT OR IGNORE INTO channels
              (profile_id, channel_index, name, role, is_private)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                1,
                channel["index"],
                channel["name"],
                channel["role"],
                1 if channel["is_private"] else 0,
            ),
        )
    conn.execute(
        """
        INSERT OR IGNORE INTO known_nodes
          (node_id, node_name, short_name, is_local, is_sample)
        VALUES ('!fieldstation-local', 'Local operator', 'LOCAL', 1, 0)
        """
    )
