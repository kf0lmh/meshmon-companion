#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${FIELDSTATION_ENV_FILE:-/etc/default/fieldstation}"
BIND="${FIELDSTATION_BIND:-127.0.0.1}"
PORT="${FIELDSTATION_PORT:-8091}"

if [[ -r "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  BIND="${FIELDSTATION_BIND:-$BIND}"
  PORT="${FIELDSTATION_PORT:-$PORT}"
fi

case "$BIND" in
  ""|"0.0.0.0"|"::") HOST="127.0.0.1" ;;
  *) HOST="$BIND" ;;
esac

URL="http://$HOST:$PORT/"

if [[ "${1:-}" == "--print-url" ]]; then
  printf '%s\n' "$URL"
  exit 0
fi

if command -v xdg-open >/dev/null 2>&1 && { [[ -n "${DISPLAY:-}" ]] || [[ -n "${WAYLAND_DISPLAY:-}" ]]; }; then
  exec xdg-open "$URL"
fi

printf 'FieldStation URL: %s\n' "$URL"
printf 'No graphical session was detected for automatic browser launch.\n'
