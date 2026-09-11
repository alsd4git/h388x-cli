"""Pure helpers for the MAC-keyed device naming workflow."""

from __future__ import annotations

import ipaddress
import re
from typing import Any, Dict, List, Optional

from .errors import H388XError
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
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2)).lower()
    return raw.lower()


def is_valid_mac(mac: Optional[str]) -> bool:
    """Return whether *mac* is a conventional 48-bit MAC address."""
    normalized = norm_mac(mac)
    return bool(re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", normalized))


def _valid_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).version == 4
    except ValueError:
        return False


def _ip_sort_key(value: Optional[str]) -> tuple[int, int | str]:
    """Sort valid IPs numerically and leave unknown values stable at the end."""
    raw = value or ""
    try:
        return (0, int(ipaddress.ip_address(raw)))
    except ValueError:
        return (1, raw)


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

    Only reservations with a MAC are exported. Sorted numerically by IP for
    stable, human-friendly output.
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
    return sorted(out, key=lambda row: _ip_sort_key(row["ip"]))


def plan_import(
    entries: List[Dict[str, Any]],
    bindings: List[DhcpBinding],
) -> List[Dict[str, Any]]:
    """Compute an idempotent, validation-first import plan keyed by MAC.

    For each ``{mac, ip, name}`` entry, decide the action against current
    reservations. Malformed entries are emitted as ``error`` items so callers
    can reject the entire plan before the first modem write.
    """
    by_mac = {norm_mac(binding.mac): binding for binding in bindings if binding.mac}
    plan: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            plan.append(
                {
                    "action": "error",
                    "error": f"entry {index} must be an object",
                    "mac": "",
                    "ip": "",
                    "name": "",
                    "id": None,
                    "old_name": None,
                    "old_ip": None,
                }
            )
            continue

        mac = str(entry.get("mac") or "").strip()
        ip = str(entry.get("ip") or "").strip()
        name = str(entry.get("name") or "").strip()
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

        if not name:
            item["action"] = "error"
            item["error"] = "missing name"
            plan.append(item)
            continue
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
            item["action"] = "error"
            item["error"] = "name contains control characters"
            plan.append(item)
            continue

        existing = by_mac.get(key)
        if existing is None:
            if not ip:
                item["action"] = "error"
                item["error"] = "missing ip for new reservation"
            elif not _valid_ipv4(ip):
                item["action"] = "error"
                item["error"] = f"invalid IPv4 address: {ip!r}"
            else:
                item["action"] = "add"
            plan.append(item)
            continue

        item["id"] = existing.id
        item["old_name"] = existing.name or ""
        item["old_ip"] = existing.ip_address or ""
        target_ip = ip or (existing.ip_address or "")
        item["ip"] = target_ip
        if not target_ip or not _valid_ipv4(target_ip):
            item["action"] = "error"
            item["error"] = f"invalid IPv4 address: {target_ip!r}"
        elif (existing.name or "") == name and (existing.ip_address or "") == target_ip:
            item["action"] = "unchanged"
        else:
            item["action"] = "edit"
        plan.append(item)

    return plan


def apply_import_plan(
    api: Any, plan: List[Dict[str, Any]]
) -> tuple[bool, Dict[str, Any]]:
    """Apply a validated import plan, stopping safely on the first write failure.

    If preflight contains any ``error`` item, no modem write is attempted.
    During apply, successful writes are retained, the first failed write is
    recorded, and remaining writes are marked skipped. This makes partial
    application explicit to both human and JSON callers.
    """
    errors = [item for item in plan if item.get("action") == "error"]
    actionable = [item for item in plan if item.get("action") in {"add", "edit"}]
    if errors:
        for item in actionable:
            item["skipped"] = "preflight failed"
        return False, {
            "applied": 0,
            "failed": 0,
            "skipped": len(actionable),
            "partial": False,
            "preflight_errors": len(errors),
        }

    applied = 0
    failed = 0
    skipped = 0
    failure_seen = False

    for item in plan:
        action = item.get("action")
        if action not in {"add", "edit"}:
            continue
        if failure_seen:
            item["skipped"] = "previous write failed"
            skipped += 1
            continue

        try:
            if action == "add":
                ok, body = api.add_dhcp_reservation(
                    mac=item["mac"], ip_address=item["ip"], name=item["name"]
                )
            else:
                ok, body = api.edit_dhcp_reservation(
                    item["id"], name=item["name"], ip_address=item["ip"]
                )
        except H388XError as exc:
            ok, body = False, f"{exc.code}: {exc}"

        item["ok"] = bool(ok)
        if ok:
            applied += 1
            continue

        item["raw"] = str(body)[:200]
        failed += 1
        failure_seen = True

    ok = failed == 0
    return ok, {
        "applied": applied,
        "failed": failed,
        "skipped": skipped,
        "partial": bool(failed and applied),
        "preflight_errors": 0,
    }
