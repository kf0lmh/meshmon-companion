#!/usr/bin/env bash
set -euo pipefail

dry=0
if [[ "${1:-}" == "--dry-run" ]]; then dry=1; shift; fi
backup="${1:-}"
[[ -n "$backup" ]] || { echo "Usage: $0 [--dry-run] BACKUP_FILE" >&2; exit 2; }
[[ "$backup" =~ ^meshmon-companion-backup-[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}(-[A-Za-z0-9._-]+)?\.tar\.gz$ || -f "$backup" ]] || { echo "Invalid backup name" >&2; exit 2; }
path="$backup"
[[ -f "$path" ]] || path="/opt/meshmon-companion/backups/$backup"
[[ -f "$path" ]] || { echo "Backup not found" >&2; exit 1; }

echo "Manifest:"
tar -xOzf "$path" manifest.txt || true
echo
echo "Contents:"
tar -tzf "$path" | sed -n '1,120p'
if [[ "$dry" == "1" ]]; then
  echo "Dry run only. No files restored."
  exit 0
fi

/opt/meshmon-companion/scripts/backup-now.sh --label pre-restore
systemctl stop meshmon-companion.service || true
tar -C / -xzf "$path" etc/meshmon-companion/config.yaml opt/meshmon-companion/docker-compose.yml opt/meshmon-companion/data
systemctl restart meshmon-companion.service
/opt/meshmon-companion/scripts/healthcheck.sh --json
