import csv
import io
from datetime import datetime, timezone


ENTRY_TYPES = (
    "check-in",
    "check-out",
    "voice contact",
    "relay",
    "situation report",
    "weather report",
    "resource/status update",
    "operator note",
    "message sent",
    "message received",
    "message failed",
    "node connected",
    "node disconnected",
    "telemetry update",
    "GPS/position update",
    "waypoint created",
    "waypoint shared",
    "waypoint received",
    "notable error",
)

SESSION_STATUSES = ("active", "closed")
EXPORT_TYPES = ("ics309", "ics214")
EXPORT_FORMATS = ("csv", "text")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def clean_session_payload(payload, partial=False):
    data = dict(payload or {})
    required = ("event_name", "net_name", "operator_name")
    if not partial:
        for key in required:
            if not str(data.get(key, "")).strip():
                raise ValueError(f"{key} is required")
    for key in (
        "event_name",
        "operational_period",
        "net_name",
        "operator_name",
        "operator_callsign",
        "station_id",
        "station_tactical_callsign",
        "notes",
    ):
        if key in data or not partial:
            data[key] = str(data.get(key, "")).strip()
    if "active_channel_index" in data and data["active_channel_index"] not in ("", None):
        data["active_channel_index"] = int(data["active_channel_index"])
    else:
        data["active_channel_index"] = 0
    return data


def clean_entry_payload(payload):
    data = dict(payload or {})
    entry_type = str(data.get("entry_type", "operator note")).strip() or "operator note"
    if entry_type not in ENTRY_TYPES:
        raise ValueError(f"entry_type must be one of: {', '.join(ENTRY_TYPES)}")
    message = str(data.get("message", "")).strip()
    if not message:
        raise ValueError("message is required")
    data["entry_type"] = entry_type
    data["message"] = message[:1000]
    data["timestamp"] = str(data.get("timestamp") or utc_now()).strip()
    data["source"] = str(data.get("source") or "manual").strip() or "manual"
    return data


def export_filename(export_type, export_format, session):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = "csv" if export_format == "csv" else "txt"
    safe_net = "".join(char.lower() if char.isalnum() else "-" for char in session["net_name"]).strip("-") or "net"
    return f"fieldstation-{export_type}-{safe_net}-{stamp}.{suffix}"


def build_export(export_type, export_format, session, entries):
    if export_type not in EXPORT_TYPES:
        raise ValueError("export_type must be ics309 or ics214")
    if export_format not in EXPORT_FORMATS:
        raise ValueError("export format must be csv or text")
    if export_type == "ics309":
        return build_ics309_csv(session, entries) if export_format == "csv" else build_ics309_text(session, entries)
    return build_ics214_csv(session, entries) if export_format == "csv" else build_ics214_text(session, entries)


def build_ics309_csv(session, entries):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ICS 309-style communications log"])
    write_session_rows(writer, session)
    writer.writerow([])
    writer.writerow(["Date/Time", "From", "To", "Channel", "Traffic Summary", "Notes/Status"])
    for entry in entries:
        writer.writerow([
            entry["timestamp"],
            entry["from_display"],
            entry["to_display"],
            entry["channel_label"],
            entry["message"],
            entry["entry_type"],
        ])
    return output.getvalue()


def build_ics309_text(session, entries):
    lines = ["ICS 309-style communications log", *session_lines(session), ""]
    for entry in entries:
        lines.append(f"{entry['timestamp']} | {entry['from_display']} -> {entry['to_display']} | {entry['channel_label']} | {entry['entry_type']}")
        lines.append(entry["message"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_ics214_csv(session, entries):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ICS 214-style activity log"])
    write_session_rows(writer, session)
    writer.writerow([])
    writer.writerow(["Activity Date/Time", "Activity/Event Description", "Notable Decisions/Actions", "Notes"])
    for entry in entries:
        writer.writerow([entry["timestamp"], entry["entry_type"], entry["message"], entry["source"]])
    return output.getvalue()


def build_ics214_text(session, entries):
    lines = ["ICS 214-style activity log", *session_lines(session), ""]
    for entry in entries:
        lines.append(f"{entry['timestamp']} | {entry['entry_type']}")
        lines.append(entry["message"])
        lines.append(f"Source: {entry['source']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_session_rows(writer, session):
    for label, value in session_field_pairs(session):
        writer.writerow([label, value])


def session_lines(session):
    return [f"{label}: {value}" for label, value in session_field_pairs(session)]


def session_field_pairs(session):
    return [
        ("Incident/Event Name", session["event_name"]),
        ("Operational Period", session["operational_period"]),
        ("Net Name", session["net_name"]),
        ("Operator/Callsign", f"{session['operator_name']} {session['operator_callsign']}".strip()),
        ("Station ID", session["station_id"]),
        ("Station Tactical Callsign", session["station_tactical_callsign"]),
        ("Start Time", session["start_time"]),
        ("End Time", session["end_time"] or ""),
        ("Status", session["status"]),
    ]
