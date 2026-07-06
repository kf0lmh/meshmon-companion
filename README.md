# MeshMonCompanion

MeshMonCompanion is a Raspberry Pi bootstrapper and companion control panel for MeshMonitor-based Meshtastic nodes.

It is intended for a clean Raspberry Pi OS / Raspberry Pi OS Lite install with a USB-connected Meshtastic node and internet access.

## What It Installs

- Docker and Docker Compose plugin if needed
- MeshMonitor
- meshtastic-serial-bridge
- MeshMonCompanion web control panel
- SSH-friendly terminal menu: `companion-menu`
- Health, backup, restore, diagnostics, and restart scripts
- systemd services and timers
- Tight sudoers rules for approved scripts only
- An interactive first-run setup wizard

## What It Does Not Do

- It does not include credentials.
- It does not include Wi-Fi passwords, Tailscale auth keys, SSH keys, logs, or generated local configs.
- It does not enable MQTT by default.
- It does not enable MQTT rebroadcasting by default.
- It does not expose admin tools publicly by default.
- It does not enable GPIO shutdown overlays by default.

## Install

Review-first method:

```bash
curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh -o install.sh
less install.sh
sudo bash install.sh
```

One-command method:

```bash
curl -fsSL https://raw.githubusercontent.com/kf0lmh/meshmon-companion/main/install.sh | sudo bash
```

Installer options:

```bash
./install.sh --help
./install.sh --dry-run
./install.sh --update
./install.sh --uninstall
./install.sh --non-interactive
```

The normal installer runs an interactive wizard. Use `--non-interactive` only for conservative default installs where prompts are not possible.

At the end of install or update, the installer prints the detected access URLs, Docker stack status, health status, and a warning if the root filesystem is too small for comfortable Docker/log/backup use.

## Updating a Checkout

For private-repo test installs, pull updates as the normal login user. Do not run `sudo git pull`; that can leave root-owned files inside `.git` and break later pulls.

```bash
cd ~/meshmon-companion
git pull
sudo ./install.sh --update
```

If a previous `sudo git pull` caused permission errors, repair ownership once:

```bash
cd ~
sudo chown -R "$USER:$USER" meshmon-companion
cd meshmon-companion
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

Stable `/dev/serial/by-id/` paths are preferred. If no device is found, installation stops with troubleshooting guidance. If multiple devices are found, the installer prompts for selection.

The wizard can also use an existing TCP serial bridge or skip node detection so configuration can be completed later.

## Access Modes

MeshMonCompanion is designed around safe admin exposure:

- Tailscale-only when Tailscale is installed and selected
- Localhost-only as the safest non-Tailscale default
- LAN-only when explicitly selected
- All interfaces only when explicitly selected and understood

The serial bridge should remain Docker-internal unless the user explicitly opts into host exposure.

## Optional Tailscale and Wi-Fi

The installer can optionally install/configure Tailscale using the official Tailscale install flow. It does not store Tailscale auth keys.

The installer can optionally configure Wi-Fi when NetworkManager and `nmcli` are available. Wi-Fi passwords are not printed in logs by the installer.

## MQTT

MQTT is disabled by default. MQTT rebroadcasting is disabled by default.

If MQTT is enabled in the wizard, the broker and username are written to the
local generated config and the password/token is written to a root-owned secret
file with restrictive permissions. MQTT rebroadcasting shows an explicit
warning because it can increase mesh traffic and affect battery or solar nodes.

MQTT configuration storage is present in this bootstrapper. Runtime integration should be verified for each MeshMonitor deployment before enabling MQTT-related features in production.

## Backups and Restore

Backups go under:

```bash
/opt/meshmon-companion/backups
```

Backups include a manifest and exclude known secret paths by default. Restore supports dry-run and must create a pre-restore backup before destructive restore.

## Security Model

The web app runs as a low-privilege `meshmon` service user. It can call only
whitelisted scripts through exact sudoers entries. There is no raw terminal,
generic service manager, unrestricted file browser, or arbitrary command
execution.

## Commands

```bash
meshmon-companion status
companion-menu
meshmon-companion menu
meshmon-companion health
meshmon-companion doctor
meshmon-companion doctor --privacy
meshmon-companion backup
meshmon-companion restore --dry-run BACKUP_FILE
meshmon-companion diagnostics --privacy
meshmon-companion update
meshmon-companion uninstall
```

`doctor` prints a single troubleshooting report with config, service status,
Docker containers, listening ports, URL checks, and recent logs. Use `--privacy`
before sharing output publicly; it redacts IP addresses, MAC addresses, and
obvious secret fields.

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
