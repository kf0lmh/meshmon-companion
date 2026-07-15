# FieldStation Implementation Plan

FieldStation is a new offline-first kiosk/operator app. It is intended for one laptop or desktop PC connected to one local
Meshtastic-style node over USB serial. The first useful milestone is a local
fullscreen interface that remains useful without internet or a connected node,
stores its own operating history in its own database, and provides chat,
monitoring, waypoints, and net logging.

FieldStation does not need to run alongside upstream MeshMonitor. It should
reuse MeshMon Companion's installer, service, USB discovery, local web UI, and
packaging patterns where practical, but it should not depend on MeshMonitor for
runtime behavior or persistence.

## Current Source of Truth

FieldStation is the active product direction. Current installs intentionally
keep compatibility paths and command names such as `/opt/meshmon-companion`,
`/etc/meshmon-companion`, `meshmon-companion.service`, and
`meshmon-companion` until a dedicated `/opt/fieldstation` migration is designed
and tested. Treat those paths as compatibility surfaces, not product identity.

Phase 6C status:

- FieldStation is its own service, API, UI, and SQLite database.
- FieldStation-only install/update is the recommended deployment path for new
  kiosk/operator systems. Optional compatibility tooling is explicit and not
  required for FieldStation runtime.
- The adapter is read-only USB only. It may read safe local node status, known
  node summaries, telemetry fields, and channel slot metadata.
- Channel keys and PSK material are not exposed; channel metadata reports only
  slot index, role, and whether a PSK is present.
- `/api/status` and healthcheck must separate FieldStation app/database health
  from read-only adapter state.
- `tx_available` and `message_receipts_available` must remain `false` until a
  later phase implements and proves live transmit/receipt behavior.
- Sending remains a local queue action only. No node config writes, channel
  programming, MQTT enablement, firmware action, or reset behavior is in scope.
- Docker, the optional dashboard, and serial bridge containers are not required
  in FieldStation-only mode. Healthcheck reports optional compatibility health
  separately from FieldStation service/API/database health.
- Existing installs can use `fieldstation-mode status`,
  `fieldstation-mode set fieldstation-only`, and
  `fieldstation-mode set compatibility-enabled` to update install-mode config
  safely. The helper backs up config before writes and does not delete data.

## Historical Repo Findings

MeshMon Companion is currently a bootstrapper and control layer around upstream
MeshMonitor, not the MeshMonitor application itself. FieldStation should be
planned as a new app/service that can stand on its own instead of as a
MeshMonitor-dependent extension.

Relevant current structure:

- `install.sh` installs packages, discovers a USB serial node, writes config,
  renders Docker Compose, starts the stack, and enables services.
- `compose/docker-compose.yml.template` and `scripts/render-compose.sh` run
  `ghcr.io/yeraze/meshmonitor:latest` plus
  `ghcr.io/yeraze/meshtastic-serial-bridge:latest`.
- `app/server.py` is a small Python `http.server` control panel on port `8090`.
- `app/static/style.css` contains the existing local-only control panel styling.
- `scripts/healthcheck.sh` provides JSON status for Docker, MeshMonitor, serial
  detection, power, storage, and service health.
- `examples/config.example.yaml` documents the current configuration shape.

Historical Meshtastic/node integration:

- USB node discovery is implemented by `scripts/discover.sh` and used by the
  installer.
- USB mode maps the selected serial device into the serial bridge container as
  `/dev/ttyACM0`.
- The serial bridge exposes TCP port `4403` inside Docker.
- MeshMonitor is configured with `MESHTASTIC_NODE_IP` and
  `MESHTASTIC_TCP_PORT`.
- The rendered compose file also exposes MeshMonitor's virtual node port `4404`
  to the configured bind address.

Historical persistence:

- MeshMonitor data is mounted at `/opt/meshmon-companion/data/meshmonitor`.
- MeshMon Companion itself does not currently own an app database.
- FieldStation will own a separate SQLite database under
  `/opt/meshmon-companion/data/fieldstation/fieldstation.sqlite3`.

## Architecture Decision

Build FieldStation as a separate local operator app/service, while reusing
MeshMon Companion's proven installation and maintenance patterns. The existing
control panel can link to FieldStation and manage its service, but FieldStation
should not be architected as a feature that requires MeshMonitor to be running.

Recommended first service shape:

- Keep the current MeshMon Companion control panel intact.
- Add a FieldStation service with its own local web UI and API, likely on its
  own port.
- Add a control panel link to open FieldStation and a service health indicator.
- Add `/api/*` endpoints inside FieldStation for state, messages, nodes,
  callsigns, waypoints, net logs, channel profile export, and USB writer
  scaffolding.
- Add a dedicated SQLite persistence layer owned by FieldStation.
- Add an adapter boundary for node connectivity so Phase 1 can ship with a
  stable local scaffold and later phases can swap in a real Meshtastic client.
- MeshMonitor may remain installable for users who want the existing dashboard,
  but it should be optional for FieldStation.

Phase 2 adapter strategy:

- Prefer direct USB access through the Meshtastic Python client for
  FieldStation's own runtime.
- Treat the existing serial bridge/TCP path as an optional future adapter, not
  as a required MeshMonitor dependency.
- Do not claim messages were sent, rebroadcast, or ACKed unless real adapter
  evidence exists.
- Keep no-node operation healthy: no USB node means disconnected/offline, not a
  FieldStation app failure.
- Keep WSL/Windows USB serial out of the Phase 2 validation target. It has
  proven unreliable enough for this project that it should not block progress.

Phase 2B closure decision:

- FieldStation currently ships a safe adapter scaffold, not live Meshtastic
  send/receive.
- The adapter keeps USB candidate detection, configured serial path awareness,
  Meshtastic Python package detection, stale/reconnect fields, and raw adapter
  state events.
- Direct USB through the Meshtastic Python client remains the preferred future
  hardware strategy.
- Real live-node send/receive remains deferred. Read-only live USB testing is
  available only for safe status, node, telemetry, and channel metadata reads.
- No hardware, missing package, bad serial path, or serial permission problems
  are adapter conditions. They should be visible in `/api/status` and
  healthcheck output without making the FieldStation app itself look broken.
- Queued messages are local records only. `seen_by_mesh` and
  `acked_by_recipient` must remain unavailable until real adapter evidence
  exists.

The adapter should support these states from the beginning:

- `disconnected`
- `connecting`
- `connected`
- `degraded`
- `reconnecting`

Do not implement Bluetooth, Wi-Fi/hotspot, MQTT, multi-node control, cloud
sync, bootable USB images, firmware flashing, or advanced radio configuration
in the first phase.

## Proposed Files

Phase 1 should add:

- `fieldstation/server.py`
- `fieldstation/__init__.py`
- `fieldstation/db.py`
- `fieldstation/models.py`
- `fieldstation/repository.py`
- `fieldstation/adapter.py`
- `fieldstation/channel_profile.py`
- `fieldstation/render.py`
- `fieldstation/static/fieldstation.css`
- `fieldstation/static/fieldstation.js`
- `systemd/fieldstation.service`
- `docs/FIELDSTATION_PLAN.md`

Phase 1 should change:

- `app/server.py`
  - Link to the FieldStation service.
  - Show FieldStation service health when available.
- `README.md`
  - Add a short FieldStation preview section after the existing control panel
    description.
- `examples/config.example.yaml`
  - Add a `fieldstation` section with enabled flag, bind address, port,
    database path, and offline map path.
- `scripts/healthcheck.sh`
  - Add FieldStation service, port, and database path/existence status once the
    DB exists.
- `scripts/render-compose.sh` or a new render script
  - FieldStation should not require MeshMonitor containers. Decide whether it
    runs directly as a systemd Python service for MVP or as its own container.

Later phases should add:

- `fieldstation/waypoints.py`
- `fieldstation/netlog.py`
- `fieldstation/ics_export.py`
- `fieldstation/usb_writer.py`
- `fieldstation/maps.py`
- `assets/fieldstation/channel-profiles/fieldstation-default.json`
- `assets/fieldstation/usb-package/README.md`
- `assets/fieldstation/ics/`
- `data/fieldstation/maps/README.md`

## Database MVP

FieldStation owns SQLite and creates tables on startup:

- `settings`
- `connection_profiles`
- `channel_profiles`
- `messages`
- `message_status_events`
- `known_nodes`
- `node_tactical_callsigns`
- `telemetry`
- `positions`
- `waypoints`
- `pending_waypoints`
- `net_sessions`
- `net_log_entries`
- `ics_exports`
- `raw_events`

For Phase 1, implement only the tables needed for channels, messages, known
nodes, tactical callsigns, and raw events. Create the rest as empty schema only
if it keeps migrations simple.

## UI MVP

The first FieldStation screen should be a real operator surface, not a landing
page. It may be exposed as `/` on the FieldStation service and linked from the
Companion control panel as "Open FieldStation."

Layout:

- Top status bar:
  - FieldStation name.
  - connection state.
  - local node ID/name if known.
  - last packet time.
  - fullscreen/kiosk action.
- Left pane:
  - channel tabs for `All`, `0 Public`, `1 Ops`, `2 WX`, `3 NCS`,
    `4 Logistics`, `5 Relay`, `6 Tactical`, `7 Test`.
  - chat history.
  - send box.
- Right pane:
  - local node status.
  - known node list.
  - recent events.

Phase 1 can use seeded/sample local data when no node is connected, but it must
make clear that the node is disconnected and stored data is offline/stale.

## Message Status Rules

Required statuses:

- `queued_local`
- `sending_to_node`
- `sent_by_local_node`
- `seen_by_mesh`
- `acked_by_recipient`
- `failed`
- `retry_available`
- `logged`

UI labels may be friendlier, but the stored status values should stay explicit.

Important constraints:

- Do not show "seen by recipient" for normal broadcast channel messages.
- For broadcast/channel messages, `seen_by_mesh` only means there is evidence
  that at least one mesh node rebroadcast/heard the packet.
- For direct messages, `acked_by_recipient` only means a real recipient ACK was
  received if supported by the integration.
- Store every status transition in `message_status_events`.

## Tactical Callsigns

Treat tactical callsigns as local FieldStation operator labels.

Rules:

- Store callsigns by real Meshtastic node ID.
- Never overwrite or transmit node config in this phase.
- Display callsign plus real identity, for example `NCS-1 / W0ACA-Field` or
  `Shelter-2 / !abcd1234`.
- Use callsigns in chat, node list, map labels, waypoints, net logs, and exports.

## Offline Map and Waypoint Plan

Use a repo-local placeholder map surface in Phase 3, then wire in a bundled map
format such as PMTiles or MBTiles after the data asset is chosen.

Phase 3 requirements:

- No internet tiles, CDN scripts, or external map APIs.
- Lincoln County, Missouri map data must be local/bundled.
- Current Phase 3 implementation may use a clearly labeled offline placeholder
  surface while real PMTiles/MBTiles data is not yet included.
- Future map assets should live under
  `/opt/meshmon-companion/data/fieldstation/maps` and can later replace the
  placeholder without changing waypoint persistence.
- Plot local and known remote node positions.
- Mark stale positions differently from recent positions.
- Add waypoints by clicking/tapping the map.
- Store waypoints locally.
- Share waypoints as short human-readable messages.
- Parse received waypoint messages into a pending queue.

Waypoint visible format:

```text
WAYPOINT: Hwy 47 Closure
TYPE: Hazard
GPS: 39.xxxxx,-90.xxxxx
NOTE: Tree blocking both lanes
```

Current Phase 3 behavior:

- The map screen is offline-only and does not load internet tiles, online
  scripts, online fonts, or external map APIs.
- The placeholder map does not provide true click-to-coordinate projection.
  Operators use manual latitude/longitude entry until real local map data is
  bundled.
- Local waypoint create/edit/status/share behavior is persisted in the
  FieldStation SQLite database.
- Waypoint sharing queues a local message using existing message storage and
  never marks the message sent, seen by mesh, or ACKed.
- Human-readable waypoint messages can be parsed through a safe local parse/API
  path into pending waypoints. Operators must Save or Ignore; FieldStation does
  not auto-save received waypoints.
- Stored node positions can appear on the map if latitude/longitude exists in
  `known_nodes`, but no fake live telemetry is generated.

## Net Log Plan

Add Net Log mode in Phase 4.

Support:

- Start/end net session.
- Manual entries.
- Automatic entries for messages, node connect/disconnect, telemetry, GPS,
  waypoints, and notable errors.
- CSV and plain-text ICS 309-style and ICS 214-style exports first.
- PDF export only if it remains simple in the current Python stack.

Current Phase 4 behavior:

- Net sessions, log entries, and export records are stored in FieldStation's
  SQLite database.
- Operators can start and close a net session, add manual entries, view the log
  table, and generate ICS 309-style or ICS 214-style CSV/plain-text exports.
- Exports are returned by the local FieldStation API with timestamped filenames
  and tracked in `ics_exports`; FieldStation does not write to arbitrary paths.
- Automatic entries are local app events only: queued message attempts, waypoint
  creation/share, pending waypoint parse/save/ignore, and adapter state
  changes.
- Queued messages and waypoint shares are logged as local queued actions, not
  transmitted RF traffic.
- No live receive, live transmit, full ICS suite, ICS 213 workflow, or PDF form
  generation is included in this phase.

## Channel Profile Plan

Add a FieldStation default profile using all eight Meshtastic messaging slots:

- `0 Public`
- `1 Ops`
- `2 WX`
- `3 NCS`
- `4 Logistics`
- `5 Relay`
- `6 Tactical`
- `7 Test`

Rules:

- Channel 0 is primary/open.
- Channels 1-7 are private secondary channels.
- Active channels are consecutive.
- Do not force-apply or overwrite the user's node channels.
- Implement import/export first.
- Add safe apply confirmation only after the Meshtastic library support is
  verified.

## USB Writer Plan

Phase 5 adds Tools > Make FieldStation USB.

MVP behavior:

- Select a detected USB device or folder target.
- Choose an offline installer package.
- Copy FieldStation installer assets, map bundle, default channel profile,
  ICS templates/export assets, readme, setup guide, and checksums.
- Verify copied checksums.
- Show safe eject instructions.

Do not build a bootable live USB image in this phase.

Current Phase 5 behavior:

- Channel profiles are local FieldStation templates stored in
  `channel_profiles` and `channels`.
- Import/export uses a versioned JSON document with profile metadata and channel
  slot definitions. Profiles are not written to radio hardware.
- Tools > Make FieldStation USB creates a folder package only. It writes into a
  selected folder or mounted USB directory and refuses dangerous system paths,
  the repo root, and raw block-device style workflows.
- The USB package includes README/setup notes, default channel profile JSON,
  map placeholder notes, ICS export notes, `manifest.json`, `checksums.txt`,
  and optional Starter Data Bundle JSON.
- Starter Data Bundle is versioned JSON and is not a clone. It can include
  channel profile templates, map placeholder metadata, waypoint library,
  remote known nodes, remote tactical callsigns, ICS notes, and documentation.
- Starter Data Bundle excludes local station identity, local tactical callsign,
  local node identity, serial path, machine settings, messages, active sessions,
  net logs, raw events, and secrets by default.
- Import preview is available before import. Import requires explicit
  confirmation and does not overwrite local identity/settings.

## Phase Prompts For Codex

### Phase 1 Prompt

Inspect the repo and implement Phase 1 of FieldStation as its own local
operator app/service, not as a MeshMonitor-dependent extension. Reuse MeshMon
Companion's installer, systemd, USB discovery, healthcheck, and local web UI
patterns where practical. Add a dedicated SQLite persistence layer for
FieldStation messages, known nodes, tactical callsigns, channel profile data,
and raw events. Add API endpoints for status, channels, messages, nodes, and
send-message. Add a USB serial adapter boundary that reports connection states
and can run safely with no node connected. Build a fullscreen-friendly
three-pane FieldStation UI with channel tabs, chat history, send box,
connection status, local node status, known nodes, and recent events. Add a
link and service health indicator in the existing Companion control panel. Keep
it offline-first and do not use CDN assets. Update docs and provide run/test
commands.

### Phase 2 Prompt

Implement Phase 2 of FieldStation. Add message status tracking with
stored status events and UI badges. Add tactical callsign editing for known
nodes and local display everywhere node identity appears. Add reconnect and
stale-state handling to the connection model. Extend monitoring panels with
battery, GPS/position, channel/region/modem preset, last packet time,
last-heard time, node battery, RSSI/SNR, and stale/recent display where data is
available. Do not falsely show recipient receipt for broadcast messages.

### Phase 2B Closure Prompt

Close Phase 2 without requiring live hardware. Keep the adapter boundary honest:
USB candidate detection, configured serial path awareness, Meshtastic Python
package detection, stale/reconnect fields, permission warnings, raw adapter
events, and clear `/api/status` reasons should remain. Do not attempt WSL USB,
TCP live-node testing, real send/receive, Bluetooth, Wi-Fi/hotspot, MQTT,
firmware flashing, maps, waypoints, net logging, ICS exports, or USB Writer in
this pass. Document that real hardware integration is deferred until a native
Linux/Raspberry Pi/remote hardware system is available and that WSL/Windows USB
serial is not a supported validation target right now.

### Phase 3 Prompt

Implement Phase 3 of FieldStation. Add an offline Lincoln County,
Missouri map view using repo-local assets only. Add local and remote node
markers with tactical callsign labels and stale styling. Add local waypoints
with name, type, coordinates, notes, priority, status, created_by,
created_by_tactical_callsign, created_at, and shared_channel. Allow adding a
waypoint from the map, storing it locally, sharing it to a selected channel as
a short human-readable Meshtastic message, parsing received waypoint messages
into a pending queue, and saving/ignoring pending waypoints.

### Phase 4 Prompt

Implement Phase 4 of FieldStation. Add Net Log mode with start/end net
session, required session fields, manual log entries, automatic entries for
message and node events, waypoint events, telemetry, GPS/position updates, and
notable errors. Store logs locally. Add CSV and plain-text ICS 309-style
communications log and ICS 214-style activity log exports.

Phase 4 should stay offline-first and honest about current adapter limits:
automatic entries must describe local queued/app events unless real adapter
evidence exists.

### Phase 5 Prompt

Implement Phase 5 of FieldStation. Add FieldStation default channel
profile import/export using the eight-slot profile. Do not apply channel
changes to a node without explicit confirmation. Add a Tools > Make
FieldStation USB scaffold or first implementation that copies an offline
installer package, local map bundle placeholder, default channel profile, ICS
templates/export assets, readme, setup guide, and checksums to a selected
folder target or USB device. Verify checksums and show safe eject guidance.

Phase 5 closes the planned MVP feature set. Future phases should focus on
hardening, real hardware integration on a proper Linux/Raspberry Pi target, real
bundled map data, and deployment polish.

## Current Phase 6 Behavior

Phase 6A validated direct USB read-only access on a native Linux target. Phase
6B makes that path service-ready:

- FieldStation uses the Meshtastic Python client only from the managed service
  environment at `/opt/meshmon-companion/.venv-fieldstation`.
- The installed service runs as the low-privilege `meshmon` user with normal
  serial group access.
- The adapter is explicitly read-only. It may read safe local node status,
  known node summaries, telemetry fields, and channel slot metadata.
- Channel keys and PSK material are never exposed; channel metadata reports only
  slot index, role, and whether a PSK is present.
- Missing package, missing serial device, permission denied, bad serial path,
  timeout, and unsupported node responses are adapter states, not app/database
  failures.
- `/api/status` and healthcheck report app/database health separately from
  adapter health.
- Sending remains local queue only. No text transmit, waypoint transmit,
  message ACK/receipt handling, channel programming, node configuration writes,
  MQTT enablement, reset, or firmware action is implemented.

## Testing Checklist

For each phase:

- Run Python syntax checks.
- Exercise `/` and existing control panel actions enough to verify no
  regression in the companion panel.
- Exercise the FieldStation service/UI with no node connected.
- Exercise missing Meshtastic package, bad serial path, and no-hardware adapter
  states without connecting to real hardware.
- Verify the app starts with no internet.
- Verify the UI clearly shows disconnected/stale states.
- Verify SQLite database creation and persistence after restart.
- Verify docs match the actual commands and paths.
