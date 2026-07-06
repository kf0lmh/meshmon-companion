#!/usr/bin/env bash
set -euo pipefail

ROOT="/opt/meshmon-companion"

usage() {
  cat <<'EOF'
meshmon-companion commands:
  status
  health
  backup [name]
  restore [--dry-run] BACKUP_FILE
  update
  uninstall
  menu
  doctor [--privacy]
  diagnostics [--privacy]
EOF
}

cmd="${1:-status}"
shift || true

case "$cmd" in
  status) systemctl status meshmon-companion.service --no-pager ;;
  health) sudo "$ROOT/scripts/healthcheck.sh" --json ;;
  backup) sudo "$ROOT/scripts/backup-now.sh" --label "${1:-}" ;;
  restore) sudo "$ROOT/scripts/restore-backup.sh" "$@" ;;
  update) sudo "$ROOT/update.sh" ;;
  uninstall) sudo "$ROOT/uninstall.sh" ;;
  menu) "$ROOT/scripts/companion-menu.sh" "$@" ;;
  doctor) sudo "$ROOT/scripts/doctor.sh" "$@" ;;
  diagnostics) sudo "$ROOT/scripts/diagnostics.sh" "$@" ;;
  --help|-h|help) usage ;;
  *) usage; exit 2 ;;
esac
