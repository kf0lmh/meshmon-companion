# FieldStation

FieldStation is an offline-first local operator terminal for a laptop, desktop,
or small Linux host connected to one local Meshtastic-style node. It owns its
own local web service, API, SQLite database, and operator UI, and it remains
useful with no internet and no node connected.

Current installs still use compatibility paths and command names from the
original MeshMonCompanion bootstrapper, including `/opt/meshmon-companion`,
`/etc/meshmon-companion`, `meshmon-companion.service`, and the
`meshmon-companion` command. Those names are compatibility surfaces, not the
long-term product identity. A future migration to `/opt/fieldstation` should be
done only after backup, restore, update, and rollback behavior is tested.

Typical use:

- Install FieldStation using the current compatibility installer.
- Open FieldStation on port `8091`.
- Use the host control panel on port `8090` for service health, backups, and
  approved maintenance actions.
- Keep messages, node labels, waypoints, net logs, and channel profile
  templates in FieldStation's own local database.

## Compatibility Context

MeshMonitor is created and maintained by Yeraze:

- MeshMonitor: https://github.com/Yeraze/meshmonitor
- Project site: https://meshmonitor.org/

This repository began as an installer and control layer around MeshMonitor. The
FieldStation direction is separate: FieldStation does not require upstream
MeshMonitor to be running, and its database is independent. The older
MeshMonitor dashboard and serial bridge stack may remain available as optional
compatibility tooling while FieldStation is being hardened.

## FieldStation

FieldStation's current compatibility database path is:

```text
/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3
```

Current FieldStation scaffold provides:

- A fullscreen-friendly local operator UI on the FieldStation service port.
- Eight numbered channel tabs: `0 Public`, `1 Ops`, `2 WX`, `3 NCS`,
  `4 Logistics`, `5 Relay`, `6 Tactical`, `7 Test`.
- Local message storage with explicit status events and operator cancellation
  for queued local messages.
- An offline map view that can use an installer-downloaded local raster tile
  package, falling back to a clearly labeled coordinate placeholder.
- Local waypoint storage, editing, status tracking, and queued waypoint sharing.
- Pending received waypoint parsing from human-readable waypoint messages.
- Net Log mode with local net sessions, manual entries, automatic local app
  entries, and ICS 309-style / ICS 214-style CSV and plain-text exports.
- Channel profile template import/export for the eight-slot FieldStation
  profile, without writing anything to radio hardware.
- Tools for creating a safe folder-based FieldStation USB package with
  checksums and an optional Starter Data Bundle.
- A read-only USB/node adapter boundary that safely reports disconnected,
  degraded, connected/read-only, and stale states.
- Known node storage and locally assigned tactical callsigns.
- A link and health status from the compatibility host control panel.

FieldStation's node adapter defaults to read-only/no-transmit. On an installed
service it runs through the managed Python environment at:

```text
/opt/meshmon-companion/.venv-fieldstation
```

When enabled and a USB serial node is available, FieldStation can read safe
local node status, known nodes, telemetry fields that are already reported by
the node, and channel slot metadata. It does not change node configuration,
program channels, expose PSKs/channel keys, mark messages as seen by the mesh,
or mark recipient ACKs.

For lab or workstation testing, FieldStation can also use a deliberately
configured TCP serial bridge by setting `serial.connection_type: tcp` with
`serial.tcp_host` and `serial.tcp_port`. Node config/channel writes are not
performed.

Manual transmit can be enabled only by explicitly setting
`fieldstation.tx_enabled: true` in local config and re-rendering/restarting the
service. FieldStation never auto-transmits, never runs transmit loops, and does
not claim mesh delivery or recipient ACKs.

The installer adds the low-privilege service user to normal serial access
groups and renders read-only adapter settings into `/etc/default/fieldstation`.
No node, missing package, bad serial path, or permission problem is reported as
adapter degraded/disconnected while the FieldStation app and database can still
remain healthy. WSL/Windows USB serial testing is not a supported validation
target.

Run it from a checkout for local testing:

```bash
FIELDSTATION_DB=/tmp/fieldstation.sqlite3 FIELDSTATION_SERIAL_AUTODETECT=0 FIELDSTATION_PORT=8091 python3 fieldstation/server.py
```

Then open:

```text
http://127.0.0.1:8091/
```

The app is intentionally useful with no node connected. Queued messages,
tactical callsigns, the node directory, channel profile rows, and status/event
tracking are stored locally. Queued messages are clearly marked as local only
until a real adapter accepts them from the local node. Operators can cancel
queued/retry messages from the chat view to remove them from the active local
send queue while preserving the status history.

Phase 3 map and waypoint behavior:

- The map screen is offline-only. During first interactive install, the
  installer asks for a map center location/address and radius, then downloads a
  bounded local OpenStreetMap raster tile package under
  `/opt/meshmon-companion/data/fieldstation/maps`.
- If no package is configured or the download fails, FieldStation falls back to
  a clearly labeled coordinate placeholder.
- No CDN scripts, online fonts, internet tiles, or external map APIs are used.
- Runtime map display uses only local files served by FieldStation.
- Installed local map packages can be panned and zoomed inside the FieldStation
  map view.
- Future bundled PMTiles, MBTiles, or similar assets should also live under the
  same map directory.
- Sharing a waypoint creates a queued local message in the existing
  human-readable format. It is not marked sent, seen by mesh, or ACKed.
- Received waypoint parsing is available through local FieldStation APIs and
  pending waypoint UI only; parsed waypoints are not auto-saved.

Phase 4 net log behavior:

- Net Log mode stores local net sessions and log entries in FieldStation's
  SQLite database.
- Operators can start/end a net session and add manual entries for voice,
  field, or radio activity that happens outside FieldStation.
- FieldStation automatically logs local app events where practical, including
  queued local messages, waypoint create/share activity, pending waypoint
  decisions, and adapter state changes.
- Exports are generated locally through the FieldStation API as timestamped
  downloadable content and tracked in the `ics_exports` table.
- CSV and plain-text exports are labeled as ICS 309-style communications logs
  and ICS 214-style activity logs. They are not official PDF form layouts.
- Queued messages and waypoint shares remain local-only until future real
  Meshtastic send/receive integration exists.

Phase 5 profile and USB package behavior:

- Channel profiles are local FieldStation templates only. They are not applied
  to a connected node in this phase.
- The default profile uses `0 Public`, `1 Ops`, `2 WX`, `3 NCS`,
  `4 Logistics`, `5 Relay`, `6 Tactical`, and `7 Test`.
- Channel profile import/export uses versioned JSON. Sensitive channel material
  is excluded/redacted by default.
- Tools > Make FieldStation USB writes only into a selected folder or already
  mounted USB directory. It does not format drives, erase files, write raw block
  devices, or create a bootable OS image.
- The package includes setup notes, default channel profile JSON, map/ICS
  placeholders, manifest data, checksums, and optionally a Starter Data Bundle.
- Starter Data Bundle export is versioned JSON and is not a clone. It excludes
  local station identity, local tactical callsign, serial paths, machine
  settings, message history, net logs, raw events, and secrets by default.
- Checksums can be verified from `checksums.txt` or through the local USB Writer
  verify API.

Install/update behavior:

- FieldStation runs as the low-privilege `meshmon` service user.
- The installer creates/updates `/opt/meshmon-companion/.venv-fieldstation`
  from `fieldstation/requirements.txt` for the read-only USB adapter.
- The `meshmon` service user is added to `dialout` and `tty` when those groups
  exist, so USB serial devices can be read without chmod hacks.
- FieldStation-only mode is the recommended default for new kiosk/operator
  systems. It does not require Docker, the optional dashboard, or serial bridge
  containers.
- Runtime data under `/opt/meshmon-companion/data` is preserved during updates.
- Uninstall stops/disables `fieldstation.service` and removes the systemd unit,
  but leaves `/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3`
  in place unless the operator removes the data directory manually.

## Quick Install

Logged one-command FieldStation-only install:

```bash
curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh -o /tmp/fieldstation-install.sh && sudo bash /tmp/fieldstation-install.sh --fieldstation-only
```

The installer prints a log path at startup. By default it writes to:

```text
/tmp/meshmon-companion-install-YYYY-MM-DD_HHMMSS.log
```

Review-first install:

```bash
curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh -o install.sh
less install.sh
sudo bash install.sh
```

For a non-interactive FieldStation-only install:

```bash
sudo bash install.sh --non-interactive --fieldstation-only
```

Optional compatibility tooling can still be installed for hosts that need it:

```bash
sudo bash install.sh
```

## What You Get

- FieldStation local service, API, UI, and SQLite database
- Managed FieldStation Python environment for the read-only USB adapter
- Local host maintenance/control panel
- Linux desktop launcher and `fieldstation-open` browser opener when a GUI is
  available; headless hosts print the local URL instead
- Optional compatibility Docker stack only when selected
- SSH-friendly terminal menu: `companion-menu`
- Health, backup, restore, diagnostics, and restart scripts
- systemd services and timers
- Tight sudoers rules for approved scripts only
- An interactive first-run setup wizard

## Main Commands

```bash
fieldstation-open
meshmon-companion status
companion-menu
meshmon-companion menu
meshmon-companion health
meshmon-companion doctor
meshmon-companion doctor --privacy
meshmon-companion backup
meshmon-companion restore --dry-run BACKUP_FILE
meshmon-companion update
meshmon-companion uninstall
```

`doctor` prints a single troubleshooting report with config, service status,
Docker containers, listening ports, URL checks, and recent logs. Use `--privacy`
before sharing output publicly; it redacts IP addresses, MAC addresses, and
obvious secret fields.

## Installer Options

The normal installer runs an interactive wizard. Use `--non-interactive` only
for conservative default installs where prompts are not possible.

```bash
./install.sh --help
./install.sh --dry-run
./install.sh --update
./install.sh --uninstall
./install.sh --non-interactive
./install.sh --fieldstation-only
./install.sh --update --fieldstation-only
```

At the end of install or update, the installer prints the detected access URLs,
FieldStation service name, database path, environment path, managed Python
environment path, health status, and optional compatibility status when that
stack is enabled.

## Changing Install Mode

Existing installs can be marked as FieldStation-only or compatibility-enabled
without hand-editing the local config:

```bash
fieldstation-mode status
sudo fieldstation-mode set fieldstation-only --dry-run
sudo fieldstation-mode set fieldstation-only
sudo fieldstation-mode set compatibility-enabled
```

The helper changes only local config keys, creates a timestamped backup before
writing, and preserves FieldStation data, optional compatibility data, backups,
and unknown config keys. Run the follow-up update command printed by the helper
to apply service changes.

## Security Defaults

FieldStation is meant to be safe by default for small field deployments:

- No credentials, Wi-Fi passwords, Tailscale auth keys, SSH keys, logs, or
  generated local configs are included in this repository.
- MQTT and MQTT rebroadcasting are disabled unless explicitly enabled.
- Admin tools are not exposed publicly by default.
- FieldStation runs as a low-privilege `meshmon` service user.
- The web app can call only whitelisted scripts through exact sudoers entries.
- There is no raw terminal, generic service manager, unrestricted file browser,
  or arbitrary command execution in the web panel.

## Access Modes

FieldStation's host services are designed around controlled admin exposure:

- Tailscale-only when Tailscale is installed and selected
- Localhost-only as the safest non-Tailscale default
- LAN-only when explicitly selected
- All interfaces only when explicitly selected and understood

Compatibility serial bridge ports stay Docker-internal unless the user
explicitly opts into host exposure.

## Updating a Checkout

If you installed from a cloned checkout, pull updates as the normal login user.
Do not run `sudo git pull`; that can leave root-owned files inside `.git` and
break later pulls.

```bash
cd ~/meshmon-companion
git pull
sudo ./install.sh --update
```

If a previous `sudo git pull` caused permission errors, repair ownership once:

```bash
cd ~
sudo chown -R "$USER:$USER" meshmon-companion
cd ~/meshmon-companion
git pull
sudo ./install.sh --update
```

## Supported Systems

- Raspberry Pi OS
- Debian-based Raspberry Pi systems
- systemd-based Linux
- ARM or x86_64 architectures supported by Docker images

## USB Node Discovery

The installer discovers USB serial candidates from:

- `/dev/serial/by-id/`
- `/dev/ttyACM*`
- `/dev/ttyUSB*`

Stable `/dev/serial/by-id/` paths are preferred. If no device is found,
installation stops with troubleshooting guidance. If multiple devices are found,
the installer prompts for selection.

The wizard can also use an existing TCP serial bridge or skip node detection so
configuration can be completed later.

## Optional Tailscale and Wi-Fi

The installer can optionally install/configure Tailscale using the official
Tailscale install flow. It does not store Tailscale auth keys.

The installer can optionally configure Wi-Fi when NetworkManager and `nmcli` are
available. Wi-Fi passwords are not printed in logs by the installer.

## MQTT

MQTT is disabled by default. MQTT rebroadcasting is disabled by default.

If MQTT is enabled in the wizard, the broker and username are written to the
local generated config and the password/token is written to a root-owned secret
file with restrictive permissions. MQTT rebroadcasting shows an explicit
warning because it can increase mesh traffic and affect battery or solar nodes.

MQTT configuration storage is present in the compatibility installer. Runtime
integration should be verified for each deployment before enabling MQTT-related
features in production.

## Backups and Restore

Backups go under:

```bash
/opt/meshmon-companion/backups
```

Backups include a manifest and exclude known secret paths by default. Restore
supports dry-run and must create a pre-restore backup before destructive restore.

## Example Values

Documentation examples use safe placeholder values only:

- Hostname: `example-node`
- Node: `Example Mesh Node`
- Short name: `EXMP`
- Node ID: `!00000000`
- Documentation IP: `192.0.2.10`
- Tailscale-style example IP: `100.64.0.10`
- SSID: `ExampleSSID`
- Serial path: `/dev/serial/by-id/usb-EXAMPLE_Meshtastic_Device`
