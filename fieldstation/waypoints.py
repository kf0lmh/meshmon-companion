WAYPOINT_TYPES = (
    "General",
    "Net Control",
    "Relay Point",
    "Hazard",
    "Road Closure",
    "Shelter",
    "Staging",
    "Observation",
    "Weather Report",
    "Damage Report",
    "Resource Needed",
    "Resource Available",
)

WAYPOINT_STATUSES = ("active", "resolved", "stale", "deleted")

LINCOLN_COUNTY_BOUNDS = {
    "north": 39.38,
    "south": 38.86,
    "west": -91.28,
    "east": -90.58,
    "center_latitude": 39.08,
    "center_longitude": -90.96,
}


def clean_waypoint_payload(payload, partial=False):
    data = dict(payload or {})
    if not partial or "name" in data:
        name = str(data.get("name", "")).strip()
        if not name:
            raise ValueError("Waypoint name is required")
        data["name"] = name[:120]
    if not partial or "type" in data:
        waypoint_type = str(data.get("type", "General")).strip() or "General"
        if waypoint_type not in WAYPOINT_TYPES:
            raise ValueError(f"Waypoint type must be one of: {', '.join(WAYPOINT_TYPES)}")
        data["type"] = waypoint_type
    if not partial or "latitude" in data:
        data["latitude"] = parse_coordinate(data.get("latitude"), "latitude", -90, 90)
    if not partial or "longitude" in data:
        data["longitude"] = parse_coordinate(data.get("longitude"), "longitude", -180, 180)
    if "status" in data or not partial:
        status = str(data.get("status", "active")).strip() or "active"
        if status not in WAYPOINT_STATUSES:
            raise ValueError(f"Waypoint status must be one of: {', '.join(WAYPOINT_STATUSES)}")
        data["status"] = status
    if "notes" in data or not partial:
        data["notes"] = str(data.get("notes", "")).strip()[:500]
    if "priority" in data or not partial:
        data["priority"] = str(data.get("priority", "Normal")).strip()[:32] or "Normal"
    return data


def parse_coordinate(value, label, minimum, maximum):
    try:
        coord = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} must be a number") from None
    if coord < minimum or coord > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return coord


def waypoint_text(waypoint):
    lines = [
        f"WAYPOINT: {value_for(waypoint, 'name')}",
        f"TYPE: {value_for(waypoint, 'type')}",
        f"GPS: {float(value_for(waypoint, 'latitude')):.5f},{float(value_for(waypoint, 'longitude')):.5f}",
    ]
    note = str(value_for(waypoint, "notes") or "").strip()
    if note:
        lines.append(f"NOTE: {note[:120]}")
    return "\n".join(lines)


def value_for(mapping, key):
    if hasattr(mapping, "get"):
        return mapping.get(key)
    return mapping[key]


def parse_waypoint_message(body):
    fields = {}
    for raw in str(body or "").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        fields[key.strip().upper()] = value.strip()
    if not {"WAYPOINT", "TYPE", "GPS"}.issubset(fields):
        return None
    gps = fields["GPS"].split(",", 1)
    if len(gps) != 2:
        raise ValueError("Waypoint GPS must be formatted as latitude,longitude")
    parsed = {
        "name": fields["WAYPOINT"],
        "type": fields["TYPE"],
        "latitude": gps[0].strip(),
        "longitude": gps[1].strip(),
        "notes": fields.get("NOTE", ""),
        "priority": fields.get("PRIORITY", "Normal"),
        "status": "active",
    }
    return clean_waypoint_payload(parsed)
