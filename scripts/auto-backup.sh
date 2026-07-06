#!/usr/bin/env bash
set -euo pipefail
# Initial implementation: daily backup check. Future versions will read schedule from config.
last="/opt/meshmon-companion/state/last-backup-success"
if [[ ! -f "$last" || "$(find "$last" -mmin +1440 -print)" ]]; then
  /opt/meshmon-companion/scripts/backup-now.sh --label auto
fi
