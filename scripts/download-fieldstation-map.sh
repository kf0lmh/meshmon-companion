#!/usr/bin/env bash
set -euo pipefail

LOCATION=""
RADIUS_MILES="10"
ZOOM_MIN="10"
ZOOM_MAX="13"
OUT="/opt/meshmon-companion/data/fieldstation/maps"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --location) LOCATION="${2:-}"; shift 2 ;;
    --radius-miles) RADIUS_MILES="${2:-}"; shift 2 ;;
    --zoom-min) ZOOM_MIN="${2:-}"; shift 2 ;;
    --zoom-max) ZOOM_MAX="${2:-}"; shift 2 ;;
    --out) OUT="${2:-}"; shift 2 ;;
    --help)
      cat <<'EOF'
Usage: download-fieldstation-map.sh --location LOCATION --radius-miles MILES [--out DIR]

Downloads a bounded local vector map package for FieldStation.
The package is stored under DIR with manifest.json, vector_map.json, and README.md.
EOF
      exit 0
      ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$LOCATION" ]]; then
  echo "Map location is required." >&2
  exit 1
fi

mkdir -p "$OUT"

python3 - "$LOCATION" "$RADIUS_MILES" "$ZOOM_MIN" "$ZOOM_MAX" "$OUT" <<'PY'
import json
import math
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

location, radius_text, zoom_min_text, zoom_max_text, out_text = sys.argv[1:6]
radius_miles = float(radius_text)
zoom_min = int(zoom_min_text)
zoom_max = int(zoom_max_text)
if radius_miles <= 0 or radius_miles > 50:
    raise SystemExit("Radius must be greater than 0 and no more than 50 miles.")
if zoom_min < 0 or zoom_max < zoom_min or zoom_max > 16:
    raise SystemExit("Zoom range must be ordered and no higher than 16.")

out = Path(out_text)
manifest_path = out / "manifest.json"
vector_path = out / "vector_map.json"
readme_path = out / "README.md"
agent = "FieldStation offline map installer (https://github.com/kf0lmh/meshmon-companion)"

def fetch_json(url, data=None, timeout=60):
    headers = {"User-Agent": agent}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

query_args = {"format": "jsonv2", "limit": "1", "q": location}
if re.fullmatch(r"\d{5}(-\d{4})?", location.strip()):
    query_args["countrycodes"] = "us"
query = urllib.parse.urlencode(query_args)
matches = fetch_json(f"https://nominatim.openstreetmap.org/search?{query}", timeout=30)
if not matches:
    raise SystemExit(f"Could not find map center for: {location}")

match = matches[0]
lat = float(match["lat"])
lon = float(match["lon"])
lat_delta = radius_miles / 69.0
cos_lat = max(0.2, math.cos(math.radians(lat)))
lon_delta = radius_miles / (69.0 * cos_lat)
bounds = {
    "north": min(85.0, lat + lat_delta),
    "south": max(-85.0, lat - lat_delta),
    "west": max(-180.0, lon - lon_delta),
    "east": min(180.0, lon + lon_delta),
    "center_latitude": lat,
    "center_longitude": lon,
}

south, west, north, east = bounds["south"], bounds["west"], bounds["north"], bounds["east"]
overpass_query = f"""
[out:json][timeout:180];
(
  way["highway"~"motorway|trunk|primary|secondary|tertiary|unclassified|residential"]({south},{west},{north},{east});
  way["waterway"~"river|stream|canal"]({south},{west},{north},{east});
  way["railway"~"rail|light_rail"]({south},{west},{north},{east});
  way["natural"="water"]({south},{west},{north},{east});
  node["place"~"city|town|village|hamlet"]({south},{west},{north},{east});
);
out tags geom;
""".strip()

endpoints = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
raw = None
errors = []
for endpoint in endpoints:
    try:
        raw = fetch_json(endpoint, data=overpass_query.encode(), timeout=240)
        break
    except urllib.error.HTTPError as exc:
        errors.append(f"{endpoint}: HTTP {exc.code}")
    except Exception as exc:
        errors.append(f"{endpoint}: {exc}")
if raw is None:
    raise SystemExit("Could not download vector map data: " + "; ".join(errors))

ROAD_PRIORITY = {
    "motorway": 10,
    "trunk": 9,
    "primary": 8,
    "secondary": 7,
    "tertiary": 6,
    "unclassified": 4,
    "residential": 3,
}

def simplify(points, max_points):
    if len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    result = points[::step]
    if result[-1] != points[-1]:
        result.append(points[-1])
    return result

def clean_tags(tags):
    return {key: str(tags[key])[:120] for key in ("name", "highway", "waterway", "railway", "natural", "place") if key in tags}

features = []
for element in raw.get("elements", []):
    tags = element.get("tags") or {}
    if element.get("type") == "node":
        place = tags.get("place")
        if place:
            features.append(
                {
                    "kind": "place",
                    "priority": {"city": 10, "town": 8, "village": 6, "hamlet": 4}.get(place, 1),
                    "label": tags.get("name", place)[:80],
                    "point": [element.get("lon"), element.get("lat")],
                    "tags": clean_tags(tags),
                }
            )
        continue
    geometry = element.get("geometry") or []
    points = [[item.get("lon"), item.get("lat")] for item in geometry if item.get("lon") is not None and item.get("lat") is not None]
    if len(points) < 2:
        continue
    highway = tags.get("highway")
    waterway = tags.get("waterway")
    railway = tags.get("railway")
    natural = tags.get("natural")
    if highway:
        priority = ROAD_PRIORITY.get(highway, 1)
        features.append({"kind": "road", "priority": priority, "points": simplify(points, 80), "tags": clean_tags(tags)})
    elif waterway:
        features.append({"kind": "waterway", "priority": 7, "points": simplify(points, 100), "tags": clean_tags(tags)})
    elif railway:
        features.append({"kind": "rail", "priority": 6, "points": simplify(points, 100), "tags": clean_tags(tags)})
    elif natural == "water":
        features.append({"kind": "water", "priority": 5, "points": simplify(points, 140), "tags": clean_tags(tags)})

features.sort(key=lambda item: (item.get("priority", 0), len(item.get("points", []))), reverse=True)
max_features = 6500
features = features[:max_features]
if not features:
    raise SystemExit("Downloaded map data did not contain usable local features.")

vector_doc = {
    "format": "fieldstation-offline-vector-map-v1",
    "bounds": bounds,
    "features": features,
}
manifest = {
    "format": "fieldstation-offline-vector-map-v1",
    "location": location,
    "display_name": match.get("display_name", location),
    "radius_miles": radius_miles,
    "zoom_min": zoom_min,
    "zoom_max": zoom_max,
    "bounds": bounds,
    "source": "OpenStreetMap vector data via Overpass",
    "attribution": "Map data copyright OpenStreetMap contributors",
    "internet_required_at_runtime": False,
    "vector_path": "vector_map.json",
    "features_downloaded": len(features),
    "raw_elements_seen": len(raw.get("elements", [])),
    "errors": errors,
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
vector_path.write_text(json.dumps(vector_doc, separators=(",", ":")) + "\n")
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
readme_path.write_text(
    "# FieldStation Offline Map Package\n\n"
    f"Location: {manifest['display_name']}\n\n"
    f"Radius: {radius_miles} miles\n\n"
    f"Features: {len(features)}\n\n"
    "Runtime internet is not required for this package. Attribution: Map data "
    "copyright OpenStreetMap contributors.\n"
)
print(json.dumps({"manifest": str(manifest_path), "features_downloaded": len(features), "raw_elements_seen": len(raw.get("elements", [])), "errors": len(errors)}))
PY
