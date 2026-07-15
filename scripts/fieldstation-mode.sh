#!/usr/bin/env bash
set -euo pipefail

CONFIG="${MESHMON_COMPANION_CONFIG:-/etc/meshmon-companion/config.yaml}"

if [[ ! -r "$CONFIG" && "$(id -u)" != "0" ]]; then
  if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    exec sudo -n env MESHMON_COMPANION_CONFIG="$CONFIG" "$0" "$@"
  fi
  echo "Config not readable: $CONFIG" >&2
  echo "Try: sudo fieldstation-mode $*" >&2
  exit 1
fi

python3 - "$CONFIG" "$@" <<'PY'
import argparse
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


SECTION_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:\s*(?:#.*)?)?$")
KEY_RE = re.compile(r"^([ \t]+)([A-Za-z0-9_-]+):(?:\s*(.*?))?\s*$")


def parse_args():
    parser = argparse.ArgumentParser(
        prog="fieldstation-mode",
        description="Show or change the local FieldStation install mode.",
    )
    parser.add_argument("config")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status")
    set_parser = sub.add_parser("set")
    set_parser.add_argument("mode", choices=("fieldstation-only", "compatibility-enabled"))
    set_parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command is None:
        args.command = "status"
    return args


def read_config(path):
    try:
        return path.read_text(encoding="utf-8").splitlines(keepends=True)
    except FileNotFoundError:
        raise SystemExit(f"Config not found: {path}")


def validate(lines, path):
    current = None
    seen = {}
    seen_sections = set()
    for idx, raw in enumerate(lines, start=1):
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise SystemExit(f"Config appears invalid at {path}:{idx}: tab indentation is not supported")
        if not line.startswith((" ", "\t")):
            match = SECTION_RE.match(line)
            if match:
                current = match.group(1)
                if current in ("fieldstation", "compatibility"):
                    if current in seen_sections:
                        raise SystemExit(f"Config appears invalid at {path}:{idx}: duplicate {current} section")
                    seen_sections.add(current)
                seen.setdefault(current, set())
                continue
            if ":" in line:
                current = None
                continue
            else:
                raise SystemExit(f"Config appears invalid at {path}:{idx}: expected a top-level section or key")
        if current is None:
            raise SystemExit(f"Config appears invalid at {path}:{idx}: indented key before any section")
        key_match = KEY_RE.match(line)
        if key_match:
            seen.setdefault(current, set()).add(key_match.group(2))
    return seen


def section_value(lines, section, key, default=""):
    current = None
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            match = SECTION_RE.match(line)
            current = match.group(1) if match else None
            continue
        if current == section:
            match = KEY_RE.match(line)
            if match and match.group(2) == key:
                value = (match.group(3) or "").split("#", 1)[0].strip().strip('"')
                return value
    return default


def top_value(lines, key, default=""):
    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line.startswith((" ", "\t")):
            continue
        if ":" in line and not SECTION_RE.match(line):
            current_key, value = line.split(":", 1)
            if current_key == key:
                return value.split("#", 1)[0].strip().strip('"')
    return default


def truthy(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def current_mode(lines):
    enabled = truthy(section_value(lines, "fieldstation", "enabled", "true"))
    compat = truthy(section_value(lines, "compatibility", "optional_stack_enabled", "false"))
    if not enabled:
        return "fieldstation-disabled"
    return "compatibility-enabled" if compat else "fieldstation-only"


def set_section_key(lines, section, key, value):
    output = []
    current = None
    in_section = False
    section_found = False
    key_written = False
    inserted = False

    for raw in lines:
        line = raw.rstrip("\n")
        is_top = bool(line.strip()) and not line.startswith((" ", "\t")) and not line.strip().startswith("#")
        match = SECTION_RE.match(line) if is_top else None
        if match:
            if in_section and not key_written:
                output.append(f"  {key}: {value}\n")
                key_written = True
                inserted = True
            current = match.group(1)
            in_section = current == section
            if in_section:
                section_found = True
            output.append(raw)
            continue
        if is_top:
            if in_section and not key_written:
                output.append(f"  {key}: {value}\n")
                key_written = True
                inserted = True
            current = None
            in_section = False
            output.append(raw)
            continue
        if in_section:
            key_match = KEY_RE.match(line)
            if key_match and key_match.group(2) == key:
                indent = key_match.group(1)
                output.append(f"{indent}{key}: {value}\n")
                key_written = True
                continue
        output.append(raw)

    if section_found and not key_written:
        output.append(f"  {key}: {value}\n")
        inserted = True
    elif not section_found:
        if output and not output[-1].endswith("\n"):
            output[-1] += "\n"
        if output and output[-1].strip():
            output.append("\n")
        output.append(f"{section}:\n")
        output.append(f"  {key}: {value}\n")
        inserted = True
    return output, inserted


def apply_mode(lines, compat_enabled):
    changed = []
    desired_compat = "true" if compat_enabled else "false"
    old_enabled = section_value(lines, "fieldstation", "enabled", "")
    old_compat = section_value(lines, "compatibility", "optional_stack_enabled", "")
    lines, _ = set_section_key(lines, "fieldstation", "enabled", "true")
    lines, _ = set_section_key(lines, "compatibility", "optional_stack_enabled", desired_compat)
    if old_enabled.strip().lower() != "true":
        changed.append(("fieldstation.enabled", old_enabled or "<missing>", "true"))
    if old_compat.strip().lower() != desired_compat:
        changed.append(("compatibility.optional_stack_enabled", old_compat or "<missing>", desired_compat))
    return lines, changed


def backup_path(path):
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return path.with_name(f"{path.name}.{stamp}.bak")


def write_atomic(path, lines):
    original = path.stat()
    backup = backup_path(path)
    shutil.copy2(path, backup)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        os.chmod(tmp_name, stat.S_IMODE(original.st_mode) or 0o600)
        try:
            os.chown(tmp_name, original.st_uid, original.st_gid)
        except PermissionError:
            pass
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return backup


def service_status(name):
    try:
        result = subprocess.run(["systemctl", "is-active", name], text=True, capture_output=True, timeout=3)
    except Exception:
        return "unknown"
    return result.stdout.strip() or "unknown"


def display_host(value):
    if value in ("", "0.0.0.0", "::"):
        return "127.0.0.1"
    return value


def print_status(path, lines):
    mode = current_mode(lines)
    fieldstation_enabled = section_value(lines, "fieldstation", "enabled", "true") or "true"
    compat_enabled = section_value(lines, "compatibility", "optional_stack_enabled", "false") or "false"
    bind = section_value(lines, "fieldstation", "bind", "") or top_value(lines, "control_bind", "127.0.0.1")
    port = section_value(lines, "fieldstation", "port", "") or section_value(lines, "ports", "fieldstation", "8091")
    print(f"Config: {path}")
    print("Config valid: true")
    print(f"Current install mode: {mode}")
    print(f"FieldStation enabled: {fieldstation_enabled}")
    print(f"Optional compatibility enabled: {compat_enabled}")
    print(f"FieldStation service status: {service_status('fieldstation')}")
    print(f"FieldStation URL: http://{display_host(bind)}:{port}")


def followup(mode):
    if mode == "fieldstation-only":
        return "sudo ./install.sh --update --fieldstation-only"
    return "sudo ./install.sh --update"


def main():
    args = parse_args()
    path = Path(args.config)
    lines = read_config(path)
    validate(lines, path)

    if args.command == "status":
        print_status(path, lines)
        return

    compat_enabled = args.mode == "compatibility-enabled"
    old_mode = current_mode(lines)
    new_lines, changed = apply_mode(lines, compat_enabled)
    validate(new_lines, path)
    backup = backup_path(path)
    print(f"Config: {path}")
    print(f"Old mode: {old_mode}")
    print(f"New mode: {args.mode}")
    print("Changes:")
    if changed:
        for key, old, new in changed:
            print(f"  {key}: {old} -> {new}")
    else:
        print("  none")
    print(f"Backup path: {backup}")
    print(f"Follow-up: {followup(args.mode)}")
    if args.dry_run:
        print("Dry run: no changes written")
        return
    written_backup = write_atomic(path, new_lines)
    print(f"Wrote config: {path}")
    print(f"Backup created: {written_backup}")


if __name__ == "__main__":
    main()
PY
