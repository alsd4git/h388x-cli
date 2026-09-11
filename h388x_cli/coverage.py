"""Canonical WebUI capability catalog and read-only capability summaries.

The catalog is deliberately independent from the live modem.  It describes
what the CLI knows how to read/write, while an optional discovery report marks
which endpoint tags were observed on a particular firmware instance.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import json


COVERAGE_SCHEMA_VERSION = "1"

STATUS_COVERED = "covered"
STATUS_PARTIAL = "partial"
STATUS_HAR = "har_required"
STATUS_UNAVAILABLE = "unavailable"


def _entry(
    capability_id: str,
    page: str,
    endpoints: Iterable[str],
    operation: str,
    commands: Iterable[str],
    status: str = STATUS_COVERED,
    *,
    risk: str = "none",
    note: str = "",
) -> Dict[str, Any]:
    return {
        "id": capability_id,
        "page": page,
        "endpoints": list(endpoints),
        "operation": operation,
        "commands": list(commands),
        "status": status,
        "risk": risk,
        "note": note,
    }


# Keep this list as the machine-readable source of truth for ``capabilities``.
# The narrative matrix in docs/webui-coverage.md adds firmware observations and
# rationale, but must not be used by the CLI as an input format.
COVERAGE_CATALOG: List[Dict[str, Any]] = [
    _entry("device.info", "statusMgr", ["devmgr_statusmgr_lua.lua"], "read", ["info"]),
    _entry(
        "dsl.summary",
        "dslWanStatus",
        ["dsl_interface_status_lua.lua"],
        "read",
        ["stats"],
    ),
    _entry(
        "dsl.interface",
        "dslWanStatus",
        ["dsl_interface_status_lua.lua"],
        "read",
        ["dsl-interface"],
    ),
    _entry(
        "wan.connections", "dslWanStatus", ["wan_internet_lua.lua"], "read", ["wan"]
    ),
    _entry(
        "clients.lan",
        "localNetStatus",
        ["accessdev_landevs_lua.lua"],
        "read",
        ["clients"],
    ),
    _entry(
        "clients.wifi",
        "localNetStatus",
        ["accessdev_ssiddev_lua.lua"],
        "read",
        ["clients"],
    ),
    _entry(
        "lan.public",
        "localNetStatus",
        ["publiclan_status_lua.lua"],
        "read",
        ["public-lan"],
    ),
    _entry("lan.usb", "localNetStatus", ["usb_usbdevs_lua.lua"], "read", ["usb-devs"]),
    _entry(
        "wifi.status",
        "wlanBasic",
        ["wlan_basiconoff_lua.lua", "wlan_status_lua.lua"],
        "read",
        ["wifi"],
    ),
    _entry(
        "wifi.ssid-config",
        "wlanBasic",
        ["wlan_sssidconf_lua.lua"],
        "read",
        ["wifi-ssid-config"],
    ),
    _entry(
        "wifi.advanced",
        "wlanBasic",
        ["wlan_basicadconf_lua.lua"],
        "read",
        ["wifi-advanced"],
    ),
    _entry(
        "wifi.radio-write",
        "wlanBasic",
        ["wlan_basiconoff_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
        note="Radio toggle requires an isolated live HAR.",
    ),
    _entry(
        "wifi.ssid-write",
        "wlanBasic",
        ["wlan_sssidconf_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
        note="SSID/password/visibility/client cap.",
    ),
    _entry(
        "wifi.acl",
        "wlanAdvanced",
        ["wlan_macfilteraclpolicy_lua.lua", "wlan_macfilterrule_m.lua"],
        "read",
        ["wifi-acl"],
    ),
    _entry(
        "wifi.acl-write",
        "wlanAdvanced",
        ["wlan_macfilteraclpolicy_lua.lua", "wlan_macfilterrule_m.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "wifi.schedule",
        "WlanWiFiSchedule",
        ["wlan_wifi_schedule_lua.lua"],
        "read",
        ["wifi-schedule"],
    ),
    _entry(
        "wifi.schedule-write",
        "WlanWiFiSchedule",
        ["wlan_wifi_schedule_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "wifi.band-steering",
        "wlanBssSteeringOnoff",
        ["wlan_BssSteeringOnoff_lua.lua"],
        "read",
        ["band-steering"],
    ),
    _entry(
        "wifi.band-steering-write",
        "wlanBssSteeringOnoff",
        ["wlan_BssSteeringOnoff_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "firewall.summary",
        "firewall",
        ["firewall_config_lua.lua", "firewall_dos_lua.lua"],
        "read",
        ["firewall"],
    ),
    _entry(
        "firewall.global-write",
        "firewall",
        ["firewall_config_lua.lua", "firewall_dos_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "firewall.criteria",
        "filterCriteria",
        [
            "firewall_filterglobal_m.lua",
            "firewall_ipfilter_m.lua",
            "firewall_ipfilter_priority_lua.lua",
            "firewall_urlfilter_m.lua",
        ],
        "read",
        ["firewall-ipfilter", "firewall-urlfilter"],
    ),
    _entry(
        "firewall.ipfilter-write",
        "filterCriteria",
        ["firewall_ipfilter_m.lua"],
        "write",
        ["firewall-ipfilter-add", "firewall-ipfilter-del", "firewall-ipfilter-toggle"],
        risk="reversible",
    ),
    _entry(
        "firewall.urlfilter-write",
        "filterCriteria",
        ["firewall_urlfilter_m.lua"],
        "write",
        ["firewall-urlfilter-add", "firewall-urlfilter-del"],
        risk="reversible",
    ),
    _entry("firewall.dmz", "dmzMenu", ["firewall_dmz_m.lua"], "read", ["firewall"]),
    _entry(
        "firewall.dmz-write",
        "dmzMenu",
        ["firewall_dmz_m.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "firewall.parental-control",
        "parentCtrl",
        ["firewall_parentctrl_lua.lua"],
        "read",
        ["parental-control"],
    ),
    _entry(
        "firewall.parental-control-write",
        "parentCtrl",
        ["firewall_parentctrl_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "nat.port-forward",
        "portForwardingMenu",
        ["firewall_portforwarding_m.lua"],
        "read",
        ["port-forward"],
    ),
    _entry(
        "nat.port-forward-write",
        "portForwardingMenu",
        ["firewall_portforwarding_m.lua"],
        "write",
        [
            "port-forward-add",
            "port-forward-del",
            "port-forward-toggle",
            "port-forward-edit",
        ],
        risk="sensitive",
    ),
    _entry(
        "lan.dhcp",
        "lanMgrIpv4",
        ["dhcp4s_dhcpbasiccfg_lua.lua", "dhcp4s_dhcpbinding_m.lua"],
        "read",
        ["dhcp"],
    ),
    _entry(
        "lan.dhcp-write",
        "lanMgrIpv4",
        ["dhcp4s_dhcpbinding_m.lua"],
        "write",
        ["dhcp-reserve-add", "dhcp-reserve-del", "devices"],
        risk="reversible",
    ),
    _entry(
        "lan.dns",
        "dns",
        ["dns_localdns_lua.lua", "dns_hostname_lua.lua"],
        "read",
        ["dns"],
    ),
    _entry(
        "lan.dns-host-write",
        "dns",
        ["dns_hostname_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "lan.dhcp-dns-write",
        "lanMgrIpv4",
        ["dhcp4s_dhcpbasiccfg_lua.lua"],
        "write",
        ["dns-set"],
        risk="reversible",
    ),
    _entry("lan.arp", "arpTable", ["arp_arptable_lua.lua"], "read", ["arp"]),
    _entry(
        "lan.mac-table", "macTable", ["macinfo_mactable_lua.lua"], "read", ["mac-table"]
    ),
    _entry(
        "lan.eth",
        "localNetStatus/ethWanStatus",
        ["eth_lanstatus_lua.lua", "eth_interface_status_lua.lua"],
        "read",
        ["eth"],
    ),
    _entry(
        "lan.ipv6",
        "lanMgrIpv6",
        [
            "dhcp6s_dhcpserver_lua.lua",
            "dhcp6s_hostinfo_lua.lua",
            "ra_raservice_lua.lua",
            "prefix_prefixpool_lua.lua",
            "prefix_staticprefix_lua.lua",
        ],
        "read",
        ["dhcp6", "ipv6-prefix"],
    ),
    _entry(
        "lan.ipv6-write",
        "lanMgrIpv6",
        [
            "dhcp6s_dhcpserver_lua.lua",
            "ra_raservice_lua.lua",
            "prefix_staticprefix_lua.lua",
        ],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry("lan.edns0", "smEdns0", ["edns0_lua.lua"], "read", ["edns0"]),
    _entry(
        "lan.edns0-write",
        "smEdns0",
        ["edns0_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "services.voip",
        "voipStatus/flexibleBind",
        ["voip_voipstatus_m.lua", "voip_flexiblebinding_lua.lua"],
        "read",
        ["voip"],
    ),
    _entry(
        "services.voip-media",
        "sipMedia",
        ["voip_sipmedia_lua.lua"],
        "read",
        ["voip-media"],
    ),
    _entry(
        "services.voip-pos", "posOnoff", ["voip_posonoff_lua.lua"], "read", ["voip-pos"]
    ),
    _entry(
        "services.voip-write",
        "voipStatus/sipMedia",
        [],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "services.upnp",
        "upnp",
        ["upnp_upnp_m.lua", "upnp_portmapping_lua.lua"],
        "read",
        ["upnp"],
    ),
    _entry(
        "services.upnp-write",
        "upnp",
        ["upnp_upnp_m.lua", "upnp_portmapping_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry("services.dms", "dms", ["dms_dms_lua.lua"], "read", ["dms"]),
    _entry(
        "services.dms-write",
        "dms",
        ["dms_dms_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry("services.ftp", "ftp", ["ftp_ftpserver_m.lua"], "read", ["ftp"]),
    _entry(
        "services.ftp-write",
        "ftp",
        ["ftp_ftpserver_m.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry("services.ddns", "ddns", ["ddns_lua.lua"], "read", ["ddns"]),
    _entry(
        "services.ddns-write",
        "ddns",
        ["ddns_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry("services.nanocdn", "mabrNanoCDN", ["nanocdn_lua.lua"], "read", ["nanocdn"]),
    _entry("mesh.topology", "mmTopology", ["topo_lua.lua"], "read", ["topology"]),
    _entry(
        "admin.users",
        "accountMgr",
        ["devauth_accountmgr_lua.lua"],
        "read",
        ["admin-users"],
    ),
    _entry(
        "admin.password-write",
        "accountMgr",
        ["devauth_accountmgr_lua.lua"],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "admin.web-timeout",
        "loginTimeoutMgr",
        ["web_login_timeout_lua.lua"],
        "read",
        ["web-timeout"],
    ),
    _entry(
        "admin.web-timeout-write",
        "loginTimeoutMgr",
        ["web_login_timeout_lua.lua"],
        "write",
        ["web-timeout --set"],
        risk="reversible",
    ),
    _entry(
        "admin.mobile-wan",
        "wan3gStatus",
        ["wwan_mobile_status_lua.lua"],
        "read",
        ["mobile-wan"],
    ),
    _entry("admin.sntp", "sntp (hiddenData)", ["sntp_data"], "read", ["sntp"]),
    _entry(
        "admin.sntp-write",
        "sntp (hiddenData)",
        ["sntp_data"],
        "write",
        [],
        STATUS_HAR,
        risk="reversible",
    ),
    _entry(
        "admin.config-backup",
        "usrCfgMgr",
        ["do_download_usercfg.lua"],
        "read",
        ["config backup"],
    ),
    _entry(
        "admin.config-restore",
        "usrCfgMgr",
        [],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "admin.reboot",
        "rebootAndReset",
        ["devmgr_restartmgr_lua.lua"],
        "write",
        ["reboot"],
        risk="sensitive",
    ),
    _entry(
        "admin.factory-reset",
        "rebootAndReset",
        [],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
    _entry(
        "diagnostics.ping",
        "networkDiag",
        ["networkdiag_ping_lua.lua"],
        "action",
        ["ping"],
    ),
    _entry(
        "diagnostics.traceroute",
        "networkDiag",
        ["networkdiag_traceroute_lua.lua"],
        "action",
        ["traceroute"],
    ),
    _entry(
        "diagnostics.dsl",
        "networkDiag",
        [],
        "action",
        [],
        STATUS_HAR,
        risk="none",
        note="Live UI form present; endpoint not mapped yet.",
    ),
    _entry(
        "admin.certificates",
        "Gestione Certificati",
        [],
        "read/write",
        [],
        STATUS_HAR,
        risk="sensitive",
        note="Live page present; endpoint not mapped yet.",
    ),
    _entry(
        "admin.firmware-upgrade",
        "upgrade",
        [],
        "write",
        [],
        STATUS_HAR,
        risk="sensitive",
    ),
]


def _endpoint_tags(report: Dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for endpoint in report.get("endpoints", []):
        if isinstance(endpoint, dict):
            tag = endpoint.get("tag")
            if isinstance(tag, str):
                tags.add(tag)
    return tags


def load_discovery_report(path: Path) -> Dict[str, Any]:
    """Load a local discovery JSON report and validate its top-level shape."""
    with path.open("r", encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise ValueError("discovery report must contain a JSON object")
    return report


def summarize_discovery(
    report: Dict[str, Any], path: Optional[Path] = None
) -> Dict[str, Any]:
    stats = report.get("stats")
    if not isinstance(stats, dict):
        stats = {}
    raw_device = report.get("device")
    if not isinstance(raw_device, dict):
        raw_device = {}
    device = {
        key: raw_device.get(key)
        for key in ("host", "model", "software", "hardware", "boot", "firmware_date")
        if raw_device.get(key) not in (None, "")
    }
    return {
        "path": str(path) if path is not None else None,
        "device": device,
        "stats": {
            key: stats.get(key)
            for key in (
                "requests_made",
                "errors",
                "asset_count",
                "endpoint_count",
                "endpoint_fetched",
                "endpoints_with_data",
            )
            if key in stats
        },
    }


def build_capabilities(
    device: Optional[Dict[str, Any]] = None,
    discovery: Optional[Dict[str, Any]] = None,
    discovery_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Build a stable, serial-free capabilities document."""
    tags = _endpoint_tags(discovery or {})
    capabilities: List[Dict[str, Any]] = []
    for item in COVERAGE_CATALOG:
        capability = dict(item)
        endpoints = capability.get("endpoints", [])
        capability["detected"] = bool(endpoints) and any(
            tag in tags for tag in endpoints
        )
        capabilities.append(capability)

    counts = Counter(item["status"] for item in capabilities)
    safe_device = device or {}
    device_payload = {
        key: safe_device.get(key)
        for key in ("host", "model", "software", "hardware", "boot", "firmware_date")
        if safe_device.get(key) not in (None, "")
    }
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "device": device_payload,
        "coverage": {
            "total": len(capabilities),
            "by_status": dict(sorted(counts.items())),
        },
        "capabilities": capabilities,
        "discovery": summarize_discovery(discovery, discovery_path)
        if discovery is not None
        else None,
    }
