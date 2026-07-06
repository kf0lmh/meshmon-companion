#!/usr/bin/env bash
set -euo pipefail

paths_only=0
if [[ "${1:-}" == "--paths-only" ]]; then
  paths_only=1
fi

emit_device() {
  path="$1"
  [[ -e "$path" ]] || return 0
  real="$(readlink -f "$path" 2>/dev/null || printf '%s' "$path")"
  if [[ "$paths_only" == "1" ]]; then
    printf '%s\n' "$path"
    return
  fi
  printf 'path=%s\n' "$path"
  printf 'tty=%s\n' "$real"
  if command -v udevadm >/dev/null 2>&1; then
    udevadm info -q property -n "$real" 2>/dev/null | grep -E '^(ID_VENDOR|ID_MODEL|ID_VENDOR_ID|ID_MODEL_ID|ID_USB_DRIVER)=' || true
  fi
  printf '\n'
}

seen=""
if [[ -d /dev/serial/by-id ]]; then
  for dev in /dev/serial/by-id/*; do
    [[ -e "$dev" ]] || continue
    emit_device "$dev"
    seen="$seen $(readlink -f "$dev")"
  done
fi

for dev in /dev/ttyACM* /dev/ttyUSB*; do
  [[ -e "$dev" ]] || continue
  real="$(readlink -f "$dev")"
  [[ " $seen " == *" $real "* ]] && continue
  emit_device "$dev"
done
