#!/usr/bin/env bash
set -euo pipefail
find /opt/meshmon-companion/backups -maxdepth 1 -type f -name 'meshmon-companion-backup-*.tar.gz' -printf '%TY-%Tm-%Td %TH:%TM %s %f\n' 2>/dev/null | sort -r
