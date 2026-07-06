#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/meshmon-companion"
BACKUP_DIR="$ROOT/backups"
STATE_DIR="$ROOT/state"
TMP_DIR="$ROOT/tmp/backup-$(date +%F_%H%M%S)"
STAMP="$(date +%F_%H%M%S)"
LABEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --label) LABEL="${2:-}"; shift 2 ;;
    *) echo "Usage: $0 [--label name]" >&2; exit 2 ;;
  esac
done

safe_label="$(printf '%s' "$LABEL" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//' | cut -c1-48)"
name="meshmon-companion-backup-${STAMP}${safe_label:+-$safe_label}.tar.gz"
archive="$BACKUP_DIR/$name"

umask 077
mkdir -p "$BACKUP_DIR" "$STATE_DIR" "$TMP_DIR"
if getent group meshmon >/dev/null 2>&1; then
  chgrp meshmon "$BACKUP_DIR" "$STATE_DIR"
  chmod 750 "$BACKUP_DIR" "$STATE_DIR"
fi
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/manifest.txt" <<EOF
timestamp=$(date -Is)
hostname=$(hostname)
os_version=$(grep PRETTY_NAME /etc/os-release | cut -d= -f2- | tr -d '"')
kernel=$(uname -r)
architecture=$(uname -m)
backup_label=$LABEL
meshmon_companion_version=0.1.0
include_secret_paths=false
included_files=/etc/meshmon-companion/config.yaml,/opt/meshmon-companion/docker-compose.yml
EOF

tar -czf "$TMP_DIR/$name" -C "$TMP_DIR" manifest.txt -C / \
  etc/meshmon-companion/config.yaml \
  opt/meshmon-companion/docker-compose.yml \
  opt/meshmon-companion/data 2>"$TMP_DIR/tar-warnings.log" || true
mv "$TMP_DIR/$name" "$archive"
if getent group meshmon >/dev/null 2>&1; then
  chgrp meshmon "$archive"
  chmod 640 "$archive"
else
  chmod 600 "$archive"
fi
echo "timestamp=$(date -Is)" > "$STATE_DIR/last-backup-success"
echo "name=$name" >> "$STATE_DIR/last-backup-success"
echo "Created $archive"
