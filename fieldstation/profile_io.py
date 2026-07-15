from datetime import datetime, timezone


SCHEMA_VERSION = 1


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def profile_document(profile, include_sensitive=False):
    channels = []
    for channel in profile["channels"]:
        item = {
            "index": channel["index"],
            "name": channel["name"],
            "role": channel["role"],
            "is_private": channel["is_private"],
        }
        if channel.get("psk"):
            item["psk"] = "REDACTED"
        channels.append(item)
    return {
        "schema": "fieldstation.channel_profile",
        "schema_version": SCHEMA_VERSION,
        "exported_at": utc_now(),
        "profile": {
            "name": profile["name"],
            "description": profile["description"],
            "created_at": profile["created_at"],
            "updated_at": profile["updated_at"],
            "channels": channels,
        },
        "sensitive_material_included": False,
        "warning": "Local FieldStation template only. Sensitive material is never exported and this is not written to radio hardware.",
    }


def validate_profile_document(document):
    if not isinstance(document, dict):
        raise ValueError("Profile import must be a JSON object")
    if document.get("schema") != "fieldstation.channel_profile":
        raise ValueError("Unsupported channel profile schema")
    if int(document.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("Unsupported channel profile schema_version")
    profile = document.get("profile")
    if not isinstance(profile, dict):
        raise ValueError("profile is required")
    name = str(profile.get("name", "")).strip()
    if not name:
        raise ValueError("profile.name is required")
    channels = profile.get("channels")
    if not isinstance(channels, list) or not channels:
        raise ValueError("profile.channels must be a non-empty list")
    seen = set()
    normalized = []
    for channel in channels:
        if not isinstance(channel, dict):
            raise ValueError("Each channel must be an object")
        try:
            index = int(channel.get("index"))
        except (TypeError, ValueError):
            raise ValueError("Channel index must be a number") from None
        if index < 0 or index > 7:
            raise ValueError("Channel index must be between 0 and 7")
        if index in seen:
            raise ValueError(f"Duplicate channel index {index}")
        seen.add(index)
        name_value = str(channel.get("name", "")).strip()
        if not name_value:
            raise ValueError(f"Channel {index} name is required")
        role = str(channel.get("role") or ("primary" if index == 0 else "secondary")).strip()
        if index == 0 and role != "primary":
            raise ValueError("Channel 0 must be primary")
        if index > 0 and role == "primary":
            raise ValueError("Only channel 0 may be primary")
        normalized.append(
            {
                "index": index,
                "name": name_value[:64],
                "role": role[:32],
                "is_private": bool(channel.get("is_private")),
            }
        )
    active = sorted(seen)
    if active != list(range(min(active), max(active) + 1)) or active[0] != 0:
        raise ValueError("Active channels must be consecutive starting at 0")
    return {
        "name": name,
        "description": str(profile.get("description", "")).strip(),
        "channels": sorted(normalized, key=lambda item: item["index"]),
    }
