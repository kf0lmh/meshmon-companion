DEFAULT_CHANNELS = [
    {"index": 0, "name": "Public", "role": "primary", "is_private": False},
    {"index": 1, "name": "Ops", "role": "secondary", "is_private": True},
    {"index": 2, "name": "WX", "role": "secondary", "is_private": True},
    {"index": 3, "name": "NCS", "role": "secondary", "is_private": True},
    {"index": 4, "name": "Logistics", "role": "secondary", "is_private": True},
    {"index": 5, "name": "Relay", "role": "secondary", "is_private": True},
    {"index": 6, "name": "Tactical", "role": "secondary", "is_private": True},
    {"index": 7, "name": "Test", "role": "secondary", "is_private": True},
]


def channel_label(channel):
    return f"{channel['index']} {channel['name']}"
