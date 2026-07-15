import glob
import importlib.util
import os
import stat
from datetime import datetime, timezone
from importlib import metadata


STALE_SECONDS = 180


class NodeAdapter:
    """Connection boundary for local Meshtastic node access.

    Phase 2 chooses direct USB through the Meshtastic Python library as the
    preferred real adapter strategy, but keeps the runtime safe when the library
    or hardware is absent. Real send/receive remains gated until the dependency
    and hardware path are installed and explicitly enabled.
    """

    def __init__(self, configured_port="", previous_status=None):
        self.configured_port = configured_port
        self.previous_status = previous_status or {}
        self.connection_type = os.environ.get("FIELDSTATION_CONNECTION_TYPE", "usb").strip().lower() or "usb"
        self.node_host = os.environ.get("FIELDSTATION_NODE_HOST", "").strip()
        self.node_port = positive_int(os.environ.get("FIELDSTATION_NODE_PORT"), 4403)
        self.client_enabled = truthy(os.environ.get("FIELDSTATION_ENABLE_MESHTASTIC", "0"))
        self.tx_enabled = truthy(os.environ.get("FIELDSTATION_TX_ENABLED", "0"))
        self.autodetect_enabled = truthy(os.environ.get("FIELDSTATION_SERIAL_AUTODETECT", "1"))
        self.read_timeout = positive_int(os.environ.get("FIELDSTATION_MESHTASTIC_READ_TIMEOUT"), 12)
        self.cache_seconds = positive_int(os.environ.get("FIELDSTATION_ADAPTER_CACHE_SECONDS"), 30)

    def status(self):
        if self.connection_type == "tcp":
            return self.tcp_status()

        serial_ports = discover_serial_ports() if self.autodetect_enabled else []
        selected_port = self.configured_port or (serial_ports[0] if serial_ports else "")
        now = utc_now()
        dependency = meshtastic_dependency()
        previous_state = self.previous_status.get("state")
        reconnect_attempts = int(self.previous_status.get("reconnect_attempts") or 0)
        last_connection_at = self.previous_status.get("last_successful_connection_at")
        last_packet_at = self.previous_status.get("last_packet_at")

        serial_warning = serial_port_warning(selected_port) if selected_port and os.path.exists(selected_port) else ""
        if self.configured_port and not os.path.exists(self.configured_port):
            state = "degraded"
            reason = "configured_serial_missing"
            detail = f"Configured serial path was not found: {self.configured_port}"
            error = "Check FIELDSTATION_SERIAL_PORT or leave it empty for auto-detection."
        elif not selected_port:
            state = "disconnected"
            reason = "no_hardware"
            detail = "No USB serial node candidate was detected."
            error = "Live node features are unavailable until hardware is connected on a supported system."
        elif serial_warning:
            state = "degraded"
            reason = "serial_permission"
            detail = f"Serial path is detected but not readable/writable: {selected_port}"
            error = serial_warning
        elif not dependency["available"]:
            state = "degraded"
            reason = "missing_meshtastic_package"
            detail = "USB candidate detected, but the Meshtastic Python client is not installed."
            error = "Install or repair the FieldStation Python environment."
        elif not self.client_enabled:
            state = "degraded"
            reason = "real_adapter_disabled"
            detail = "USB candidate and Meshtastic client are available, but real adapter mode is intentionally disabled."
            error = "Live testing is deferred until a native Linux/Raspberry Pi hardware target is available."
        else:
            cached = self.cached_status(now)
            if cached:
                return cached
            return self.read_meshtastic_status(selected_port, serial_ports, dependency, now)

        if state in ("connecting", "reconnecting"):
            reconnect_attempts += 1
        elif state == "connected":
            last_connection_at = now

        stale = is_stale(last_packet_at)
        return {
            "state": state,
            "previous_state": previous_state,
            "connection_type": "usb",
            "adapter_strategy": "direct_usb_meshtastic_python",
            "selected_port": selected_port,
            "detected_ports": serial_ports,
            "serial_autodetect_enabled": self.autodetect_enabled,
            "dependency": dependency,
            "real_client_enabled": self.client_enabled,
            "adapter_mode": "read_only_usb",
            "read_only": True,
            "live_mode_available": False,
            "read_only_live_available": False,
            "telemetry_live": False,
            "tx_available": False,
            "message_receipts_available": False,
            "reason": reason,
            "permission_warning": serial_warning,
            "reconnect_attempts": reconnect_attempts,
            "last_successful_connection_at": last_connection_at,
            "last_successful_read_at": self.previous_status.get("last_successful_read_at"),
            "last_error": error,
            "last_packet_at": last_packet_at,
            "stale": stale,
            "offline": state != "connected",
            "error": error,
            "detail": detail,
            "local_node": {
                "node_id": "!fieldstation-local",
                "node_name": "Local operator",
                "short_name": "LOCAL",
                "is_local": True,
                "tactical_callsign": "",
                "firmware_version": None,
                "app_version": None,
                "battery_level": None,
                "voltage": None,
                "charging_state": None,
                "gps_status": "unknown",
                "latitude": None,
                "longitude": None,
                "region": None,
                "modem_preset": None,
                "current_channel": None,
            },
            "updated_at": now,
        }

    def tcp_status(self):
        now = utc_now()
        dependency = meshtastic_dependency()
        previous_state = self.previous_status.get("state")
        last_packet_at = self.previous_status.get("last_packet_at")
        reconnect_attempts = int(self.previous_status.get("reconnect_attempts") or 0)

        if not self.node_host:
            state = "degraded"
            reason = "tcp_host_missing"
            detail = "TCP node adapter mode is selected, but no node host is configured."
            error = "Set FIELDSTATION_NODE_HOST or serial.tcp_host in config."
        elif not dependency["available"] or not dependency["tcp_interface_available"]:
            state = "degraded"
            reason = "missing_meshtastic_package"
            detail = "TCP node adapter selected, but the Meshtastic Python client is not installed."
            error = "Install or repair the FieldStation Python environment."
        elif not self.client_enabled:
            state = "degraded"
            reason = "real_adapter_disabled"
            detail = "TCP node adapter is configured, but real adapter mode is intentionally disabled."
            error = "Enable FIELDSTATION_ENABLE_MESHTASTIC only for deliberate read-only testing."
        else:
            cached = self.cached_status(now)
            if cached:
                cached["connection_type"] = "tcp"
                cached["adapter_strategy"] = "tcp_meshtastic_python"
                cached["adapter_mode"] = self.live_adapter_mode("tcp")
                cached["selected_port"] = f"{self.node_host}:{self.node_port}"
                return cached
            return self.read_meshtastic_status_tcp(dependency, now)

        if state in ("connecting", "reconnecting"):
            reconnect_attempts += 1
        stale = is_stale(last_packet_at)
        return {
            "state": state,
            "previous_state": previous_state,
            "connection_type": "tcp",
            "adapter_strategy": "tcp_meshtastic_python",
            "selected_port": f"{self.node_host}:{self.node_port}" if self.node_host else "",
            "detected_ports": [],
            "serial_autodetect_enabled": False,
            "dependency": dependency,
            "real_client_enabled": self.client_enabled,
            "adapter_mode": "read_only_tcp",
            "read_only": True,
            "live_mode_available": False,
            "read_only_live_available": False,
            "telemetry_live": False,
            "tx_available": False,
            "message_receipts_available": False,
            "reason": reason,
            "permission_warning": "",
            "reconnect_attempts": reconnect_attempts,
            "last_successful_connection_at": self.previous_status.get("last_successful_connection_at"),
            "last_successful_read_at": self.previous_status.get("last_successful_read_at"),
            "last_error": error,
            "last_packet_at": last_packet_at,
            "stale": stale,
            "offline": state != "connected",
            "error": error,
            "detail": detail,
            "local_node": fallback_local_node(),
            "known_nodes": [],
            "read_only_channels": [],
            "updated_at": now,
        }

    def cached_status(self, now):
        if self.cache_seconds <= 0 or self.previous_status.get("state") != "connected":
            return None
        updated_at = self.previous_status.get("updated_at")
        if not updated_at or is_stale_seconds(updated_at, self.cache_seconds):
            return None
        cached = dict(self.previous_status)
        cached["cached"] = True
        cached["updated_at"] = now
        cached["tx_available"] = self.tx_enabled
        cached["message_receipts_available"] = False
        cached["adapter_mode"] = self.live_adapter_mode(cached.get("connection_type", "usb"))
        cached["read_only"] = not self.tx_enabled
        cached["reason"] = "manual_tx_ok" if self.tx_enabled else "read_only_ok"
        cached["detail"] = self.live_adapter_detail(str(cached.get("connection_type", "usb")).upper())
        cached["offline"] = False
        return cached

    def read_meshtastic_status(self, selected_port, serial_ports, dependency, now):
        iface = None
        try:
            from meshtastic.serial_interface import SerialInterface

            iface = SerialInterface(devPath=selected_port, timeout=self.read_timeout)
            my_info = safe_call(iface.getMyNodeInfo)
            my_user = safe_call(iface.getMyUser)
            nodes = extract_known_nodes(getattr(iface, "nodes", {}) or {}, now)
            local_node = extract_local_node(my_info, my_user, now)
            if local_node["node_id"] and all(node["node_id"] != local_node["node_id"] for node in nodes):
                nodes.insert(0, local_node)
            telemetry_live = has_telemetry(local_node) or any(has_telemetry(node) for node in nodes)
            channels = extract_channels(getattr(getattr(iface, "localNode", None), "channels", None))
            return {
                "state": "connected",
                "previous_state": self.previous_status.get("state"),
                "connection_type": "usb",
                "adapter_strategy": "direct_usb_meshtastic_python",
                "adapter_mode": self.live_adapter_mode("usb"),
                "selected_port": selected_port,
                "detected_ports": serial_ports,
                "serial_autodetect_enabled": self.autodetect_enabled,
                "dependency": dependency,
                "real_client_enabled": self.client_enabled,
                "read_only": not self.tx_enabled,
                "live_mode_available": True,
                "read_only_live_available": True,
                "telemetry_live": telemetry_live,
                "tx_available": self.tx_enabled,
                "message_receipts_available": False,
                "reason": "manual_tx_ok" if self.tx_enabled else "read_only_ok",
                "permission_warning": "",
                "reconnect_attempts": 0,
                "last_successful_connection_at": now,
                "last_successful_read_at": now,
                "last_error": "",
                "last_packet_at": now,
                "stale": False,
                "offline": False,
                "error": "",
                "detail": self.live_adapter_detail("USB"),
                "local_node": local_node,
                "known_nodes": nodes,
                "read_only_channels": channels,
                "updated_at": now,
            }
        except Exception as exc:
            return {
                "state": "degraded",
                "previous_state": self.previous_status.get("state"),
                "connection_type": "usb",
                "adapter_strategy": "direct_usb_meshtastic_python",
                "adapter_mode": "read_only_usb",
                "selected_port": selected_port,
                "detected_ports": serial_ports,
                "serial_autodetect_enabled": self.autodetect_enabled,
                "dependency": dependency,
                "real_client_enabled": self.client_enabled,
                "read_only": True,
                "live_mode_available": False,
                "read_only_live_available": False,
                "telemetry_live": False,
                "tx_available": False,
                "message_receipts_available": False,
                "reason": "read_only_error",
                "permission_warning": "",
                "reconnect_attempts": int(self.previous_status.get("reconnect_attempts") or 0) + 1,
                "last_successful_connection_at": self.previous_status.get("last_successful_connection_at"),
                "last_successful_read_at": self.previous_status.get("last_successful_read_at"),
                "last_error": str(exc),
                "last_packet_at": self.previous_status.get("last_packet_at"),
                "stale": True,
                "offline": True,
                "error": str(exc),
                "detail": "Read-only Meshtastic adapter failed to read the serial node.",
                "local_node": fallback_local_node(),
                "known_nodes": [],
                "read_only_channels": [],
                "updated_at": now,
            }
        finally:
            if iface is not None:
                try:
                    iface.close()
                except Exception:
                    pass

    def read_meshtastic_status_tcp(self, dependency, now):
        iface = None
        try:
            from meshtastic.tcp_interface import TCPInterface

            iface = TCPInterface(self.node_host, portNumber=self.node_port, timeout=self.read_timeout)
            return self.read_status_from_interface(
                iface,
                dependency,
                now,
                connection_type="tcp",
                adapter_strategy="tcp_meshtastic_python",
                adapter_mode=self.live_adapter_mode("tcp"),
                selected_port=f"{self.node_host}:{self.node_port}",
                detected_ports=[],
                serial_autodetect_enabled=False,
                detail=self.live_adapter_detail("TCP"),
            )
        except Exception as exc:
            return self.read_error_status(
                exc,
                dependency,
                now,
                connection_type="tcp",
                adapter_strategy="tcp_meshtastic_python",
                adapter_mode="read_only_tcp",
                selected_port=f"{self.node_host}:{self.node_port}",
                detected_ports=[],
                serial_autodetect_enabled=False,
                detail="Read-only Meshtastic adapter failed to read the TCP node bridge.",
            )
        finally:
            if iface is not None:
                try:
                    iface.close()
                except Exception:
                    pass

    def read_status_from_interface(
        self,
        iface,
        dependency,
        now,
        connection_type,
        adapter_strategy,
        adapter_mode,
        selected_port,
        detected_ports,
        serial_autodetect_enabled,
        detail,
    ):
        my_info = safe_call(iface.getMyNodeInfo)
        my_user = safe_call(iface.getMyUser)
        nodes = extract_known_nodes(getattr(iface, "nodes", {}) or {}, now)
        local_node = extract_local_node(my_info, my_user, now)
        if local_node["node_id"] and all(node["node_id"] != local_node["node_id"] for node in nodes):
            nodes.insert(0, local_node)
        telemetry_live = has_telemetry(local_node) or any(has_telemetry(node) for node in nodes)
        channels = extract_channels(getattr(getattr(iface, "localNode", None), "channels", None))
        return {
            "state": "connected",
            "previous_state": self.previous_status.get("state"),
            "connection_type": connection_type,
            "adapter_strategy": adapter_strategy,
            "adapter_mode": adapter_mode,
            "selected_port": selected_port,
            "detected_ports": detected_ports,
            "serial_autodetect_enabled": serial_autodetect_enabled,
            "dependency": dependency,
            "real_client_enabled": self.client_enabled,
            "read_only": not self.tx_enabled,
            "live_mode_available": True,
            "read_only_live_available": True,
            "telemetry_live": telemetry_live,
            "tx_available": self.tx_enabled,
            "message_receipts_available": False,
            "reason": "manual_tx_ok" if self.tx_enabled else "read_only_ok",
            "permission_warning": "",
            "reconnect_attempts": 0,
            "last_successful_connection_at": now,
            "last_successful_read_at": now,
            "last_error": "",
            "last_packet_at": now,
            "stale": False,
            "offline": False,
            "error": "",
            "detail": detail,
            "local_node": local_node,
            "known_nodes": nodes,
            "read_only_channels": channels,
            "updated_at": now,
        }

    def live_adapter_mode(self, transport):
        prefix = "manual_tx" if self.tx_enabled else "read_only"
        return f"{prefix}_{transport}"

    def live_adapter_detail(self, transport):
        if self.tx_enabled:
            return f"{transport} adapter is connected. Manual operator transmit is enabled; config writes and recipient ACK claims are disabled."
        return f"Read-only {transport} adapter is connected. Transmit and config writes are disabled."

    def read_error_status(
        self,
        exc,
        dependency,
        now,
        connection_type,
        adapter_strategy,
        adapter_mode,
        selected_port,
        detected_ports,
        serial_autodetect_enabled,
        detail,
    ):
        return {
            "state": "degraded",
            "previous_state": self.previous_status.get("state"),
            "connection_type": connection_type,
            "adapter_strategy": adapter_strategy,
            "adapter_mode": adapter_mode,
            "selected_port": selected_port,
            "detected_ports": detected_ports,
            "serial_autodetect_enabled": serial_autodetect_enabled,
            "dependency": dependency,
            "real_client_enabled": self.client_enabled,
            "read_only": True,
            "live_mode_available": False,
            "read_only_live_available": False,
            "telemetry_live": False,
            "tx_available": False,
            "message_receipts_available": False,
            "reason": "read_only_error",
            "permission_warning": "",
            "reconnect_attempts": int(self.previous_status.get("reconnect_attempts") or 0) + 1,
            "last_successful_connection_at": self.previous_status.get("last_successful_connection_at"),
            "last_successful_read_at": self.previous_status.get("last_successful_read_at"),
            "last_error": str(exc),
            "last_packet_at": self.previous_status.get("last_packet_at"),
            "stale": True,
            "offline": True,
            "error": str(exc),
            "detail": detail,
            "local_node": fallback_local_node(),
            "known_nodes": [],
            "read_only_channels": [],
            "updated_at": now,
        }

    def send_text(self, channel_index, body):
        status = self.status()
        if not self.tx_enabled:
            return {
                "accepted": False,
                "status": "queued_local",
                "detail": "Transmit is disabled; message remains a local queue entry only.",
                "adapter_status": status,
            }
        if status.get("state") != "connected":
            return {
                "accepted": False,
                "status": "retry_available",
                "detail": "Transmit is enabled, but no connected node adapter is available.",
                "adapter_status": status,
            }
        try:
            if self.connection_type == "tcp":
                self.send_text_tcp(channel_index, body)
            else:
                self.send_text_usb(status.get("selected_port"), channel_index, body)
            status["tx_available"] = True
            status["message_receipts_available"] = False
            return {
                "accepted": True,
                "status": "sent_by_local_node",
                "detail": "Submitted to the local node. FieldStation does not claim mesh delivery or recipient ACK.",
                "adapter_status": status,
            }
        except Exception as exc:
            status["last_error"] = str(exc)
            return {
                "accepted": False,
                "status": "retry_available",
                "detail": f"Transmit attempt failed before local node submission: {exc}",
                "adapter_status": status,
            }

    def send_text_usb(self, selected_port, channel_index, body):
        if not selected_port:
            raise ValueError("No serial port selected")
        iface = None
        try:
            from meshtastic.serial_interface import SerialInterface

            iface = SerialInterface(devPath=selected_port, timeout=self.read_timeout)
            iface.sendText(body, channelIndex=int(channel_index), wantAck=False, wantResponse=False)
        finally:
            if iface is not None:
                try:
                    iface.close()
                except Exception:
                    pass

    def send_text_tcp(self, channel_index, body):
        iface = None
        try:
            from meshtastic.tcp_interface import TCPInterface

            iface = TCPInterface(self.node_host, portNumber=self.node_port, timeout=self.read_timeout)
            iface.sendText(body, channelIndex=int(channel_index), wantAck=False, wantResponse=False)
        finally:
            if iface is not None:
                try:
                    iface.close()
                except Exception:
                    pass

def discover_serial_ports():
    ports = []
    seen_real = set()
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        for path in sorted(glob.glob(pattern)):
            if not os.path.exists(path):
                continue
            real = os.path.realpath(path)
            if real in seen_real:
                continue
            ports.append(path)
            seen_real.add(real)
    return ports


def meshtastic_dependency():
    available = importlib.util.find_spec("meshtastic") is not None
    serial_available = importlib.util.find_spec("meshtastic.serial_interface") is not None if available else False
    tcp_available = importlib.util.find_spec("meshtastic.tcp_interface") is not None if available else False
    version = None
    if available:
        try:
            version = metadata.version("meshtastic")
        except metadata.PackageNotFoundError:
            version = None
    return {
        "package": "meshtastic",
        "available": available,
        "serial_interface_available": serial_available,
        "tcp_interface_available": tcp_available,
        "version": version,
    }


def serial_port_warning(path):
    try:
        info = os.stat(path)
    except OSError as exc:
        return str(exc)
    if not stat.S_ISCHR(info.st_mode):
        return "Configured serial path is not a character device."
    if not os.access(path, os.R_OK | os.W_OK):
        return "The FieldStation service user needs read/write permission for this serial device, usually through dialout/tty group membership."
    return ""


def is_stale(timestamp):
    if not timestamp:
        return True
    try:
        checked = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - checked).total_seconds() > STALE_SECONDS
    except ValueError:
        return True


def truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def safe_call(callback):
    try:
        return callback()
    except Exception:
        return {}


def fallback_local_node():
    return {
        "node_id": "!fieldstation-local",
        "node_name": "Local operator",
        "short_name": "LOCAL",
        "is_local": True,
        "tactical_callsign": "",
        "firmware_version": None,
        "app_version": None,
        "battery_level": None,
        "voltage": None,
        "charging_state": None,
        "gps_status": "unknown",
        "latitude": None,
        "longitude": None,
        "region": None,
        "modem_preset": None,
        "current_channel": None,
    }


def extract_local_node(my_info, my_user, now):
    user = my_user if isinstance(my_user, dict) and my_user else (my_info or {}).get("user", {})
    metrics = (my_info or {}).get("deviceMetrics", {})
    position = (my_info or {}).get("position", {})
    node = node_from_parts(user.get("id") or node_id_from_num((my_info or {}).get("num")), user, metrics, position, now)
    node["is_local"] = True
    return node


def extract_known_nodes(nodes, now):
    results = []
    if not isinstance(nodes, dict):
        return results
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        user = node.get("user", {}) or {}
        metrics = node.get("deviceMetrics", {}) or {}
        position = node.get("position", {}) or {}
        item = node_from_parts(user.get("id") or node_id, user, metrics, position, now)
        item["is_local"] = False
        item["rssi"] = clean_number(node.get("rssi"))
        item["snr"] = clean_number(node.get("snr"))
        results.append(item)
    return results


def node_from_parts(node_id, user, metrics, position, now):
    latitude, longitude = extract_position(position)
    return {
        "node_id": node_id or "",
        "node_name": user.get("longName") or user.get("id") or node_id or "",
        "short_name": user.get("shortName") or "",
        "is_local": False,
        "is_sample": False,
        "firmware_version": None,
        "app_version": None,
        "role": None,
        "region": None,
        "modem_preset": None,
        "current_channel": None,
        "battery_level": clean_number(metrics.get("batteryLevel")),
        "voltage": clean_number(metrics.get("voltage")),
        "charging_state": None,
        "gps_status": "known" if latitude is not None and longitude is not None else "unknown",
        "latitude": latitude,
        "longitude": longitude,
        "rssi": None,
        "snr": None,
        "last_heard_at": now,
        "hw_model": user.get("hwModel"),
    }


def node_id_from_num(num):
    try:
        return f"!{int(num):08x}"
    except (TypeError, ValueError):
        return ""


def extract_position(position):
    if not isinstance(position, dict):
        return None, None
    if position.get("latitude") is not None and position.get("longitude") is not None:
        return clean_number(position.get("latitude")), clean_number(position.get("longitude"))
    lat_i = position.get("latitudeI")
    lon_i = position.get("longitudeI")
    if lat_i is not None and lon_i is not None:
        latitude = clean_number(lat_i)
        longitude = clean_number(lon_i)
        if latitude is not None and longitude is not None:
            return latitude / 1e7, longitude / 1e7
    return None, None


def extract_channels(channels):
    results = []
    if not channels:
        return results
    for idx, channel in enumerate(channels):
        settings = getattr(channel, "settings", None)
        role = str(getattr(channel, "role", "") or "")
        try:
            index = int(getattr(channel, "index"))
        except (TypeError, ValueError):
            index = idx
        results.append({"index": index, "role": role, "psk_present": bool(getattr(settings, "psk", b""))})
    return results


def has_telemetry(node):
    return node.get("battery_level") is not None or node.get("voltage") is not None or node.get("latitude") is not None


def clean_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_stale_seconds(timestamp, seconds):
    try:
        checked = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        if checked.tzinfo is None:
            checked = checked.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - checked).total_seconds() > seconds
    except (AttributeError, ValueError):
        return True


def positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
