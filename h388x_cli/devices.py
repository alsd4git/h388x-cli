"""Pure helpers for the MAC-keyed device naming workflow."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .models import Client, DhcpBinding


_MAC_HEX_RE = re.compile(r"^[0-9a-fA-F]{12}$")


def norm_mac(mac: Optional[str]) -> str:
    """Normalize a MAC for comparison and imports.

    Common colon-, dash- and dot-separated representations are accepted and
    normalized to lower-case colon notation. Invalid/non-standard values are
    still returned as a trimmed lower-case string so read-only modem data is
    never silently discarded; write/import validation can reject them.
    """
    raw = (mac or "").strip()
    if not raw:
        return ""
    compact = re.sub(r"[:-]", "", raw).replace(".", "")
    if _MAC_HEX_RE.fullmatch(compact):
        return ":".join(compact[i:i + 2] for i in range(0, 12, 2)).lower()
    return raw.lower()


def is_valid_mac(mac: Optional[str]) -> bool:
    """Return whether *mac* is a conventional 48-bit MAC address."""
    normalized = norm_mac(mac)
    return bool(re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", normalized))


def _empty_device(mac: Optional[str]) -> Dict[str, Any]:
    return {
        "mac": mac,
        "hostname": None,
        "ipv4": None,
        "ipv6": None,
        "interface": None,
        "online": False,
        "reserved": False,
        "name": None,
        "reserved_ip": None,
        "reservation_id": None,
    }


def merge_devices(
    clients: List[Client],
    bindings: List[DhcpBinding],
) -> List[Dict[str, Any]]:
    """Merge connected clients with DHCP reservations, keyed by MAC.

    Each row exposes both the observed DHCP hostname and the assigned
    reservation name so the route-A distinction stays explicit. Devices
    that have a reservation but are not currently connected still show up
    (online=False), as do connected devices without a reservation.
    """
    merged: Dict[str, Dict[str, Any]] = {}

    for client in clients:
        key = norm_mac(client.mac)
        if not key:
            continue
        row = merged.setdefault(key, _empty_device(client.mac))
        row["online"] = True
        row["hostname"] = client.hostname or row["hostname"]
        row["ipv4"] = client.ipv4 or row["ipv4"]
        row["ipv6"] = client.ipv6 or row["ipv6"]
        row["interface"] = client.interface or row["interface"]

    for binding in bindings:
        key = norm_mac(binding.mac)
        if not key:
            continue
        row = merged.setdefault(key, _empty_device(binding.mac))
        row["reserved"] = True
        row["name"] = binding.name or row["name"]
        row["reserved_ip"] = binding.ip_address or row["reserved_ip"]
        row["reservation_id"] = binding.id or row["reservation_id"]
        if not row["ipv4"]:
            row["ipv4"] = binding.ip_address

    return list(merged.values())


def reservations_export(bindings: List[DhcpBinding]) -> List[Dict[str, str]]:
    """Build the portable ``[{mac, ip, name}]`` export from reservations.

    Only reservations with a MAC are exported. Sorted by IP for stable,
    diff-friendly output.
    """
    out = [
        {
            "mac": norm_mac(binding.mac),
            "ip": binding.ip_address or "",
            "name": binding.name or "",
        }
        for binding in bindings
        if binding.mac
    ]
    return sorted(out, key=lambda row: row["ip"])


def plan_import(
    entries: List[Dict[str, Any]],
    bindings: List[DhcpBinding],
) -> List[Dict[str, Any]]:
    """Compute an idempotent, validation-first import plan keyed by MAC.

    For each ``{mac, ip, name}`` entry, decide the action against current
    reservations. Duplicate MACs and malformed/non-object entries are emitted
    as ``error`` items so callers can refuse the whole plan before writing.
    """
    by_mac = {norm_mac(binding.mac): binding for binding in bindings if binding.mac}
    plan: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            plan.append({
                "action": "error",
                "error": f"entry {index} must be an object",
                "mac": "",
                "ip": "",
                "name": "",
                "id": None,
                "old_name": None,
                "old_ip": None,
            })
            continue

        mac = (entry.get("mac") or "").strip()
        ip = (entry.get("ip") or "").strip()
        name = (entry.get("name") or "").strip()
        key = norm_mac(mac)

        item: Dict[str, Any] = {
            "mac": key or mac,
            "ip": ip,
            "name": name,
            "id": None,
            "old_name": None,
            "old_ip": None,
        }

        if not key:
            item["action"] = "error"
            item["error"] = "missing mac"
            plan.append(item)
            continue
        if not is_valid_mac(key):
            item["action"] = "error"
            item["error"] = f"invalid mac: {mac!r}"
            plan.append(item)
            continue
        if key in seen:
            item["action"] = "error"
            item["error"] = f"duplicate mac in import: {key}"
            plan.append(item)
            continue
        seen.add(key)

        existing = by_mac.get(key)
        if existing is None:
            if not ip:
                item["action"] = "error"
                item["error"] = "missing ip for new reservation"
            else:
                item["action"] = "add"
            plan.append(item)
            continue

        item["id"] = existing.id
        item["old_name"] = existing.name or ""
        item["old_ip"] = existing.ip_address or ""
        target_ip = ip or (existing.ip_address or "")
        item["ip"] = target_ip
        if (existing.name or "") == name and (existing.ip_address or "") == target_ip:
            item["action"] = "unchanged"
        else:
            item["action"] = "edit"
        plan.append(item)

    return plan
