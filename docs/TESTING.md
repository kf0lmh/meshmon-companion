# MeshMonCompanion Test Plan

## Clean Pi Happy Path

1. Flash clean Raspberry Pi OS Lite.
2. Boot the Pi and establish network access.
3. Connect one USB Meshtastic node.
4. Run the review-first installer.
5. Verify serial discovery chooses the stable `/dev/serial/by-id/` path.
6. Verify Docker and Compose are installed or detected.
7. Verify MeshMonitor starts.
8. Verify meshtastic-serial-bridge starts.
9. Verify MeshMonitor API returns OK.
10. Verify MeshMonCompanion service starts.
11. Verify backup creation and listing.
12. Verify restart scripts.
13. Verify selected access mode.
14. Verify privacy scans show no real private data.
15. Verify uninstall.
16. Verify reinstall.

## Edge Cases

- No USB device connected.
- Multiple serial devices connected.
- Tailscale not installed.
- Tailscale installed.
- Wi-Fi setup skipped.
- Wi-Fi setup selected.
- MQTT skipped.
- MQTT enabled.
- MQTT rebroadcast skipped.
- MQTT rebroadcast enabled with explicit confirmation.
- Port 8080 already in use.
- Port 8090 already in use.
- Docker already installed.
- Docker Compose plugin already installed.
- Installer re-run.

## Privacy Scan

Before publishing, run the project privacy scan from the release checklist and confirm that any matches are fake examples, generic documentation, or redaction logic only.
