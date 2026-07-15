from datetime import datetime, timezone


SCHEMA_VERSION = 1
DEFAULT_CATEGORIES = (
    "channel_profiles",
    "map_placeholder",
    "waypoints",
    "known_remote_nodes",
    "remote_tactical_callsigns",
    "ics_templates",
    "documentation",
)

EXCLUDED_BY_DEFAULT = (
    "local station tactical callsign",
    "local node identity",
    "serial device path",
    "local GPS/home position",
    "active connection profile",
    "active net session",
    "machine bind/port/service settings",
    "message history",
    "net logs",
    "raw events",
    "secrets and PSKs",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_categories(categories):
    if not categories:
        return list(DEFAULT_CATEGORIES)
    requested = [str(item).strip() for item in categories if str(item).strip()]
    allowed = set(DEFAULT_CATEGORIES)
    bad = [item for item in requested if item not in allowed]
    if bad:
        raise ValueError(f"Unsupported starter bundle categories: {', '.join(bad)}")
    return requested


def metadata(categories, source_label="FieldStation export"):
    return {
        "schema": "fieldstation.starter_bundle",
        "schema_version": SCHEMA_VERSION,
        "fieldstation_app_version": "mvp",
        "exported_at": utc_now(),
        "source_label": str(source_label or "FieldStation export")[:80],
        "included_categories": categories,
        "sensitive_material_warning": False,
        "not_a_clone": True,
        "excluded_by_default": list(EXCLUDED_BY_DEFAULT),
    }


def import_preview(document):
    if not isinstance(document, dict):
        raise ValueError("Starter bundle must be a JSON object")
    if document.get("schema") != "fieldstation.starter_bundle":
        raise ValueError("Unsupported starter bundle schema")
    if int(document.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("Unsupported starter bundle schema_version")
    data = document.get("data") or {}
    return {
        "schema_version": document.get("schema_version"),
        "source_label": document.get("source_label", ""),
        "included_categories": document.get("included_categories", []),
        "will_import": {
            "channel_profiles": len(data.get("channel_profiles", [])),
            "waypoints": len(data.get("waypoints", [])),
            "known_remote_nodes": len(data.get("known_remote_nodes", [])),
            "remote_tactical_callsigns": len(data.get("remote_tactical_callsigns", [])),
        },
        "will_not_import": list(EXCLUDED_BY_DEFAULT),
        "requires_confirmation": True,
    }
