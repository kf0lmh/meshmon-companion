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

Downloads a bounded local OpenStreetMap raster tile package for FieldStation.
The package is stored under DIR with a manifest.json and README.
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
tiles_root = out / "tiles" / "osm"
manifest_path = out / "manifest.json"
readme_path = out / "README.md"
agent = "FieldStation offline map installer (https://github.com/kf0lmh/meshmon-companion)"

def fetch_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

query = urllib.parse.urlencode({"format": "jsonv2", "limit": "1", "q": location})
matches = fetch_json(f"https://nominatim.openstreetmap.org/search?{query}")
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

def lon_to_tile_x(value, zoom):
    return int((value + 180.0) / 360.0 * (2 ** zoom))

def lat_to_tile_y(value, zoom):
    rad = math.radians(value)
    return int((1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (2 ** zoom))

jobs = []
for zoom in range(zoom_min, zoom_max + 1):
    x_min = lon_to_tile_x(bounds["west"], zoom)
    x_max = lon_to_tile_x(bounds["east"], zoom)
    y_min = lat_to_tile_y(bounds["north"], zoom)
    y_max = lat_to_tile_y(bounds["south"], zoom)
    for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
        for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
            jobs.append((zoom, x, y))

max_tiles = 1200
if len(jobs) > max_tiles:
    kept = []
    for job in jobs:
        if job[0] < zoom_max:
            kept.append(job)
    jobs = kept
    zoom_max -= 1
if len(jobs) > max_tiles:
    raise SystemExit(f"Requested area is too large for installer download ({len(jobs)} tiles). Use a smaller radius.")

downloaded = 0
skipped = 0
errors = []
for zoom, x, y in jobs:
    target = tiles_root / str(zoom) / str(x) / f"{y}.png"
    if target.exists() and target.stat().st_size > 0:
        skipped += 1
        continue
    target.parent.mkdir(parents=True, exist_ok=True)
    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    request = urllib.request.Request(url, headers={"User-Agent": agent})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            target.write_bytes(response.read())
        downloaded += 1
        time.sleep(0.08)
    except urllib.error.HTTPError as exc:
        errors.append(f"{zoom}/{x}/{y}: HTTP {exc.code}")
    except Exception as exc:
        errors.append(f"{zoom}/{x}/{y}: {exc}")

manifest = {
    "format": "fieldstation-offline-raster-tiles-v1",
    "location": location,
    "display_name": match.get("display_name", location),
    "radius_miles": radius_miles,
    "zoom_min": zoom_min,
    "zoom_max": zoom_max,
    "bounds": bounds,
    "source": "OpenStreetMap raster tiles",
    "attribution": "Map data and tiles copyright OpenStreetMap contributors",
    "internet_required_at_runtime": False,
    "tile_path": "tiles/osm/{z}/{x}/{y}.png",
    "tiles_requested": len(jobs),
    "tiles_downloaded": downloaded,
    "tiles_reused": skipped,
    "errors": errors[:25],
    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}
manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
readme_path.write_text(
    "# FieldStation Offline Map Package\n\n"
    f"Location: {manifest['display_name']}\n\n"
    f"Radius: {radius_miles} miles\n\n"
    f"Zooms: {zoom_min}-{zoom_max}\n\n"
    "Runtime internet is not required for this package. Attribution: Map data "
    "and tiles copyright OpenStreetMap contributors.\n"
)
print(json.dumps({"manifest": str(manifest_path), "tiles_downloaded": downloaded, "tiles_reused": skipped, "errors": len(errors)}))
PY
