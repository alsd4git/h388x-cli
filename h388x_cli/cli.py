import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.text import Text

from .api import ZTEH388XAPI
from .devices import (
    apply_import_plan as _apply_import_plan,
    merge_devices as _merge_devices,
    norm_mac as _norm_mac,
    plan_import as _plan_import,
    reservations_export as _reservations_export,
)
from .discovery import Spider
from .errors import H388XError
from .discovery import compare_discovery_reports
from .coverage import build_capabilities, load_discovery_report
from .private_files import write_private_bytes as _write_private_bytes
from .models import (
    AdminUser,
    ArpEntry,
    BandSteeringState,
    Client,
    Ddns,
    DeviceInfo,
    Dhcp6Server,
    DhcpBinding,
    DhcpConfig,
    Dms,
    DSLStats,
    Dmz,
    DnsHostname,
    DnsLocal,
    DslInterface,
    EasyMeshState,
    EthInterface,
    FirewallDos,
    FirewallLevel,
    FtpServer,
    FtpUser,
    MacTableEntry,
    MobileWanInfo,
    NanoCdnStatus,
    PortForwardingRule,
    PublicLan,
    RouterAdvertisement,
    SntpConfig,
    TopologyAgent,
    TopologyController,
    UpnpConfig,
    UpnpPortMapping,
    UrlFilterGlobal,
    VoipLine,
    VoipSipLine,
    WanConnection,
    WebLoginTimeout,
    WifiAclPolicy,
    WifiAclRule,
    WifiAP,
    WifiRadio,
    WifiRadioAdvanced,
    WifiSchedule,
    WifiSsidConfig,
)

load_dotenv()

app = typer.Typer(help="H388X Modem CLI Management Tool", no_args_is_help=True)
console = Console()


# --------------------------------------------------------------------- state

class State:
    json: bool = False


state = State()


@app.callback()
def main(
    json_output: bool = typer.Option(
        False, "--json", help="Emit machine-readable JSON instead of tables."
    ),
):
    """H388X Modem CLI."""
    state.json = json_output


# ---------------------------------------------------------------- formatters

def _deci(value: Optional[int], unit: str) -> str:
    if value is None:
        return "N/A"
    return f"{value / 10:.1f} {unit}"


def _kbps(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return f"{value} kbps"


def _humanize_uptime(seconds: Optional[int]) -> str:
    if not seconds:
        return "N/A"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    return f"{days}d {hours}h {minutes}m"


def _format_firmware_date(raw: Optional[str]) -> str:
    if not raw or len(raw) != 14 or not raw.isdigit():
        return raw or "N/A"
    return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]} {raw[8:10]}:{raw[10:12]}:{raw[12:14]}"


def _emit_json(payload: Any) -> None:
    """Print a single JSON document to stdout."""
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


# ------------------------------------------------------------------ options

def _host_opt() -> str:
    # Backward compat: keep accepting H388X_IP if H388X_HOST is unset.
    default = os.getenv("H388X_HOST") or os.getenv("H388X_IP", "192.168.1.1")
    return typer.Option(
        default,
        "--host",
        "-H",
        help=(
            "Modem host: IP, hostname, or full URL. Examples: "
            "`192.168.1.1`, `modem.example.com`, "
            "`https://modem.example.com:8443`. "
            "Plain hostnames default to http://."
        ),
    )


def _user_opt() -> str:
    return typer.Option(os.getenv("H388X_USER", "admin"), help="Admin username")


def _pwd_opt() -> Optional[str]:
    return typer.Option(None, help="Admin password (or set H388X_PASSWORD)")


def _insecure_opt() -> bool:
    return typer.Option(
        False,
        "--insecure",
        "-k",
        help="Skip TLS certificate verification (useful for self-signed HTTPS).",
    )


def get_api(
    host: str,
    user: str,
    password: Optional[str],
    insecure: bool = False,
) -> ZTEH388XAPI:
    password = password or os.getenv("H388X_PASSWORD", "")
    if not password:
        console.print(
            "[red]Error: Password is required. "
            "Set H388X_PASSWORD in .env or use --password.[/red]"
        )
        raise typer.Exit(code=1)

    if insecure:
        # urllib3 yells loudly when verify=False; silence it once, not per call.
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    api = ZTEH388XAPI(
        host=host, username=user, password=password, verify_tls=not insecure
    )
    # If a cached session was loaded from disk during ``__init__``, skip the
    # login handshake entirely. The first authenticated request will either
    # succeed or hit ``SessionTimeout``, in which case the ``_menudata``
    # retry path re-runs ``login()`` once and refreshes the cache.
    if api.has_cached_session:
        return api

    if state.json:
        ok = api.login()
    else:
        with console.status("[bold green]Connecting to modem..."):
            ok = api.login()
    if not ok:
        console.print(
            "[red]Login failed. Check credentials, IP and that no other "
            "admin session is open in a browser.[/red]"
        )
        raise typer.Exit(code=1)
    return api


# -------------------------------------------------------------- table builders

def _stats_table(s: DSLStats) -> Table:
    table = Table(title="DSL Statistics")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Status", s.status or "N/A")
    table.add_row("Module", s.module_type or "N/A")
    table.add_row("Profile", s.profile or "N/A")
    table.add_row("Data Path", s.data_path or "N/A")
    table.add_row(
        "Current Rate (D/U)",
        f"{_kbps(s.downstream_curr_rate)} / {_kbps(s.upstream_curr_rate)}",
    )
    table.add_row(
        "Max Rate (D/U)",
        f"{_kbps(s.downstream_max_rate)} / {_kbps(s.upstream_max_rate)}",
    )
    table.add_row(
        "SNR Margin (D/U)",
        f"{_deci(s.downstream_noise_margin, 'dB')} / {_deci(s.upstream_noise_margin, 'dB')}",
    )
    table.add_row(
        "Attenuation (D/U)",
        f"{_deci(s.downstream_attenuation, 'dB')} / {_deci(s.upstream_attenuation, 'dB')}",
    )
    table.add_row(
        "Power (D/U)",
        f"{_deci(s.downstream_power, 'dBm')} / {_deci(s.upstream_power, 'dBm')}",
    )
    table.add_row("Line Uptime", _humanize_uptime(s.showtime_start))
    table.add_row("FEC Errors", str(s.fec_errors) if s.fec_errors is not None else "N/A")
    return table


# ---------------------------------------------------------------------- stats

@app.command()
def stats(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    watch: Optional[float] = typer.Option(
        None,
        "--watch",
        "-w",
        help="Refresh stats every N seconds (Ctrl+C to stop).",
        min=0.1,
    ),
):
    """Display DSL line statistics (optionally live with --watch)."""
    api = get_api(host, user, password, insecure)
    try:
        if watch is None:
            raw = api.get_dsl_stats()
            if not raw:
                console.print("[red]No DSL stats returned.[/red]")
                raise typer.Exit(code=1)
            s = DSLStats.model_validate(raw)
            if state.json:
                _emit_json(s.model_dump())
            else:
                console.print(_stats_table(s))
            return

        # --watch mode
        if state.json:
            # JSON-lines, one snapshot per refresh.
            try:
                while True:
                    raw = api.get_dsl_stats()
                    if raw:
                        sys.stdout.write(
                            json.dumps(DSLStats.model_validate(raw).model_dump()) + "\n"
                        )
                        sys.stdout.flush()
                    time.sleep(watch)
            except KeyboardInterrupt:
                return

        with Live(console=console, refresh_per_second=4, screen=False) as live:
            try:
                while True:
                    raw = api.get_dsl_stats()
                    if raw:
                        live.update(_stats_table(DSLStats.model_validate(raw)))
                    time.sleep(watch)
            except KeyboardInterrupt:
                return
    finally:
        api.close()


# ----------------------------------------------------------------------- info

@app.command()
def info(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Display device information (model, firmware, serial)."""
    api = get_api(host, user, password, insecure)
    try:
        raw = api.get_device_info()
        if not raw:
            console.print("[red]No device info returned.[/red]")
            raise typer.Exit(code=1)
        d = DeviceInfo.model_validate(raw)
        if state.json:
            _emit_json(d.model_dump())
            return

        table = Table(title="Device Information")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Model", d.model or "N/A")
        table.add_row("Serial Number", d.serial_number or "N/A")
        table.add_row("Software Version", d.software_version or "N/A")
        table.add_row("Hardware Version", d.hardware_version or "N/A")
        table.add_row("Boot Version", d.boot_version or "N/A")
        table.add_row("Firmware Date", _format_firmware_date(d.firmware_date))
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------------ wan

@app.command()
def wan(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all WAN connections (default: only Connected ones).",
    ),
):
    """Show WAN connections (public IP, gateway, DNS, uptime)."""
    api = get_api(host, user, password, insecure)
    try:
        raw_list = api.get_wan_connections()
        if not raw_list:
            console.print("[red]No WAN data returned.[/red]")
            raise typer.Exit(code=1)

        conns = [WanConnection.model_validate(r) for r in raw_list]
        if not all_:
            conns = [c for c in conns if (c.status or "").lower() == "connected"]

        if state.json:
            _emit_json([c.model_dump() for c in conns])
            return

        table = Table(title="WAN Connections")
        table.add_column("Name", style="cyan")
        table.add_column("Status")
        table.add_column("IPv4", style="green")
        table.add_column("Gateway")
        table.add_column("DNS")
        table.add_column("Uptime")
        table.add_column("Services", style="yellow")

        for c in conns:
            dns = ", ".join(
                d for d in [c.dns1, c.dns2, c.dns3] if d and d != "0.0.0.0"
            )
            status_color = "green" if (c.status or "").lower() == "connected" else "red"
            table.add_row(
                c.name or "N/A",
                f"[{status_color}]{c.status or 'N/A'}[/{status_color}]",
                c.ip_address or "N/A",
                c.gateway or "N/A",
                dns or "N/A",
                _humanize_uptime(c.uptime_seconds),
                c.services or "N/A",
            )
        console.print(table)
        console.print(
            "[dim]Tip: use --json for full details (MAC, VLAN, MTU, subnet).[/dim]"
        )
    finally:
        api.close()


# -------------------------------------------------------------------- clients

@app.command()
def clients(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    leases: bool = typer.Option(
        False,
        "--leases",
        "-L",
        help="Show full DHCP lease table instead of currently-connected devices.",
    ),
):
    """List currently connected devices (LAN + Wi-Fi), or DHCP leases."""
    api = get_api(host, user, password, insecure)
    try:
        if leases:
            rows = api.get_dhcp_leases()
            if state.json:
                _emit_json(rows)
                return
            table = Table(title=f"DHCP Leases ({len(rows)})")
            table.add_column("Hostname", style="cyan")
            table.add_column("IP Address", style="green")
            table.add_column("MAC")
            table.add_column("Lease Expiry", style="yellow")
            for r in sorted(rows, key=lambda x: x.get("IPAddr", "")):
                table.add_row(
                    r.get("HostName") or "-",
                    r.get("IPAddr") or "-",
                    r.get("MACAddr") or "-",
                    r.get("ExpiredTime") or "-",
                )
            console.print(table)
            return

        lan = [Client.model_validate(r) for r in api.get_lan_clients()]
        wifi = [Client.model_validate(r) for r in api.get_wifi_clients()]
        all_clients: List[Client] = lan + wifi

        if state.json:
            _emit_json({
                "lan": [c.model_dump() for c in lan],
                "wifi": [c.model_dump() for c in wifi],
            })
            return

        table = Table(title=f"Connected Devices ({len(all_clients)})")
        table.add_column("Hostname", style="cyan")
        table.add_column("IPv4", style="green")
        table.add_column("MAC")
        table.add_column("Interface", style="yellow")
        table.add_column("IPv6", style="dim")

        for c in sorted(all_clients, key=lambda x: x.ipv4 or ""):
            table.add_row(
                c.hostname or "-",
                c.ipv4 or "-",
                c.mac or "-",
                c.interface or "-",
                c.ipv6 or "-",
            )
        console.print(table)
    finally:
        api.close()


# ---------------------------------------------------------------------- wifi

def _onoff(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    return "[green]ON[/green]" if int(value) else "[red]OFF[/red]"


def _security_label(ap: WifiAP) -> str:
    """Render a compact security mode for a WLAN AP."""
    bt = (ap.beacon_type or "").strip()
    if bt == "None":
        return "Open"
    # ZTE encodes WPA2 fields under 11i*; WPA1 under WPA*.
    parts: List[str] = []
    if ap.wpa2_auth_mode:
        parts.append(f"WPA2-{ap.wpa2_auth_mode.replace('Authentication', '')}/{ap.wpa2_encrypt or '?'}")
    elif ap.wpa_auth_mode:
        parts.append(f"WPA-{ap.wpa_auth_mode.replace('Authentication', '')}/{ap.wpa_encrypt or '?'}")
    return " ".join(parts) or bt or "N/A"


@app.command()
def wifi(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show Wi-Fi radios (2.4/5 GHz) and configured SSIDs (main + guest)."""
    api = get_api(host, user, password, insecure)
    try:
        radios_raw = api.get_wifi_radios()
        aps_raw = api.get_wifi_aps()
        radios = [WifiRadio.model_validate(r) for r in radios_raw]
        aps = [WifiAP.model_validate(r) for r in aps_raw]

        if state.json:
            _emit_json({
                "radios": [r.model_dump() for r in radios],
                "aps": [a.model_dump() for a in aps],
            })
            return

        if not radios and not aps:
            console.print("[red]No Wi-Fi data returned.[/red]")
            raise typer.Exit(code=1)

        radios_table = Table(title="Wi-Fi radios")
        radios_table.add_column("ID", style="dim")
        radios_table.add_column("Band", style="cyan")
        radios_table.add_column("Status")
        for r in radios:
            radios_table.add_row(r.id or "-", r.band or "-", _onoff(r.radio_on))
        console.print(radios_table)

        ap_table = Table(title=f"SSIDs ({len(aps)})")
        ap_table.add_column("ID", style="dim")
        ap_table.add_column("Radio", style="dim")
        ap_table.add_column("Alias", style="cyan")
        ap_table.add_column("ESSID", style="green")
        ap_table.add_column("Status")
        ap_table.add_column("Security", style="yellow")

        for ap in aps:
            ap_table.add_row(
                ap.id or "-",
                ap.radio_id or "-",
                ap.alias or "-",
                ap.essid or "-",
                _onoff(ap.enabled),
                _security_label(ap),
            )
        console.print(ap_table)
    finally:
        api.close()


# ------------------------------------------------------------------- firewall

_URL_FILTER_TARGET_LABEL = {
    0: "block-listed",
    1: "allow-listed",
}


@app.command()
def firewall(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show firewall summary: level, anti-DoS, URL filter, DMZ."""
    api = get_api(host, user, password, insecure)
    try:
        level = FirewallLevel.model_validate(api.get_firewall_level() or {})
        dos = FirewallDos.model_validate(api.get_firewall_dos() or {})
        urlf = UrlFilterGlobal.model_validate(api.get_url_filter_global() or {})
        dmz = Dmz.model_validate(api.get_dmz() or {})

        if state.json:
            _emit_json({
                "level": level.model_dump(),
                "dos": dos.model_dump(),
                "url_filter": urlf.model_dump(),
                "dmz": dmz.model_dump(),
            })
            return

        table = Table(title="Firewall")
        table.add_column("Setting", style="cyan")
        table.add_column("Value", style="magenta")

        table.add_row("Level", level.level or "N/A")

        dos_state = _onoff(dos.enabled)
        if dos.threshold is not None:
            dos_state = f"{dos_state}  [dim](threshold {dos.threshold} pkt/s)[/dim]"
        table.add_row("Anti-DoS", dos_state)

        url_state = _onoff(urlf.enabled)
        if urlf.target is not None:
            label = _URL_FILTER_TARGET_LABEL.get(int(urlf.target), str(urlf.target))
            url_state = f"{url_state}  [dim](mode: {label})[/dim]"
        table.add_row("URL filter", url_state)

        dmz_state = _onoff(dmz.enabled)
        if dmz.internal_client:
            dmz_state = f"{dmz_state}  → [green]{dmz.internal_client}[/green]"
        table.add_row("DMZ", dmz_state)

        console.print(table)
    finally:
        api.close()


# --------------------------------------------------------------- port-forward

def _port_range(start: Optional[int], end: Optional[int]) -> str:
    if start is None:
        return "-"
    if end is None or end == start:
        return str(start)
    return f"{start}-{end}"


def _remote_range(start: Optional[str], end: Optional[str]) -> str:
    if not start or start == "0.0.0.0":
        return "any"
    if not end or end == start or end == "0.0.0.0":
        return start
    return f"{start}-{end}"


@app.command("port-forward")
def port_forward(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all rules (default: only Enabled ones).",
    ),
):
    """List configured port-forwarding rules (NAT)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_port_forwarding_rules()
        rules = [PortForwardingRule.model_validate(r) for r in rows]
        if not all_:
            rules = [r for r in rules if r.enabled]

        if state.json:
            _emit_json([r.model_dump() for r in rules])
            return

        table = Table(title=f"Port forwarding ({len(rules)})")
        table.add_column("#", style="dim")
        table.add_column("Status")
        table.add_column("Description", style="cyan")
        table.add_column("Proto", style="yellow")
        table.add_column("WAN port", style="magenta")
        table.add_column("LAN client", style="green")
        table.add_column("LAN port", style="magenta")
        table.add_column("From", style="dim")

        for r in rules:
            table.add_row(
                (r.id or "").rsplit("PtMapping", 1)[-1] or "-",
                _onoff(r.enabled),
                r.description or "-",
                r.protocol or "-",
                _port_range(r.external_port, r.external_port_end),
                r.internal_client or "-",
                str(r.internal_port) if r.internal_port is not None else "-",
                _remote_range(r.remote_host, r.remote_host_end),
            )
        console.print(table)
        if not all_:
            console.print(
                "[dim]Tip: pass --all to also show disabled rules.[/dim]"
            )
    finally:
        api.close()


@app.command("port-forward-add")
def port_forward_add(
    description: str = typer.Argument(..., help="Free-form rule name."),
    protocol: str = typer.Argument(
        ..., help="TCP | UDP | BOTH (case-insensitive)."
    ),
    external_port: int = typer.Argument(
        ..., min=1, max=65535, help="WAN port to expose."
    ),
    internal_client: str = typer.Argument(
        ..., help="LAN IPv4 to forward the traffic to."
    ),
    internal_port: Optional[int] = typer.Option(
        None, "--int-port",
        min=1, max=65535,
        help="LAN port (default: same as EXTERNAL_PORT).",
    ),
    external_port_end: Optional[int] = typer.Option(
        None, "--ext-port-end",
        min=1, max=65535,
        help="End of WAN port range (default: same as EXTERNAL_PORT).",
    ),
    remote_host: str = typer.Option(
        "0.0.0.0", "--remote-host",
        help='Source IP restriction. "0.0.0.0" = any (default).',
    ),
    remote_host_end: str = typer.Option(
        "0.0.0.0", "--remote-host-end",
        help='End of source IP range. "0.0.0.0" = same as --remote-host.',
    ),
    disable: bool = typer.Option(
        False, "--disable",
        help="Create the rule disabled (defaults to enabled).",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Add a new port-forwarding rule (NAT)."""
    api = get_api(host, user, password, insecure)
    try:
        ok, body = api.add_port_forwarding_rule(
            description=description,
            protocol=protocol,
            external_port=external_port,
            internal_client=internal_client,
            internal_port=internal_port,
            external_port_end=external_port_end,
            remote_host=remote_host,
            remote_host_end=remote_host_end,
            enable=not disable,
        )
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Add failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        rows = api.get_port_forwarding_rules()
        new_rules = [
            PortForwardingRule.model_validate(r) for r in rows
            if r.get("Description") == description
        ]
        if state.json:
            _emit_json({
                "ok": True,
                "added": [r.model_dump() for r in new_rules],
            })
            return
        if new_rules:
            r = new_rules[-1]
            console.print(
                f"[green]Added[/green] port-forward "
                f"[bold]{r.id or '?'}[/bold]: "
                f"{r.protocol} {r.external_port} → "
                f"{r.internal_client}:{r.internal_port}  ([cyan]{r.description}[/cyan])"
            )
        else:
            console.print(
                f"[green]Added[/green] rule [cyan]{description}[/cyan] "
                f"(modem returned SUCC but no matching row read back)."
            )
    finally:
        api.close()


@app.command("port-forward-del")
def port_forward_del(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Either the bare suffix (e.g. '7') or the "
            "full path 'DEV.NAT.PtMapping7' (as shown by `h388x port-forward`)."
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes",
        help="Skip the confirmation prompt.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Delete a port-forwarding rule by ID."""
    inst_id = (
        rule_id
        if rule_id.startswith("DEV.NAT.PtMapping")
        else f"DEV.NAT.PtMapping{rule_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_port_forwarding_rules()
        target = next(
            (r for r in rows if r.get("_OBJ_InstID") == inst_id), None
        )
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"rule {inst_id!r} not found"})
            else:
                console.print(f"[red]No rule with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        if not yes and not state.json:
            rule = PortForwardingRule.model_validate(target)
            console.print(
                f"About to delete [bold]{inst_id}[/bold]: "
                f"{rule.protocol} {rule.external_port} → "
                f"{rule.internal_client}:{rule.internal_port}  "
                f"([cyan]{rule.description}[/cyan])"
            )
            if not typer.confirm("Proceed?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=1)

        ok, body = api.del_port_forwarding_rule(inst_id)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Delete failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "deleted": inst_id})
        else:
            console.print(
                f"[green]Deleted[/green] port-forward [bold]{inst_id}[/bold]."
            )
    finally:
        api.close()


@app.command("port-forward-toggle")
def port_forward_toggle(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Bare suffix (e.g. '7') or full path "
            "'DEV.NAT.PtMapping7'."
        ),
    ),
    enable: Optional[bool] = typer.Option(
        None, "--on/--off",
        help="Force enabled (--on) or disabled (--off). Default: flip current.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Enable/disable a port-forwarding rule (keeps all other fields)."""
    inst_id = (
        rule_id
        if rule_id.startswith("DEV.NAT.PtMapping")
        else f"DEV.NAT.PtMapping{rule_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_port_forwarding_rules()
        target = next((r for r in rows if r.get("_OBJ_InstID") == inst_id), None)
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"rule {inst_id!r} not found"})
            else:
                console.print(f"[red]No rule with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        currently_on = target.get("Enable") == "1"
        new_state = (not currently_on) if enable is None else enable
        if new_state == currently_on:
            if state.json:
                _emit_json({"ok": True, "id": inst_id, "enabled": currently_on, "changed": False})
            else:
                console.print(
                    f"[yellow]Rule [bold]{inst_id}[/bold] already "
                    f"{'enabled' if currently_on else 'disabled'}.[/yellow]"
                )
            return

        ok, body = api.set_port_forwarding_enabled(inst_id, new_state)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Toggle failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "id": inst_id, "enabled": new_state, "changed": True})
        else:
            console.print(
                f"[green]{'Enabled' if new_state else 'Disabled'}[/green] "
                f"port-forward [bold]{inst_id}[/bold]."
            )
    finally:
        api.close()


@app.command("port-forward-edit")
def port_forward_edit(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Bare suffix (e.g. '7') or full path "
            "'DEV.NAT.PtMapping7'."
        ),
    ),
    description: Optional[str] = typer.Option(None, "--desc", help="New rule name."),
    protocol: Optional[str] = typer.Option(
        None, "--protocol", help="New protocol: TCP | UDP | BOTH."
    ),
    external_port: Optional[int] = typer.Option(
        None, "--ext-port", min=1, max=65535, help="New WAN port."
    ),
    external_port_end: Optional[int] = typer.Option(
        None, "--ext-port-end", min=1, max=65535, help="New end of WAN port range."
    ),
    internal_client: Optional[str] = typer.Option(
        None, "--client", help="New LAN IPv4 target."
    ),
    internal_port: Optional[int] = typer.Option(
        None, "--int-port", min=1, max=65535, help="New LAN port."
    ),
    remote_host: Optional[str] = typer.Option(
        None, "--remote-host", help='New source IP restriction ("0.0.0.0" = any).'
    ),
    remote_host_end: Optional[str] = typer.Option(
        None, "--remote-host-end", help="New end of source IP range."
    ),
    enable: Optional[bool] = typer.Option(
        None, "--on/--off", help="Also enable/disable the rule."
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Edit fields of an existing port-forwarding rule (only the flags
    you pass are changed; everything else is kept)."""
    inst_id = (
        rule_id
        if rule_id.startswith("DEV.NAT.PtMapping")
        else f"DEV.NAT.PtMapping{rule_id}"
    )
    if all(
        v is None for v in (
            description, protocol, external_port, external_port_end,
            internal_client, internal_port, remote_host, remote_host_end, enable,
        )
    ):
        console.print("[yellow]Nothing to change (pass at least one field).[/yellow]")
        raise typer.Exit(code=1)

    api = get_api(host, user, password, insecure)
    try:
        ok, body = api.edit_port_forwarding_rule(
            inst_id,
            description=description, protocol=protocol,
            external_port=external_port, external_port_end=external_port_end,
            internal_client=internal_client, internal_port=internal_port,
            remote_host=remote_host, remote_host_end=remote_host_end,
            enable=enable,
        )
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Edit failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        rows = api.get_port_forwarding_rules()
        updated = next((r for r in rows if r.get("_OBJ_InstID") == inst_id), None)
        if state.json:
            _emit_json({
                "ok": True,
                "updated": PortForwardingRule.model_validate(updated).model_dump()
                if updated else None,
            })
            return
        if updated:
            r = PortForwardingRule.model_validate(updated)
            console.print(
                f"[green]Updated[/green] port-forward [bold]{inst_id}[/bold]: "
                f"{r.protocol} {r.external_port} → "
                f"{r.internal_client}:{r.internal_port}  ([cyan]{r.description}[/cyan]) "
                f"{'enabled' if r.enabled else 'disabled'}"
            )
        else:
            console.print(
                f"[green]Updated[/green] [bold]{inst_id}[/bold] "
                f"(modem returned SUCC but no matching row read back)."
            )
    finally:
        api.close()


# ------------------------------------------------------------------------ dns

@app.command()
def dns(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show modem DNS config + bound hostnames (DHCP + manual)."""
    api = get_api(host, user, password, insecure)
    try:
        local = DnsLocal.model_validate(api.get_dns_local() or {})
        hosts = [DnsHostname.model_validate(r) for r in api.get_dns_hostnames()]

        if state.json:
            _emit_json({
                "local": local.model_dump(),
                "hostnames": [h.model_dump() for h in hosts],
            })
            return

        local_table = Table(title="Local DNS")
        local_table.add_column("Field", style="cyan")
        local_table.add_column("Value", style="magenta")

        def _srv(addr: Optional[str]) -> str:
            if not addr or addr == "0.0.0.0":
                return "[dim](from WAN)[/dim]"
            return addr

        local_table.add_row("Domain", local.domain_name or "-")
        local_table.add_row("Server 1", _srv(local.server1))
        local_table.add_row("Server 2", _srv(local.server2))
        console.print(local_table)

        hosts_table = Table(title=f"DNS-bound hostnames ({len(hosts)})")
        hosts_table.add_column("Hostname", style="cyan")
        hosts_table.add_column("IP", style="green")
        hosts_table.add_column("MAC")
        hosts_table.add_column("Lease", style="yellow")
        for h in sorted(hosts, key=lambda x: x.ip_address or ""):
            lease = (
                "static" if h.lease_time == 0
                else (str(h.lease_time) + "s" if h.lease_time is not None else "-")
            )
            hosts_table.add_row(
                h.hostname or "-",
                h.ip_address or "-",
                h.mac or "-",
                lease,
            )
        console.print(hosts_table)
    finally:
        api.close()


@app.command("dns-set")
def dns_set(
    dns1: Optional[str] = typer.Argument(
        None, help="Primary DNS server pushed to LAN clients via DHCP."
    ),
    dns2: Optional[str] = typer.Option(
        None, "--dns2", help="Secondary DNS server (optional)."
    ),
    from_wan: bool = typer.Option(
        False, "--from-wan",
        help="Use the ISP-provided DNS instead of manual servers (ignores DNS1).",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Set the DNS servers handed to LAN clients via DHCP.

    This is the resolver the LAN actually uses. Existing leases keep
    their old DNS until renewal, so the live connection is not dropped.
    IP/pool/lease settings are preserved (read-modify-write).
    """
    if not from_wan and not dns1:
        console.print("[red]Provide DNS1, or use --from-wan.[/red]")
        raise typer.Exit(code=1)
    api = get_api(host, user, password, insecure)
    try:
        before = api.get_dhcp_config()
        ok, body = api.set_dhcp_dns(dns1=dns1, dns2=dns2, from_wan=from_wan)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Set failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        after = api.get_dhcp_config()
        if state.json:
            _emit_json({
                "ok": True,
                "before": {"dns1": before.get("DNSServer1"), "dns2": before.get("DNSServer2"),
                           "source": before.get("DnsServerSource")},
                "after": {"dns1": after.get("DNSServer1"), "dns2": after.get("DNSServer2"),
                          "source": after.get("DnsServerSource")},
            })
            return
        if after.get("DnsServerSource") == "1":
            console.print("[green]DNS source set to[/green] [bold]ISP / from WAN[/bold].")
        else:
            console.print(
                f"[green]DNS push updated[/green]: "
                f"[bold]{after.get('DNSServer1')}[/bold] / "
                f"[bold]{after.get('DNSServer2')}[/bold] "
                f"(was {before.get('DNSServer1')} / {before.get('DNSServer2')})"
            )
    finally:
        api.close()


# ------------------------------------------------------------------ mac-table

@app.command("mac-table")
def mac_table(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show the modem bridge's L2 forwarding table (MACs per interface)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_mac_table()
        entries = [MacTableEntry.model_validate(r) for r in rows]

        if state.json:
            _emit_json([e.model_dump() for e in entries])
            return

        table = Table(title=f"MAC table ({len(entries)})")
        table.add_column("MAC", style="cyan")
        table.add_column("VLAN", style="yellow")
        table.add_column("Interface", style="green")
        table.add_column("Age", style="magenta", justify="right")

        for e in sorted(entries, key=lambda x: (x.interface or "", x.mac or "")):
            age = (
                f"{e.aging_time:.1f}s" if e.aging_time is not None else "-"
            )
            table.add_row(
                e.mac or "-",
                str(e.vlan_id) if e.vlan_id is not None else "-",
                e.interface or "-",
                age,
            )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------------ arp

@app.command()
def arp(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show the modem's ARP cache (IPv4 -> MAC per interface)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_arp_table()
        entries = [ArpEntry.model_validate(r) for r in rows]

        if state.json:
            _emit_json([e.model_dump() for e in entries])
            return

        def _ip_key(addr: Optional[str]) -> tuple:
            try:
                return tuple(int(p) for p in (addr or "").split("."))
            except ValueError:
                return (0, 0, 0, 0)

        table = Table(title=f"ARP cache ({len(entries)})")
        table.add_column("IP", style="green")
        table.add_column("MAC", style="cyan")
        table.add_column("Interface", style="yellow")
        table.add_column("Status", style="dim", justify="right")
        for e in sorted(entries, key=lambda x: _ip_key(x.dest_ip)):
            table.add_row(
                e.dest_ip or "-",
                e.mac or "-",
                e.interface or "-",
                str(e.status) if e.status is not None else "-",
            )
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------------------- ddns

@app.command()
def ddns(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show DDNS client status (single IGD.DDNSC1)."""
    api = get_api(host, user, password, insecure)
    try:
        raw = api.get_ddns()
        d = Ddns.model_validate(raw or {})

        if state.json:
            _emit_json(d.model_dump())
            return

        table = Table(title="DDNS")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("State", _onoff(d.enabled))
        table.add_row("Service", d.service or "-")
        table.add_row("Username", d.username or "-")
        table.add_row("Domain", d.domain or "-")
        table.add_row("Status", d.status or "-")
        table.add_row("Last error", d.last_error or "-")
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------------ eth

def _human_bytes(n: Optional[int]) -> str:
    if n is None:
        return "-"
    if n == 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    idx = 0
    while value >= 1024 and idx < len(units) - 1:
        value /= 1024
        idx += 1
    return f"{value:.2f} {units[idx]}"


def _link_speed(mbps: Optional[int], status: Optional[str]) -> str:
    # Modem reports LinkSpeed=10 when the port has no link, even on gigabit
    # PHYs, which is misleading. Treat any NoLink-ish status as no speed.
    if not status or status.lower() in {"nolink", "down", "disabled"}:
        return "-"
    if mbps is None:
        return "-"
    if mbps >= 1000 and mbps % 1000 == 0:
        return f"{mbps // 1000} Gbps"
    return f"{mbps} Mbps"


@app.command()
def eth(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show ethernet port status (4 LAN + the eth-WAN uplink)."""
    api = get_api(host, user, password, insecure)
    try:
        lan_rows = api.get_eth_lan_ports()
        wan_row = api.get_eth_wan_port()
        lan = [EthInterface.model_validate(r) for r in lan_rows]
        wan = EthInterface.model_validate(wan_row or {}) if wan_row else None

        if state.json:
            _emit_json({
                "lan": [p.model_dump() for p in lan],
                "wan": wan.model_dump() if wan else None,
            })
            return

        lan_table = Table(title=f"LAN ports ({len(lan)})")
        lan_table.add_column("Port", style="cyan")
        lan_table.add_column("Status")
        lan_table.add_column("Speed", style="magenta")
        lan_table.add_column("Duplex")
        lan_table.add_column("RX", style="green", justify="right")
        lan_table.add_column("TX", style="green", justify="right")
        lan_table.add_column("MAC", style="dim")
        for p in lan:
            up = (p.status or "").lower() == "up"
            status = (
                f"[green]{p.status}[/green]" if up
                else f"[dim]{p.status or '-'}[/dim]"
            )
            lan_table.add_row(
                p.alias or (p.id or "-"),
                status,
                _link_speed(p.link_speed, p.status),
                p.link_duplex if up else "-",
                _human_bytes(p.bytes_rx),
                _human_bytes(p.bytes_tx),
                p.mac or "-",
            )
        console.print(lan_table)

        if wan:
            wan_table = Table(title="WAN (ethernet)")
            wan_table.add_column("Field", style="cyan")
            wan_table.add_column("Value", style="magenta")
            wan_table.add_row("Port ID", wan.id or "-")
            wan_table.add_row("Status", wan.status or "-")
            wan_table.add_row("Speed", _link_speed(wan.link_speed, wan.status))
            wan_table.add_row(
                "Duplex",
                wan.link_duplex if (wan.status or "").lower() == "up" else "-",
            )
            wan_table.add_row("MAC", wan.mac or "-")
            wan_table.add_row("RX bytes", _human_bytes(wan.bytes_rx))
            wan_table.add_row("TX bytes", _human_bytes(wan.bytes_tx))
            if wan.packets_rx is not None or wan.packets_tx is not None:
                wan_table.add_row(
                    "Packets RX/TX",
                    f"{wan.packets_rx or 0} / {wan.packets_tx or 0}",
                )
            if wan.single_status:
                wan_table.add_row("Optical status", wan.single_status)
                wan_table.add_row(
                    "Optical RX/TX",
                    f"{wan.single_rx_strength or '-'} / {wan.single_tx_strength or '-'}",
                )
            console.print(wan_table)
    finally:
        api.close()


# ----------------------------------------------------------------------- dhcp

def _format_lease(seconds: Optional[int]) -> str:
    if seconds is None:
        return "-"
    if seconds == 0:
        return "infinite"
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}s")
    return " ".join(parts) or "0s"


_DNS_SOURCE_LABEL = {
    0: "manual",
    1: "from WAN",
}


@app.command()
def dhcp(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show DHCPv4 server config + static reservations (bindings)."""
    api = get_api(host, user, password, insecure)
    try:
        cfg = DhcpConfig.model_validate(api.get_dhcp_config() or {})
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]

        if state.json:
            _emit_json({
                "config": cfg.model_dump(),
                "bindings": [b.model_dump() for b in bindings],
            })
            return

        cfg_table = Table(title="DHCPv4 server")
        cfg_table.add_column("Field", style="cyan")
        cfg_table.add_column("Value", style="magenta")
        cfg_table.add_row("State", _onoff(cfg.enabled))
        cfg_table.add_row("Router IP", cfg.router_ip or "-")
        cfg_table.add_row("Subnet mask", cfg.subnet_mask or "-")
        cfg_table.add_row(
            "Pool",
            f"{cfg.pool_min or '-'} ... {cfg.pool_max or '-'}",
        )
        cfg_table.add_row("Lease time", _format_lease(cfg.lease_time))
        cfg_table.add_row(
            "DNS source",
            _DNS_SOURCE_LABEL.get(cfg.dns_source, str(cfg.dns_source)) if cfg.dns_source is not None else "-",
        )
        cfg_table.add_row("DNS 1 (pushed)", cfg.dns1 or "-")
        cfg_table.add_row("DNS 2 (pushed)", cfg.dns2 or "-")
        console.print(cfg_table)

        bind_table = Table(title=f"Static bindings / reservations ({len(bindings)})")
        bind_table.add_column("Name", style="cyan")
        bind_table.add_column("IP", style="green")
        bind_table.add_column("MAC")
        bind_table.add_column("ID", style="dim")
        for b in sorted(bindings, key=lambda x: x.ip_address or ""):
            bind_table.add_row(
                b.name or "-",
                b.ip_address or "-",
                b.mac or "-",
                b.id or "-",
            )
        console.print(bind_table)
    finally:
        api.close()


# Static DHCPv4 reservations are exposed by the modem with instance ids
# shaped like ``DEV.V4DP.Sr.Pl1.Bd<N>`` (one pool, one binding subtree).
# Accept a bare suffix on the CLI and expand it, mirroring the
# port-forward-del UX (``DEV.NAT.PtMapping<N>``).
_DHCP_BIND_ID_PREFIX = "DEV.V4DP.Sr.Pl1.Bd"


@app.command("dhcp-reserve-add")
def dhcp_reserve_add(
    mac: str = typer.Argument(
        ..., help="Client MAC address (e.g. AA:BB:CC:DD:EE:FF)."
    ),
    ip_address: str = typer.Argument(
        ..., help="LAN IPv4 to bind to this MAC."
    ),
    name: str = typer.Argument(
        ..., help="Free-form hostname/label for the reservation."
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Add a static DHCPv4 reservation (MAC → IP)."""
    api = get_api(host, user, password, insecure)
    try:
        ok, body = api.add_dhcp_reservation(
            mac=mac, ip_address=ip_address, name=name,
        )
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Add failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        rows = api.get_dhcp_bindings()
        new_rows = [
            DhcpBinding.model_validate(r) for r in rows
            if (r.get("MACAddr") or "").lower() == mac.lower()
        ]
        if state.json:
            _emit_json({
                "ok": True,
                "added": [b.model_dump() for b in new_rows],
            })
            return
        if new_rows:
            b = new_rows[-1]
            # ``console.print`` parses ``[..]`` as rich markup, and a
            # MAC like ``02:AB:CD:...`` contains substrings (``[ab]``,
            # ``[cd]``) that match emoji shortcodes. Disable markup on
            # the MAC line so addresses render verbatim.
            console.print(
                f"[green]Added[/green] reservation "
                f"[bold]{b.id or '?'}[/bold]: "
                f"([cyan]{b.name or name}[/cyan]) → {b.ip_address or ip_address}"
            )
            console.print(f"  MAC: {b.mac or mac}", markup=False, emoji=False)
        else:
            console.print(
                f"[green]Added[/green] reservation for [cyan]{mac}[/cyan] "
                f"(modem returned SUCC but no matching row read back)."
            )
    finally:
        api.close()


@app.command("dhcp-reserve-del")
def dhcp_reserve_del(
    binding_id: str = typer.Argument(
        ...,
        help=(
            "Binding _OBJ_InstID. Either the bare suffix (e.g. '1') or the "
            "full path 'DEV.V4DP.Sr.Pl1.Bd1' (as shown by `h388x dhcp`)."
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes",
        help="Skip the confirmation prompt.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Delete a DHCPv4 reservation by ID."""
    inst_id = (
        binding_id
        if binding_id.startswith(_DHCP_BIND_ID_PREFIX)
        else f"{_DHCP_BIND_ID_PREFIX}{binding_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_dhcp_bindings()
        target = next(
            (r for r in rows if r.get("_OBJ_InstID") == inst_id), None
        )
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"binding {inst_id!r} not found"})
            else:
                console.print(f"[red]No reservation with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        if not yes and not state.json:
            b = DhcpBinding.model_validate(target)
            console.print(
                f"About to delete [bold]{inst_id}[/bold]: "
                f"([cyan]{b.name or '-'}[/cyan]) → {b.ip_address or '-'}"
            )
            console.print(f"  MAC: {b.mac or '-'}", markup=False, emoji=False)
            if not typer.confirm("Proceed?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=1)

        ok, body = api.del_dhcp_reservation(inst_id)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Delete failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "deleted": inst_id})
        else:
            console.print(
                f"[green]Deleted[/green] reservation [bold]{inst_id}[/bold]."
            )
    finally:
        api.close()


# -------------------------------------------------------------------- devices

# Device-naming feature (route A): DHCP reservations (MAC -> fixed IP + Name)
# are the primary, MAC-keyed naming layer. The ``devices`` view merges the
# currently-connected clients (LAN + Wi-Fi) with the static reservations,
# keyed by MAC, so the observed DHCP hostname and the assigned reservation
# name stay visually distinct.

devices_app = typer.Typer(
    help=(
        "Device naming (DHCP reservations, MAC-keyed). Bare `devices` lists "
        "connected clients merged with reservations."
    ),
    no_args_is_help=False,
)
app.add_typer(devices_app, name="devices")


@devices_app.callback(invoke_without_command=True)
def devices_main(
    ctx: typer.Context,
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """List connected devices (LAN + Wi-Fi) merged with DHCP reservations."""
    if ctx.invoked_subcommand is not None:
        return

    api = get_api(host, user, password, insecure)
    try:
        clients = (
            [Client.model_validate(r) for r in api.get_lan_clients()]
            + [Client.model_validate(r) for r in api.get_wifi_clients()]
        )
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]
        rows = _merge_devices(clients, bindings)

        if state.json:
            _emit_json(sorted(rows, key=lambda r: r.get("ipv4") or ""))
            return

        table = Table(title=f"Devices ({len(rows)})")
        table.add_column("Name", style="cyan")
        table.add_column("Hostname (DHCP)", style="dim")
        table.add_column("IPv4", style="green")
        table.add_column("MAC")
        table.add_column("Interface", style="yellow")
        table.add_column("Online")
        table.add_column("Reserved")

        for r in sorted(rows, key=lambda r: r.get("ipv4") or ""):
            online = "[green]yes[/green]" if r["online"] else "[red]no[/red]"
            reserved = "[green]yes[/green]" if r["reserved"] else "[dim]no[/dim]"
            # MACs contain segments like ``:ab:``/``:cd:`` that rich would
            # treat as emoji shortcodes; render as plain Text so they show
            # verbatim.
            table.add_row(
                r["name"] or "-",
                r["hostname"] or "-",
                r["ipv4"] or "-",
                Text(r["mac"] or "-"),
                r["interface"] or "-",
                online,
                reserved,
            )
        console.print(table)
        console.print(
            "[dim]Tip: 'Name' = assigned reservation, 'Hostname' = "
            "observed via DHCP (read-only).[/dim]"
        )
    finally:
        api.close()


@devices_app.command("export")
def devices_export(
    file: Optional[str] = typer.Argument(
        None,
        help="Output file. Writes to stdout when omitted.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Export DHCP reservations as portable JSON ``[{mac, ip, name}]``."""
    api = get_api(host, user, password, insecure)
    try:
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]
        data = _reservations_export(bindings)
    finally:
        api.close()

    if file:
        with open(file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
        if not state.json:
            console.print(
                f"[green]Exported[/green] {len(data)} reservation(s) to "
                f"[bold]{file}[/bold]."
            )
    else:
        _emit_json(data)


@devices_app.command("import")
def devices_import(
    file: str = typer.Argument(
        ..., help="JSON file with [{mac, ip, name}] entries to apply."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and show the diff without writing anything to the modem.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Apply reservation names from JSON with validation-first semantics.

    The complete plan is validated before the first write. During apply the
    command stops at the first failed write and reports partial application.
    """
    try:
        with open(file, "r", encoding="utf-8") as fh:
            entries = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        if state.json:
            _emit_json({"ok": False, "error": f"cannot read {file!r}: {exc}"})
        else:
            console.print(f"[red]Cannot read[/red] [bold]{file}[/bold]: {exc}")
        raise typer.Exit(code=1)

    if not isinstance(entries, list):
        if state.json:
            _emit_json({"ok": False, "error": "JSON root must be a list"})
        else:
            console.print("[red]JSON root must be a list of {mac, ip, name}.[/red]")
        raise typer.Exit(code=1)

    api = get_api(host, user, password, insecure)
    try:
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]
        plan = _plan_import(entries, bindings)
        preflight_errors = sum(1 for item in plan if item["action"] == "error")

        if dry_run:
            apply_ok = preflight_errors == 0
            summary = {
                "applied": 0,
                "failed": 0,
                "skipped": 0,
                "partial": False,
                "preflight_errors": preflight_errors,
            }
        else:
            apply_ok, summary = _apply_import_plan(api, plan)

        if state.json:
            _emit_json({
                "ok": apply_ok,
                "dry_run": dry_run,
                "summary": summary,
                "plan": plan,
            })
            if not apply_ok:
                raise typer.Exit(code=1)
            return

        table = Table(title=f"Import plan ({'dry-run' if dry_run else 'applied'})")
        table.add_column("Action")
        table.add_column("Name", style="cyan")
        table.add_column("IP", style="green")
        table.add_column("MAC")
        table.add_column("Detail", style="dim")
        colors = {"add": "green", "edit": "yellow", "unchanged": "dim", "error": "red"}
        for item in plan:
            action = item["action"]
            color = colors.get(action, "white")
            if action == "edit":
                detail = f"was: {item['old_name'] or '-'} / {item['old_ip'] or '-'}"
            elif action == "error":
                detail = item.get("error", "")
            else:
                detail = ""
            if item.get("skipped"):
                action = f"{action} SKIPPED"
                color = "yellow"
                detail = item["skipped"]
            elif not dry_run and "ok" in item and not item["ok"]:
                action = f"{action} FAILED"
                color = "red"
                detail = item.get("raw", detail)
            table.add_row(
                f"[{color}]{action}[/{color}]",
                item["name"] or "-",
                item["ip"] or "-",
                Text(item["mac"] or "-"),
                detail,
            )
        console.print(table)
        n_add = sum(1 for item in plan if item["action"] == "add")
        n_edit = sum(1 for item in plan if item["action"] == "edit")
        n_same = sum(1 for item in plan if item["action"] == "unchanged")
        n_err = sum(1 for item in plan if item["action"] == "error")
        console.print(
            f"[dim]add={n_add} edit={n_edit} unchanged={n_same} error={n_err} "
            f"applied={summary['applied']} failed={summary['failed']} "
            f"skipped={summary['skipped']}"
            + ("  (dry-run, nothing written)" if dry_run else "")
            + "[/dim]"
        )
        if not apply_ok:
            if summary.get("partial"):
                console.print(
                    "[red]Import stopped after a write failure. Some earlier changes "
                    "were already applied; review the plan before retrying.[/red]"
                )
            elif preflight_errors:
                console.print("[red]Preflight failed; no modem changes were attempted.[/red]")
            raise typer.Exit(code=1)
    finally:
        api.close()

@devices_app.command("set")
def devices_set(
    mac: str = typer.Argument(..., help="Client MAC address."),
    name: str = typer.Argument(..., help="Friendly name to assign."),
    ip_address: Optional[str] = typer.Option(
        None, "--ip",
        help=(
            "IPv4 to reserve (must be in the DHCP pool). Required only when "
            "no reservation exists yet and the device's current IP can't be "
            "discovered."
        ),
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Assign a name to a device by MAC (edit reservation, or add one).

    If a reservation already exists for the MAC, only its name (and IP if
    ``--ip`` is given) is updated. Otherwise a new reservation is created;
    the IP comes from ``--ip`` or, if omitted, from the device's currently
    observed DHCP address.
    """
    key = _norm_mac(mac)
    api = get_api(host, user, password, insecure)
    try:
        existing = next(
            (b for b in (DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings())
             if _norm_mac(b.mac) == key),
            None,
        )

        if existing is not None:
            ok, body = api.edit_dhcp_reservation(
                existing.id, name=name, ip_address=ip_address,
            )
            action = "updated"
            target_ip = ip_address or existing.ip_address
        else:
            target_ip = ip_address
            if not target_ip:
                # Discover the device's current IP from connected clients.
                clients = (
                    [Client.model_validate(r) for r in api.get_lan_clients()]
                    + [Client.model_validate(r) for r in api.get_wifi_clients()]
                )
                match = next(
                    (c for c in clients if _norm_mac(c.mac) == key and c.ipv4), None
                )
                target_ip = match.ipv4 if match else None
            if not target_ip:
                msg = (
                    "no reservation for this MAC and could not discover its "
                    "current IP; pass --ip <addr in DHCP pool>"
                )
                if state.json:
                    _emit_json({"ok": False, "error": msg})
                else:
                    console.print(f"[red]{msg}[/red]")
                raise typer.Exit(code=1)
            ok, body = api.add_dhcp_reservation(
                mac=mac, ip_address=target_ip, name=name,
            )
            action = "added"

        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Set failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        if state.json:
            _emit_json({
                "ok": True, "action": action,
                "mac": mac, "ip": target_ip, "name": name,
            })
        else:
            console.print(
                f"[green]{action.capitalize()}[/green] reservation "
                f"([cyan]{name}[/cyan]) → {target_ip}"
            )
            console.print(f"  MAC: {mac}", markup=False, emoji=False)
    finally:
        api.close()


@devices_app.command("clear")
def devices_clear(
    mac: str = typer.Argument(..., help="Client MAC address."),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Remove the DHCP reservation (and its name) for a device by MAC."""
    key = _norm_mac(mac)
    api = get_api(host, user, password, insecure)
    try:
        existing = next(
            (b for b in (DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings())
             if _norm_mac(b.mac) == key),
            None,
        )
        if existing is None:
            msg = f"no reservation found for MAC {mac!r}"
            if state.json:
                _emit_json({"ok": False, "error": msg})
            else:
                console.print(msg, style="red", markup=False, emoji=False)
            raise typer.Exit(code=1)

        if not yes and not state.json:
            console.print(
                f"About to delete [bold]{existing.id}[/bold]: "
                f"([cyan]{existing.name or '-'}[/cyan]) → {existing.ip_address or '-'}"
            )
            console.print(f"  MAC: {existing.mac or mac}", markup=False, emoji=False)
            if not typer.confirm("Proceed?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=1)

        ok, body = api.del_dhcp_reservation(existing.id)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Clear failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "deleted": existing.id, "mac": mac})
        else:
            console.print(
                f"[green]Cleared[/green] reservation [bold]{existing.id}[/bold]."
            )
    finally:
        api.close()


@devices_app.command("edit")
def devices_edit(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Interactively name devices one by one (reservations, route A).

    Walks the merged device list and prompts per device:
    - press Enter to keep the current name,
    - type a name to set/rename (creates a reservation using the device's
      observed IP when none exists yet),
    - type ``-`` to clear an existing reservation.

    Nothing is written until you confirm the summary at the end.
    """
    if state.json:
        console.print(
            "[red]`devices edit` is interactive and does not support --json.[/red]"
        )
        raise typer.Exit(code=1)

    api = get_api(host, user, password, insecure)
    try:
        clients = (
            [Client.model_validate(r) for r in api.get_lan_clients()]
            + [Client.model_validate(r) for r in api.get_wifi_clients()]
        )
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]
        rows = sorted(_merge_devices(clients, bindings), key=lambda r: r.get("ipv4") or "")

        console.print("[bold]Interactive device naming[/bold] (route A: DHCP reservations)")
        console.print(
            "[dim]Enter = keep · type a name to set/rename · '-' = clear · "
            "Ctrl-C = abort[/dim]\n"
        )

        # Each action: (kind, row, new_name) where kind in add/edit/clear.
        actions: List[tuple] = []
        for r in rows:
            current = r["name"] or ""
            online = "[green]online[/green]" if r["online"] else "[red]offline[/red]"
            reserved = "reserved" if r["reserved"] else "no-reservation"
            console.print(
                f"[green]{r['ipv4'] or '-'}[/green]  "
                f"name=[cyan]{current or '-'}[/cyan]  "
                f"dhcp=[dim]{r['hostname'] or '-'}[/dim]  "
                f"{online}  [dim]{reserved}[/dim]"
            )
            console.print(f"  MAC {r['mac'] or '-'}", markup=False, emoji=False)

            ans = typer.prompt("  name", default=current, show_default=True).strip()

            if ans == current:
                continue  # unchanged
            if ans == "-":
                if r["reserved"]:
                    actions.append(("clear", r, None))
                else:
                    console.print("  [dim](nothing to clear)[/dim]")
                continue
            if r["reserved"]:
                actions.append(("edit", r, ans))
            elif r["ipv4"]:
                actions.append(("add", r, ans))
            else:
                console.print(
                    "  [yellow]skip: no reservation and no observed IP "
                    "(use `devices set MAC NAME --ip`).[/yellow]"
                )

        if not actions:
            console.print("\n[dim]No changes.[/dim]")
            return

        table = Table(title="Pending changes")
        table.add_column("Action")
        table.add_column("Name", style="cyan")
        table.add_column("IP", style="green")
        table.add_column("MAC")
        applied = 0
        for index, (kind, r, new) in enumerate(actions):
            if kind == "edit":
                ok, body = api.edit_dhcp_reservation(r["reservation_id"], name=new)
            elif kind == "add":
                ok, body = api.add_dhcp_reservation(
                    mac=r["mac"], ip_address=r["ipv4"], name=new,
                )
            else:
                ok, body = api.del_dhcp_reservation(r["reservation_id"])
            label = (new if new is not None else r["name"]) or "-"
            if ok:
                applied += 1
                console.print(
                    f"[green]{kind}[/green] [cyan]{label}[/cyan] → {r['ipv4'] or '-'}"
                )
                continue

            remaining = len(actions) - index - 1
            console.print(
                f"[red]{kind} FAILED[/red] for {label}: [dim]{body[:200]}[/dim]"
            )
            console.print(
                f"[red]Stopped after failure: applied={applied}, failed=1, "
                f"skipped={remaining}. Earlier successful changes remain applied.[/red]"
            )
            raise typer.Exit(code=1)

    finally:
        api.close()


# ---------------------------------------------------------------------- dhcp6

@app.command()
def dhcp6(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show IPv6 DHCPv6 server + Router Advertisement state."""
    api = get_api(host, user, password, insecure)
    try:
        srv = Dhcp6Server.model_validate(api.get_dhcp6_server() or {})
        ra = RouterAdvertisement.model_validate(api.get_ra() or {})
        hosts = api.get_dhcp6_hosts()

        if state.json:
            _emit_json({
                "dhcp6_server": srv.model_dump(),
                "ra": ra.model_dump(),
                "hosts": hosts,
            })
            return

        srv_table = Table(title="DHCPv6 server")
        srv_table.add_column("Field", style="cyan")
        srv_table.add_column("Value", style="magenta")
        srv_table.add_row("State", _onoff(srv.enabled))
        srv_table.add_row("IA_NA (stateful)", _onoff(srv.iana_enabled))
        srv_table.add_row(
            "Prefix source",
            "auto (from WAN)" if srv.prefix_auto else "manual",
        )
        if not srv.prefix_auto:
            srv_table.add_row("Manual prefixes", srv.manual_prefixes or "-")
        srv_table.add_row("DNS source", "manual" if srv.manual_dns else "auto")
        if srv.manual_dns:
            srv_table.add_row("DNS 1", srv.dns1 or "-")
            srv_table.add_row("DNS 2", srv.dns2 or "-")
            srv_table.add_row("DNS 3", srv.dns3 or "-")
        srv_table.add_row("DNS refresh", _format_lease(srv.dns_refresh_time))
        console.print(srv_table)

        ra_table = Table(title="Router Advertisement (RA)")
        ra_table.add_column("Field", style="cyan")
        ra_table.add_column("Value", style="magenta")
        ra_table.add_row("State", _onoff(ra.enabled))
        ra_table.add_row("M flag (managed)", _onoff(ra.managed_flag))
        ra_table.add_row("O flag (other-config)", _onoff(ra.other_config_flag))
        ra_table.add_row(
            "Prefix source",
            "auto (from WAN)" if ra.prefix_auto else "manual",
        )
        if not ra.prefix_auto:
            ra_table.add_row("Manual prefixes", ra.manual_prefixes or "-")
        ra_table.add_row(
            "RA interval",
            f"{ra.min_interval}..{ra.max_interval}s"
            if ra.min_interval is not None and ra.max_interval is not None else "-",
        )
        if ra.adv_mtu_enabled:
            ra_table.add_row("Advertised MTU", str(ra.adv_mtu) if ra.adv_mtu else "-")
        ra_table.add_row("Preferred router", _onoff(ra.preferred_router_flag))
        console.print(ra_table)

        console.print(
            f"[dim]DHCPv6 client bindings (OBJ_DHCP6C_ID): {len(hosts)}[/dim]"
        )
    finally:
        api.close()


# ----------------------------------------------------------------------- voip

def _voip_status_style(status: Optional[str]) -> str:
    if not status:
        return "-"
    s = status.lower()
    if "non" in s:  # "Non registrato"
        return f"[red]{status}[/red]"
    if "regist" in s:  # "Registrato"
        return f"[green]{status}[/green]"
    return status


def _short_line_id(full_id: Optional[str]) -> str:
    # e.g. IGD.SV.VS1.VP1.VL1 -> VL1, IGD.SV.VS1.VP1.VL1.LS -> VL1.LS
    if not full_id:
        return "-"
    parts = full_id.split(".")
    return ".".join(parts[-2:]) if parts[-1] == "LS" else parts[-1]


def _phy_jacks(phy_list: Optional[str]) -> str:
    # Comma-separated indices -> TEL1,TEL2 style for readability.
    if not phy_list:
        return "[dim]unbound[/dim]"
    out = []
    for raw in phy_list.split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            out.append(f"TEL{int(raw) + 1}")
        except ValueError:
            out.append(raw)
    return ", ".join(out) if out else "[dim]unbound[/dim]"


@app.command()
def voip(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show VoIP line status (SIP registration + physical bindings)."""
    api = get_api(host, user, password, insecure)
    try:
        status = api.get_voip_status()
        bindings = api.get_voip_bindings()

        lines = [VoipLine.model_validate(r) for r in status.get("OBJ_VOIPVPLINE_ID", [])]
        sips = [VoipSipLine.model_validate(r) for r in status.get("OBJ_VOIPSIPLINE_ID", [])]
        bind_lines = [VoipLine.model_validate(r) for r in bindings.get("OBJ_VOIPVPLINE_ID", [])]

        # Index PhyList by virtual-line id (the bindings response uses _InstID,
        # not _OBJ_InstID, so VoipLine.id_alt is the join key here).
        phy_by_id = {b.id_alt: b.phy_list for b in bind_lines if b.id_alt}

        if state.json:
            _emit_json({
                "lines": [
                    {
                        **line.model_dump(),
                        "phy_list": phy_by_id.get(line.id_alt or line.id),
                    }
                    for line in lines
                ],
                "sip_lines": [s.model_dump() for s in sips],
                "bindings": bindings,
            })
            return

        # Join SIP line to its parent VL via id prefix (foo.VL1.LS -> foo.VL1).
        sip_by_vl: dict[str, VoipSipLine] = {}
        for s in sips:
            if s.id and s.id.endswith(".LS"):
                sip_by_vl[s.id[:-3]] = s

        table = Table(title=f"VoIP lines ({len(lines)})")
        table.add_column("Line", style="cyan")
        table.add_column("Phone name")
        table.add_column("Number", style="magenta")
        table.add_column("Registration")
        table.add_column("Bound jacks", style="green")

        for line in lines:
            vl_id = line.id or line.id_alt
            sip = sip_by_vl.get(vl_id) if vl_id else None
            table.add_row(
                _short_line_id(vl_id),
                (sip.phone_name if sip else None) or "-",
                (sip.auth_username if sip else None) or "[dim]not set[/dim]",
                _voip_status_style(line.is_online),
                _phy_jacks(phy_by_id.get(line.id_alt or line.id)),
            )
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------------------- upnp

@app.command()
def upnp(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show UPnP IGD state + live port mappings."""
    api = get_api(host, user, password, insecure)
    try:
        cfg = UpnpConfig.model_validate(api.get_upnp_config() or {})
        maps = [UpnpPortMapping.model_validate(r) for r in api.get_upnp_portmappings()]

        if state.json:
            _emit_json({
                "config": cfg.model_dump(),
                "port_mappings": [m.model_dump() for m in maps],
            })
            return

        cfg_table = Table(title="UPnP IGD")
        cfg_table.add_column("Field", style="cyan")
        cfg_table.add_column("Value", style="magenta")
        cfg_table.add_row("State", _onoff(cfg.enabled))
        console.print(cfg_table)

        if not maps:
            console.print(
                "[dim]No live UPnP port mappings (clients can request "
                "them only while UPnP is ON).[/dim]"
            )
            return

        maps_table = Table(title=f"UPnP port mappings ({len(maps)})")
        maps_table.add_column("Status")
        maps_table.add_column("Description", style="cyan")
        maps_table.add_column("Proto", style="yellow")
        maps_table.add_column("WAN port", style="magenta")
        maps_table.add_column("LAN client", style="green")
        maps_table.add_column("LAN port", style="magenta")
        maps_table.add_column("Lease", style="dim")
        for m in maps:
            lease = "perm" if m.lease_duration == 0 else (
                f"{m.lease_duration}s" if m.lease_duration is not None else "-"
            )
            maps_table.add_row(
                _onoff(m.enabled),
                m.description or "-",
                m.protocol or "-",
                str(m.external_port) if m.external_port is not None else "-",
                m.internal_client or "-",
                str(m.internal_port) if m.internal_port is not None else "-",
                lease,
            )
        console.print(maps_table)
    finally:
        api.close()


# ------------------------------------------------------------------------ dms

@app.command()
def dms(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show DLNA / DMS media-server config (USB sharing)."""
    api = get_api(host, user, password, insecure)
    try:
        d = Dms.model_validate(api.get_dms() or {})

        if state.json:
            _emit_json(d.model_dump())
            return

        table = Table(title="DLNA media server")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("State", _onoff(d.enabled))
        table.add_row("Name", d.name or "-")
        table.add_row("Root path", d.path_root or "-")
        table.add_row("Content list", d.content_list or "-")
        table.add_row(
            "Rescan",
            "on demand only" if d.rescan_time == 0 else _format_lease(d.rescan_time),
        )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------------ ftp

@app.command()
def ftp(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show FTP server state + configured FTP users."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_ftp()
        cfg_rows = data.get("OBJ_FMFTPSERVERCFG_ID", [])
        user_rows = data.get("OBJ_FMFTPUSER_ID", [])
        cfg = FtpServer.model_validate(cfg_rows[0] if cfg_rows else {})
        users = [FtpUser.model_validate(r) for r in user_rows]

        if state.json:
            _emit_json({
                "config": cfg.model_dump(),
                "users": [u.model_dump() for u in users],
            })
            return

        cfg_table = Table(title="FTP server")
        cfg_table.add_column("Field", style="cyan")
        cfg_table.add_column("Value", style="magenta")
        cfg_table.add_row("State", _onoff(cfg.enabled))
        console.print(cfg_table)

        users_table = Table(title=f"FTP users ({len(users)})")
        users_table.add_column("Username", style="cyan")
        users_table.add_column("ID", style="dim")
        for u in users:
            users_table.add_row(u.username or "-", u.id or "-")
        console.print(users_table)
    finally:
        api.close()


# ------------------------------------------------------------------- nanocdn

@app.command()
def nanocdn(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show NanoCDN runtime stats (TIM IPTV multicast offload)."""
    api = get_api(host, user, password, insecure)
    try:
        n = NanoCdnStatus.model_validate(api.get_nanocdn() or {})

        if state.json:
            _emit_json(n.model_dump())
            return

        def _bps(v: Optional[int]) -> str:
            if v is None:
                return "-"
            if v >= 1_000_000:
                return f"{v / 1_000_000:.2f} Mbps"
            if v >= 1_000:
                return f"{v / 1_000:.1f} kbps"
            return f"{v} bps"

        table = Table(title="NanoCDN")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row(
            "Status",
            ("[green]running[/green]" if n.status == 1 else f"raw={n.status}")
            if n.status is not None else "-",
        )
        table.add_row(
            "Sessions (now / min / max)",
            f"{n.sessions if n.sessions is not None else '-'}"
            f" / {n.min_sessions if n.min_sessions is not None else '-'}"
            f" / {n.max_sessions if n.max_sessions is not None else '-'}",
        )
        table.add_row(
            "Mcast bitrate (now / min / max)",
            f"{_bps(n.mcast_bitrate)} / {_bps(n.min_mcast_bitrate)} / {_bps(n.max_mcast_bitrate)}",
        )
        table.add_row(
            "Mcast frames (lifetime)",
            str(n.mcast_frames) if n.mcast_frames is not None else "-",
        )
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------- wifi-advanced

@app.command("wifi-advanced")
def wifi_advanced(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show per-radio advanced Wi-Fi config (channel, BW, power, country)."""
    api = get_api(host, user, password, insecure)
    try:
        radios = [WifiRadioAdvanced.model_validate(r) for r in api.get_wifi_advanced()]

        if state.json:
            _emit_json([r.model_dump() for r in radios])
            return

        table = Table(title=f"Wi-Fi radios — advanced ({len(radios)})")
        table.add_column("Radio", style="cyan")
        table.add_column("Band", style="magenta")
        table.add_column("Channel")
        table.add_column("Width")
        table.add_column("TxPower")
        table.add_column("Country", style="dim")
        table.add_column("Standard", style="dim")
        for r in radios:
            ch = (
                f"{r.channel} ([dim]auto[/dim])" if r.auto_channel and r.channel is not None
                else (str(r.channel) if r.channel is not None else "-")
            )
            table.add_row(
                r.id or "-",
                r.band or "-",
                ch,
                r.bandwidth or "-",
                r.tx_power or "-",
                r.country_code or "-",
                r.standard or "-",
            )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------ wifi-acl

@app.command("wifi-acl")
def wifi_acl(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show per-SSID MAC filter policy + the configured ACL rules."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_wifi_mac_filter()
        policies = [WifiAclPolicy.model_validate(r) for r in data.get("OBJ_WLANACL_ID", [])]
        rules = [WifiAclRule.model_validate(r) for r in data.get("OBJ_ACLCFG_ID", [])]

        if state.json:
            _emit_json({
                "policies": [p.model_dump() for p in policies],
                "rules": [r.model_dump() for r in rules],
            })
            return

        pol_table = Table(title=f"MAC filter policy ({len(policies)})")
        pol_table.add_column("SSID", style="cyan")
        pol_table.add_column("AP ID", style="dim")
        pol_table.add_column("Policy", style="magenta")
        for p in policies:
            label = p.policy or "-"
            if label.lower() == "disabled":
                label = f"[dim]{label}[/dim]"
            pol_table.add_row(p.alias or "-", p.id or "-", label)
        console.print(pol_table)

        if not rules:
            console.print(
                "[dim]No MAC ACL entries configured "
                "(rules apply only when an SSID's policy is Allow/Deny).[/dim]"
            )
            return

        rule_table = Table(title=f"MAC ACL entries ({len(rules)})")
        rule_table.add_column("MAC", style="cyan")
        rule_table.add_column("AP / parent", style="green")
        rule_table.add_column("ID", style="dim")
        for r in rules:
            rule_table.add_row(r.mac or "-", r.ap_id or "-", r.id or "-")
        console.print(rule_table)
    finally:
        api.close()


# ------------------------------------------------------------ wifi-schedule

_DAY_NAMES = [
    ("day_mon", "Mon"),
    ("day_tue", "Tue"),
    ("day_wed", "Wed"),
    ("day_thu", "Thu"),
    ("day_fri", "Fri"),
    ("day_sat", "Sat"),
    ("day_sun", "Sun"),
]


def _schedule_days(s: WifiSchedule) -> str:
    flags = [name for attr, name in _DAY_NAMES if getattr(s, attr)]
    if not flags:
        return "[dim]no days[/dim]"
    if len(flags) == 7:
        return "every day"
    return ",".join(flags)


def _schedule_window(s: WifiSchedule) -> str:
    if any(v is None for v in (s.start_hour, s.start_min, s.end_hour, s.end_min)):
        return "-"
    return f"{s.start_hour:02d}:{s.start_min:02d} - {s.end_hour:02d}:{s.end_min:02d}"


_SCHEDULE_ACTION_LABEL = {
    0: "Wi-Fi OFF in window",
    1: "Wi-Fi ON in window",
}


@app.command("wifi-schedule")
def wifi_schedule(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show recurring Wi-Fi on/off schedules per AP."""
    api = get_api(host, user, password, insecure)
    try:
        schedules = [WifiSchedule.model_validate(r) for r in api.get_wifi_schedule()]

        if state.json:
            _emit_json([s.model_dump() for s in schedules])
            return

        table = Table(title=f"Wi-Fi schedule ({len(schedules)})")
        table.add_column("AP", style="cyan")
        table.add_column("State")
        table.add_column("Window", style="magenta")
        table.add_column("Days", style="green")
        table.add_column("Action")
        for s in schedules:
            action = _SCHEDULE_ACTION_LABEL.get(s.action, str(s.action) if s.action is not None else "-")
            table.add_row(
                (s.id or "-").rsplit(".", 1)[-1],
                _onoff(s.enabled),
                _schedule_window(s),
                _schedule_days(s),
                action,
            )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------- band-steering

@app.command("band-steering")
def band_steering(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show EasyMesh + band-steering master switches."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_band_steering()
        mesh_rows = data.get("OBJ_EASYMESHENABLE_ID", [])
        bs_rows = data.get("OBJ_BANDSTEERENABLE_ID", [])
        mesh = EasyMeshState.model_validate(mesh_rows[0] if mesh_rows else {})
        bs = BandSteeringState.model_validate(bs_rows[0] if bs_rows else {})

        if state.json:
            _emit_json({
                "easy_mesh": mesh.model_dump(),
                "band_steering": bs.model_dump(),
            })
            return

        table = Table(title="EasyMesh / band steering")
        table.add_column("Feature", style="cyan")
        table.add_column("State", style="magenta")
        table.add_row("EasyMesh", _onoff(mesh.enabled))
        table.add_row("Band steering", _onoff(bs.enabled))
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------ topology

@app.command()
def topology(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show EasyMesh topology (controller + agent layers)."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_topology()
        controller_raw = data.get("controllerData") or {}
        controller = (
            TopologyController.model_validate(controller_raw)
            if controller_raw
            else None
        )

        def _agents(layer: Dict[str, Any]) -> List[TopologyAgent]:
            instances = layer.get("Instance") or []
            if isinstance(instances, dict):
                instances = [instances]
            return [TopologyAgent.model_validate(i) for i in instances]

        layer1 = data.get("agentlay1") or {}
        layer2 = data.get("agentlay2") or {}
        agents1 = _agents(layer1)
        agents2 = _agents(layer2)

        if state.json:
            _emit_json({
                "controller": controller.model_dump() if controller else None,
                "agentlay1": {
                    "count": layer1.get("MGET_INST_NUM", 0),
                    "agents": [a.model_dump() for a in agents1],
                },
                "agentlay2": {
                    "count": layer2.get("MGET_INST_NUM", 0),
                    "agents": [a.model_dump() for a in agents2],
                },
            })
            return

        if controller:
            table = Table(title="Mesh controller")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="magenta")
            table.add_row("Device", controller.device_name or "-")
            table.add_row("Manufacturer", controller.manufacturer or "-")
            table.add_row("Software", controller.software_version or "-")
            table.add_row("IP", controller.ip_address or "-")
            table.add_row("MAC", controller.mac or "-")
            table.add_row("Access type", controller.access_type or "-")
            table.add_row("Link speed", controller.link_speed or "-")
            table.add_row("BH STA RSSI", controller.bh_sta_rssi or "-")
            table.add_row(
                "Associated devices",
                str(controller.associated_devices)
                if controller.associated_devices is not None
                else "-",
            )
            console.print(table)
        else:
            console.print("[yellow]No controller data returned.[/yellow]")

        for label, layer, agents in (
            ("Mesh agents (layer 1)", layer1, agents1),
            ("Mesh agents (layer 2)", layer2, agents2),
        ):
            count = layer.get("MGET_INST_NUM", 0)
            if not agents:
                console.print(f"[dim]{label}: none (MGET_INST_NUM={count})[/dim]")
                continue
            agent_table = Table(title=f"{label} ({count})")
            agent_table.add_column("Device", style="cyan")
            agent_table.add_column("MAC", style="white")
            agent_table.add_column("IP", style="white")
            agent_table.add_column("Access", style="magenta")
            agent_table.add_column("Link", style="green")
            agent_table.add_column("RSSI", style="yellow")
            agent_table.add_column("SW", style="dim")
            for a in agents:
                agent_table.add_row(
                    a.device_name or "-",
                    a.mac or "-",
                    a.ip_address or "-",
                    a.access_type or "-",
                    a.link_speed or "-",
                    a.bh_sta_rssi or "-",
                    a.software_version or "-",
                )
            console.print(agent_table)
    finally:
        api.close()


def _render_generic_rows(
    title: str, rows: List[Dict[str, str]], empty_msg: str
) -> None:
    """Render a list of XML instances when the schema isn't known.

    Used for endpoints that are empty on stock TIM Hub+ (firewall
    rules, parental control). When rules eventually exist, the table
    auto-derives columns from the union of keys preserving order of
    first appearance.
    """
    if not rows:
        console.print(f"[dim]{empty_msg}[/dim]")
        return
    cols: List[str] = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                cols.append(k)
    table = Table(title=title)
    for c in cols:
        table.add_column(c, style="cyan" if c.lower().endswith("id") else "white")
    for r in rows:
        table.add_row(*[str(r.get(c, "")) for c in cols])
    console.print(table)


_RTP_PT_NAME = {
    "0": "G.711µ (PCMU)",
    "8": "G.711a (PCMA)",
    "9": "G.722",
    "18": "G.729",
}


# ---------------------------------------------------------------- voip-media

@app.command("voip-media")
def voip_media(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show SIP codec preferences per line (3 codecs × 2 VL lines)."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_voip_media()
        codecs = data.get("OBJ_VOIPLINEVMEDAI_ID", [])
        if state.json:
            _emit_json({
                "lines": data.get("OBJ_VOIPVPLINE_ID", []),
                "codecs": codecs,
            })
            return
        if not codecs:
            console.print("[yellow]No VoIP media data returned.[/yellow]")
            return
        table = Table(title="VoIP SIP media codecs")
        table.add_column("Line", style="cyan")
        table.add_column("Slot", style="dim")
        table.add_column("Priority", style="magenta")
        table.add_column("Enabled", style="green")
        table.add_column("RTP PT", style="white")
        table.add_column("Codec", style="white")
        table.add_column("Clock", style="dim")
        table.add_column("Ptime", style="dim")
        for c in codecs:
            inst = c.get("_InstID", "")
            # Format: IGD.SV.VS1.VP1.VL{n}.LC.CL{m}
            line = "-"
            slot = "-"
            parts = inst.split(".")
            for p in parts:
                if p.startswith("VL"):
                    line = p
                elif p.startswith("CL"):
                    slot = p
            pt = c.get("MediaVPV", "")
            pt_name = _RTP_PT_NAME.get(pt, f"PT {pt}" if pt else "-")
            try:
                enabled = int(c.get("MediaVEnable", "0"))
            except (TypeError, ValueError):
                enabled = None
            table.add_row(
                line, slot,
                c.get("MediaVPri", "-"),
                _onoff(enabled),
                pt or "-",
                pt_name,
                c.get("MediaVCR", "-"),
                c.get("MediaVPT", "-"),
            )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------ voip-pos

@app.command("voip-pos")
def voip_pos(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show VoIP POS (port-on-off) toggles per VoIP slot."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_voip_pos()
        if state.json:
            _emit_json(rows)
            return
        if not rows:
            console.print("[yellow]No VoIP POS data returned.[/yellow]")
            return
        table = Table(title="VoIP POS toggles")
        table.add_column("Slot", style="cyan")
        table.add_column("Enabled", style="magenta")
        for r in rows:
            try:
                enabled = int(r.get("VoipPosEnable", "0"))
            except (TypeError, ValueError):
                enabled = None
            table.add_row(r.get("_InstID", "-"), _onoff(enabled))
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------- usb-devs

@app.command("usb-devs")
def usb_devs(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show attached USB storage devices (empty when no stick plugged)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_usb_devs()
        if state.json:
            _emit_json(rows)
            return
        _render_generic_rows(
            "USB storage devices", rows,
            "No USB storage device attached.",
        )
    finally:
        api.close()


# ----------------------------------------------------------- wifi-ssid-config

@app.command("wifi-ssid-config")
def wifi_ssid_config(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show full SSID configuration (hidden flag, max users, security)."""
    api = get_api(host, user, password, insecure)
    try:
        ssids = [WifiSsidConfig.model_validate(r) for r in api.get_wifi_ssid_config()]
        if state.json:
            _emit_json([s.model_dump() for s in ssids])
            return
        if not ssids:
            console.print("[yellow]No SSID config returned.[/yellow]")
            return
        table = Table(title="Wi-Fi SSID configuration")
        table.add_column("Alias", style="cyan")
        table.add_column("Radio", style="dim")
        table.add_column("ESSID", style="white")
        table.add_column("On", style="green")
        table.add_column("Hidden", style="yellow")
        table.add_column("Max users", style="magenta")
        table.add_column("Security", style="white")
        for s in ssids:
            sec_parts = []
            if s.beacon_type:
                sec_parts.append(s.beacon_type)
            auth = s.wpa2_auth_mode or s.wpa_auth_mode
            enc = s.wpa2_encrypt or s.wpa_encrypt
            if auth:
                sec_parts.append(auth)
            if enc:
                sec_parts.append(enc)
            table.add_row(
                s.alias or "-",
                s.radio_id or "-",
                s.essid or "-",
                _onoff(s.enabled),
                _onoff(s.hidden),
                str(s.max_users) if s.max_users is not None else "-",
                " / ".join(sec_parts) if sec_parts else "-",
            )
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------------------- sntp

@app.command("sntp")
def sntp(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show SNTP / time config (NTP servers, timezone, current time)."""
    api = get_api(host, user, password, insecure)
    try:
        row = api.get_sntp()
        cfg = SntpConfig.model_validate(row) if row else None
        if state.json:
            _emit_json(cfg.model_dump() if cfg else {})
            return
        if not cfg:
            console.print("[yellow]No SNTP data returned.[/yellow]")
            return
        table = Table(title="SNTP / time")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Current local time", cfg.current_local_time or "-")
        table.add_row(
            "Zone index",
            str(cfg.zone_index) if cfg.zone_index is not None else "-",
        )
        table.add_row("Auto timezone", _onoff(cfg.auto_set_tzname))
        table.add_row("Daylight saving", _onoff(cfg.daylight_savings_used))
        table.add_row(
            "Poll interval (s)",
            str(cfg.poll_time_interval) if cfg.poll_time_interval is not None else "-",
        )
        table.add_row(
            "DSCP",
            str(cfg.dscp) if cfg.dscp is not None else "-",
        )
        console.print(table)

        srv_table = Table(title="NTP servers")
        srv_table.add_column("#", style="cyan")
        srv_table.add_column("Hostname", style="white")
        servers = [
            ("1", cfg.ntp_server_1),
            ("2", cfg.ntp_server_2),
            ("3", cfg.ntp_server_3),
            ("4", cfg.ntp_server_4),
            ("5", cfg.ntp_server_5),
        ]
        for n, h in servers:
            srv_table.add_row(n, h or "-")
        console.print(srv_table)
    finally:
        api.close()


# --------------------------------------------------------------------- edns0

@app.command("edns0")
def edns0(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show EDNS0 (client-subnet) DNS extension toggle."""
    api = get_api(host, user, password, insecure)
    try:
        row = api.get_edns0()
        if state.json:
            _emit_json(row)
            return
        if not row:
            console.print("[yellow]No EDNS0 data returned.[/yellow]")
            return
        table = Table(title="EDNS0")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Instance", row.get("_InstID", "-"))
        enable_raw = row.get("EDNS0Enable")
        try:
            enable_val = int(enable_raw) if enable_raw is not None else None
        except (TypeError, ValueError):
            enable_val = None
        table.add_row("Enabled", _onoff(enable_val))
        console.print(table)
    finally:
        api.close()


# --------------------------------------------------------------- ipv6-prefix

@app.command("ipv6-prefix")
def ipv6_prefix(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show IPv6 prefix pool (DHCPv6-PD) and static prefixes."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_ipv6_prefix()
        if state.json:
            _emit_json(data)
            return
        _render_generic_rows(
            "IPv6 prefix pool (DHCPv6-PD)", data.get("pool", []),
            "No delegated IPv6 prefix from the ISP.",
        )
        _render_generic_rows(
            "IPv6 static prefixes", data.get("static", []),
            "No static IPv6 prefix configured.",
        )
    finally:
        api.close()


# ------------------------------------------------------------ firewall-ipfilter

@app.command("firewall-ipfilter")
def firewall_ipfilter(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show user-defined IP-filter rules + priority slot."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_firewall_ipfilter()
        if state.json:
            _emit_json(data)
            return
        _render_generic_rows(
            "IP filter rules", data.get("rules", []),
            "No IP-filter rules configured.",
        )
        _render_generic_rows(
            "IP filter priority", data.get("priority", []),
            "No IP-filter priority entry.",
        )
    finally:
        api.close()


# ----------------------------------------------------------- firewall-urlfilter

@app.command("firewall-urlfilter")
def firewall_urlfilter(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show per-URL filter rules (master toggle is in ``firewall``)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_firewall_urlfilter()
        if state.json:
            _emit_json(rows)
            return
        _render_generic_rows(
            "URL filter rules", rows,
            "No URL-filter rules configured.",
        )
    finally:
        api.close()


# URL-filter rules get instance ids shaped ``DEV.FW.CHAIN1.URLF<N>``.
# Accept a bare suffix and expand it, like the other write commands.
_FWURL_ID_PREFIX = "DEV.FW.CHAIN1.URLF"


@app.command("firewall-urlfilter-add")
def firewall_urlfilter_add(
    name: str = typer.Argument(..., help="Rule label (1–32 ASCII chars)."),
    url: str = typer.Argument(..., help="URL/host to block (1–128 chars)."),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Add a URL-filter rule (master toggle is in ``firewall``)."""
    api = get_api(host, user, password, insecure)
    try:
        ok, body = api.add_url_filter_rule(name=name, url=url)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Add failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        rows = api.get_firewall_urlfilter()
        new_rows = [r for r in rows if r.get("Url") == url and r.get("Name") == name]
        if state.json:
            _emit_json({"ok": True, "added": new_rows})
            return
        if new_rows:
            r = new_rows[-1]
            console.print(
                f"[green]Added[/green] URL filter "
                f"[bold]{r.get('_OBJ_InstID') or '?'}[/bold]: "
                f"([cyan]{r.get('Name')}[/cyan]) → {r.get('Url')}"
            )
        else:
            console.print(
                f"[green]Added[/green] URL filter [cyan]{name}[/cyan] "
                f"(modem returned SUCC but no matching row read back)."
            )
    finally:
        api.close()


@app.command("firewall-urlfilter-del")
def firewall_urlfilter_del(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Either the bare suffix (e.g. '1') or the "
            "full path 'DEV.FW.CHAIN1.URLF1' (as shown by `h388x firewall-urlfilter`)."
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt."
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Delete a URL-filter rule by ID."""
    inst_id = (
        rule_id
        if rule_id.startswith(_FWURL_ID_PREFIX)
        else f"{_FWURL_ID_PREFIX}{rule_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_firewall_urlfilter()
        target = next((r for r in rows if r.get("_OBJ_InstID") == inst_id), None)
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"rule {inst_id!r} not found"})
            else:
                console.print(f"[red]No URL filter with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        if not yes and not state.json:
            console.print(
                f"About to delete [bold]{inst_id}[/bold]: "
                f"([cyan]{target.get('Name')}[/cyan]) → {target.get('Url')}"
            )
            if not typer.confirm("Proceed?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=1)

        ok, body = api.del_url_filter_rule(inst_id)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Delete failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "deleted": inst_id})
        else:
            console.print(f"[green]Deleted[/green] URL filter [bold]{inst_id}[/bold].")
    finally:
        api.close()


# IP-filter rules get instance ids shaped ``DEV.FW.CHAIN1.IPF<N>``.
_FWIP_ID_PREFIX = "DEV.FW.CHAIN1.IPF"


@app.command("firewall-ipfilter-add")
def firewall_ipfilter_add(
    name: str = typer.Argument(..., help="Rule label (1–32 ASCII chars)."),
    protocol: str = typer.Argument(
        ..., help="ICMP | TCP | UDP (case-insensitive) or a raw 1–255 number."
    ),
    target: str = typer.Option(
        "allow", "--target",
        help="allow (default, never blocks traffic) or deny.",
    ),
    index: int = typer.Option(
        1, "--index", min=1, max=20, help="Rule priority slot (1–20)."
    ),
    disable: bool = typer.Option(
        False, "--disable", help="Create the rule disabled (defaults to enabled)."
    ),
    ip_version: str = typer.Option(
        "4", "--ip-version", help="IP version: 4, 6, or -1 (any).",
    ),
    src_ip: str = typer.Option("", "--src-ip", help="Source IP (empty = any)."),
    src_mask: str = typer.Option("", "--src-mask", help="Source IP mask/prefix."),
    dst_ip: str = typer.Option("", "--dst-ip", help="Destination IP (empty = any)."),
    dst_mask: str = typer.Option("", "--dst-mask", help="Destination IP mask/prefix."),
    src_port_min: str = typer.Option("", "--src-port-min", help="Source port range start."),
    src_port_max: str = typer.Option("", "--src-port-max", help="Source port range end."),
    dst_port_min: str = typer.Option("", "--dst-port-min", help="Dest port range start."),
    dst_port_max: str = typer.Option("", "--dst-port-max", help="Dest port range end."),
    dscp: str = typer.Option("", "--dscp", help="DSCP value (0–63)."),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Add an IP-filter rule. Default action is allow (safe)."""
    api = get_api(host, user, password, insecure)
    try:
        ok, body = api.add_ip_filter_rule(
            name=name, protocol=protocol, target=target,
            filter_index=index, enable=not disable, ip_version=ip_version,
            source_ip=src_ip, source_mask=src_mask,
            dest_ip=dst_ip, dest_mask=dst_mask,
            min_src_port=src_port_min, max_src_port=src_port_max,
            min_dst_port=dst_port_min, max_dst_port=dst_port_max,
            dscp=dscp,
        )
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Add failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)

        rows = api.get_firewall_ipfilter().get("rules", [])
        new_rows = [r for r in rows if r.get("Name") == name]
        if state.json:
            _emit_json({"ok": True, "added": new_rows})
            return
        if new_rows:
            r = new_rows[-1]
            act = "allow" if r.get("FilterTarget") == "1" else "deny"
            console.print(
                f"[green]Added[/green] IP filter "
                f"[bold]{r.get('_OBJ_InstID') or '?'}[/bold]: "
                f"([cyan]{r.get('Name')}[/cyan]) {act} proto={r.get('Protocol')} "
                f"{'enabled' if r.get('Enable') == '1' else 'disabled'}"
            )
        else:
            console.print(
                f"[green]Added[/green] IP filter [cyan]{name}[/cyan] "
                f"(modem returned SUCC but no matching row read back)."
            )
    finally:
        api.close()


@app.command("firewall-ipfilter-del")
def firewall_ipfilter_del(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Either the bare suffix (e.g. '1') or the "
            "full path 'DEV.FW.CHAIN1.IPF1' (as shown by `h388x firewall-ipfilter`)."
        ),
    ),
    yes: bool = typer.Option(
        False, "-y", "--yes", help="Skip the confirmation prompt."
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Delete an IP-filter rule by ID."""
    inst_id = (
        rule_id
        if rule_id.startswith(_FWIP_ID_PREFIX)
        else f"{_FWIP_ID_PREFIX}{rule_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_firewall_ipfilter().get("rules", [])
        target = next((r for r in rows if r.get("_OBJ_InstID") == inst_id), None)
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"rule {inst_id!r} not found"})
            else:
                console.print(f"[red]No IP filter with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        if not yes and not state.json:
            act = "allow" if target.get("FilterTarget") == "1" else "deny"
            console.print(
                f"About to delete [bold]{inst_id}[/bold]: "
                f"([cyan]{target.get('Name')}[/cyan]) {act} proto={target.get('Protocol')}"
            )
            if not typer.confirm("Proceed?"):
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=1)

        ok, body = api.del_ip_filter_rule(inst_id)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Delete failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "deleted": inst_id})
        else:
            console.print(f"[green]Deleted[/green] IP filter [bold]{inst_id}[/bold].")
    finally:
        api.close()


@app.command("firewall-ipfilter-toggle")
def firewall_ipfilter_toggle(
    rule_id: str = typer.Argument(
        ...,
        help=(
            "Rule _OBJ_InstID. Bare suffix (e.g. '1') or full path "
            "'DEV.FW.CHAIN1.IPF1'."
        ),
    ),
    enable: Optional[bool] = typer.Option(
        None, "--on/--off",
        help="Force enabled (--on) or disabled (--off). Default: flip current.",
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Enable/disable an IP-filter rule (keeps all other fields)."""
    inst_id = (
        rule_id
        if rule_id.startswith(_FWIP_ID_PREFIX)
        else f"{_FWIP_ID_PREFIX}{rule_id}"
    )
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_firewall_ipfilter().get("rules", [])
        target = next((r for r in rows if r.get("_OBJ_InstID") == inst_id), None)
        if target is None:
            if state.json:
                _emit_json({"ok": False, "error": f"rule {inst_id!r} not found"})
            else:
                console.print(f"[red]No IP filter with id[/red] [bold]{inst_id}[/bold].")
            raise typer.Exit(code=1)

        currently_on = target.get("Enable") == "1"
        new_state = (not currently_on) if enable is None else enable
        if new_state == currently_on:
            if state.json:
                _emit_json({"ok": True, "id": inst_id, "enabled": currently_on, "changed": False})
            else:
                console.print(
                    f"[yellow]Rule [bold]{inst_id}[/bold] already "
                    f"{'enabled' if currently_on else 'disabled'}.[/yellow]"
                )
            return

        ok, body = api.set_ip_filter_enabled(inst_id, new_state)
        if not ok:
            if state.json:
                _emit_json({"ok": False, "raw": body[:400]})
            else:
                console.print(
                    f"[red]Toggle failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
            raise typer.Exit(code=1)
        if state.json:
            _emit_json({"ok": True, "id": inst_id, "enabled": new_state, "changed": True})
        else:
            console.print(
                f"[green]{'Enabled' if new_state else 'Disabled'}[/green] "
                f"IP filter [bold]{inst_id}[/bold]."
            )
    finally:
        api.close()


# ------------------------------------------------------------- parental-control

@app.command("parental-control")
def parental_control(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show parental-control entries (MAC + time schedule bindings)."""
    api = get_api(host, user, password, insecure)
    try:
        rows = api.get_parental_control()
        if state.json:
            _emit_json(rows)
            return
        _render_generic_rows(
            "Parental control entries", rows,
            "No parental-control entries configured.",
        )
    finally:
        api.close()


# --------------------------------------------------------------- dsl-interface

@app.command("dsl-interface")
def dsl_interface(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show full DSL PHY status (rates, SNR margin, attenuation, errors)."""
    api = get_api(host, user, password, insecure)
    try:
        row = api.get_dsl_interface()
        dsl = DslInterface.model_validate(row) if row else None
        if state.json:
            _emit_json(dsl.model_dump() if dsl else {})
            return
        if not dsl:
            console.print("[yellow]No DSL interface data returned.[/yellow]")
            return

        meta = Table(title="DSL interface")
        meta.add_column("Field", style="cyan")
        meta.add_column("Value", style="magenta")
        meta.add_row("Instance", dsl.id or "-")
        meta.add_row("Enabled", _onoff(dsl.enabled))
        meta.add_row("Status", dsl.status or "-")
        meta.add_row("Module", dsl.module_type or "-")
        meta.add_row("Profile", dsl.profile or "-")
        meta.add_row("Data path", dsl.data_path or "-")
        meta.add_row("Encapsulation", dsl.encapsulation or "-")
        meta.add_row("Showtime start", dsl.showtime_start or "-")
        meta.add_row(
            "Link retrains",
            str(dsl.link_retrain) if dsl.link_retrain is not None else "-",
        )
        console.print(meta)

        rates = Table(title="DSL rates / line quality")
        rates.add_column("Metric", style="cyan")
        rates.add_column("Downstream", style="green")
        rates.add_column("Upstream", style="yellow")

        def s(v):
            return str(v) if v is not None else "-"

        rates.add_row("Current rate (kbps)",
                      s(dsl.downstream_current_rate), s(dsl.upstream_current_rate))
        rates.add_row("Max rate (kbps)",
                      s(dsl.downstream_max_rate), s(dsl.upstream_max_rate))
        rates.add_row("Noise margin (× 0.1 dB)",
                      s(dsl.downstream_noise_margin), s(dsl.upstream_noise_margin))
        rates.add_row("Attenuation (× 0.1 dB)",
                      s(dsl.downstream_attenuation), s(dsl.upstream_attenuation))
        rates.add_row("Power (× 0.1 dBm)",
                      s(dsl.downstream_power), s(dsl.upstream_power))
        rates.add_row("INP",
                      s(dsl.downstream_inp), s(dsl.upstream_inp))
        rates.add_row("Interleave delay (ms)",
                      s(dsl.downstream_interleave_delay), s(dsl.upstream_interleave_delay))
        rates.add_row("Interleave depth",
                      s(dsl.downstream_interleave_depth), s(dsl.upstream_interleave_depth))
        rates.add_row("CRC errors",
                      s(dsl.downstream_crc_errors), s(dsl.upstream_crc_errors))
        console.print(rates)

        errs = Table(title="DSL FEC errors")
        errs.add_column("Counter", style="cyan")
        errs.add_column("Value", style="magenta")
        errs.add_row("FEC errors (CPE)", s(dsl.fec_errors))
        errs.add_row("FEC errors (ATU-C)", s(dsl.atuc_fec_errors))
        console.print(errs)
    finally:
        api.close()


# --------------------------------------------------------------- admin-users

@app.command("admin-users")
def admin_users(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """List web admin accounts configured on the modem."""
    api = get_api(host, user, password, insecure)
    try:
        users = [AdminUser.model_validate(r) for r in api.get_admin_users()]
        if state.json:
            _emit_json([u.model_dump() for u in users])
            return
        if not users:
            console.print("[yellow]No admin users returned.[/yellow]")
            return
        table = Table(title="Web admin accounts")
        table.add_column("ID", style="dim")
        table.add_column("Username", style="cyan")
        table.add_column("Right", style="magenta")
        for u in users:
            table.add_row(u.id or "-", u.username or "-", u.right or "-")
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------- web-login-timeout

@app.command("web-timeout")
def web_timeout(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    set_minutes: Optional[int] = typer.Option(
        None,
        "--set",
        metavar="MINUTES",
        help=(
            "Set a new idle timeout in minutes (1–60). Without this flag "
            "the command just reads the current value."
        ),
        min=1,
        max=60,
    ),
):
    """Show or update the web UI idle session timeout (minutes)."""
    api = get_api(host, user, password, insecure)
    try:
        if set_minutes is not None:
            ok, body = api.set_web_login_timeout(set_minutes)
            if not ok:
                if state.json:
                    _emit_json({"ok": False, "raw": body[:400]})
                    raise typer.Exit(code=1)
                console.print(
                    f"[red]Set failed.[/red] Modem replied:\n[dim]{body[:400]}[/dim]"
                )
                raise typer.Exit(code=1)
            # Read back to confirm and surface the actual stored value.
            row = api.get_web_login_timeout()
            tm = WebLoginTimeout.model_validate(row) if row else None
            if state.json:
                _emit_json({"ok": True, **(tm.model_dump() if tm else {})})
                return
            console.print(
                f"[green]Updated[/green] web idle timeout → "
                f"[bold]{tm.timeout if tm else set_minutes}[/bold] minutes."
            )
            return

        row = api.get_web_login_timeout()
        tm = WebLoginTimeout.model_validate(row) if row else None
        if state.json:
            _emit_json(tm.model_dump() if tm else {})
            return
        if not tm:
            console.print("[yellow]No timeout data returned.[/yellow]")
            return
        table = Table(title="Web login timeout")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Instance", tm.id or "-")
        table.add_row(
            "Timeout (min)",
            str(tm.timeout) if tm.timeout is not None else "-",
        )
        console.print(table)
    finally:
        api.close()


# ------------------------------------------------------------------ mobile-wan

@app.command("mobile-wan")
def mobile_wan(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show 3G/4G USB dongle backup status (if any)."""
    api = get_api(host, user, password, insecure)
    try:
        data = api.get_mobile_wan()
        dongle = data.get("dongle", {}) or {}
        info_raw = data.get("info", {}) or {}
        info = MobileWanInfo.model_validate(info_raw) if info_raw else None

        if state.json:
            _emit_json({
                "dongle": dongle,
                "info": info.model_dump() if info else {},
            })
            return

        table = Table(title="Mobile WAN dongle")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Dongle status", dongle.get("DongleStatus", "-"))
        table.add_row("Dev type", dongle.get("DevType", "-"))
        table.add_row("Dongle type", dongle.get("DongleType", "-"))
        if info:
            table.add_row("Operator", info.operator or "-")
            table.add_row(
                "Signal",
                str(info.signal_strength) if info.signal_strength is not None else "-",
            )
            table.add_row("IMEI", info.imei or "-")
            table.add_row("Network mode", info.network_mode or "-")
            table.add_row(
                "Alarm", str(info.alarm) if info.alarm is not None else "-"
            )
        console.print(table)
    finally:
        api.close()


# ----------------------------------------------------------------- public-lan

@app.command("public-lan")
def public_lan(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Show secondary 'public LAN' interface status (hotspot/guest slot)."""
    api = get_api(host, user, password, insecure)
    try:
        row = api.get_public_lan()
        pl = PublicLan.model_validate(row) if row else None
        if state.json:
            _emit_json(pl.model_dump() if pl else {})
            return
        if not pl:
            console.print("[yellow]No public LAN data returned.[/yellow]")
            return
        table = Table(title="Public LAN")
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Instance", pl.id or "-")
        table.add_row("Enabled", pl.enabled or "-")
        table.add_row("Public IP", pl.public_ip or "-")
        table.add_row("Public mask", pl.public_mask or "-")
        console.print(table)
    finally:
        api.close()


_HEALTH_GLYPH = {
    "ok": "[bold green]✓ OK[/bold green]",
    "warn": "[yellow]⚠ WARN[/yellow]",
    "fail": "[bold red]✗ FAIL[/bold red]",
    "info": "[dim]· INFO[/dim]",
}


def _health_row(status: str, area: str, detail: str):
    return _HEALTH_GLYPH.get(status, status), area, detail


# --------------------------------------------------------------------- health

@app.command()
def health(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """One-shot status overview (info + DSL + WAN + VoIP + mesh)."""
    api = get_api(host, user, password, insecure)
    rows: List[tuple] = []
    summary: Dict[str, Any] = {}
    try:
        # --- Device info ----------------------------------------------------
        try:
            info_raw = api.get_device_info()
            d = DeviceInfo.model_validate(info_raw) if info_raw else None
        except Exception:
            d = None
        if d:
            rows.append(_health_row(
                "ok", "Modem",
                f"{d.model or '?'} · {d.software_version or '?'} · SN {d.serial_number or '?'}",
            ))
            summary["modem"] = {
                "status": "ok",
                "model": d.model, "software": d.software_version,
                "serial": d.serial_number,
            }
        else:
            rows.append(_health_row("fail", "Modem", "no device info returned"))
            summary["modem"] = {"status": "fail"}

        # --- DSL line -------------------------------------------------------
        try:
            dsl_raw = api.get_dsl_stats()
            s = DSLStats.model_validate(dsl_raw) if dsl_raw else None
        except Exception:
            s = None
        if s and (s.status or "").lower() == "up":
            rows.append(_health_row(
                "ok", "DSL",
                f"{s.module_type or 'DSL'} {s.profile or ''} · "
                f"↓{s.downstream_curr_rate or 0}/↑{s.upstream_curr_rate or 0} kbps",
            ))
            summary["dsl"] = {
                "status": "ok",
                "line_status": s.status,
                "downstream_kbps": s.downstream_curr_rate,
                "upstream_kbps": s.upstream_curr_rate,
            }
        elif s:
            rows.append(_health_row(
                "fail", "DSL", f"line status: {s.status or 'unknown'}"
            ))
            summary["dsl"] = {"status": "fail", "line_status": s.status}
        else:
            rows.append(_health_row("warn", "DSL", "no data"))
            summary["dsl"] = {"status": "warn"}

        # --- WAN connections ------------------------------------------------
        try:
            wan_rows = api.get_wan_connections()
        except Exception:
            wan_rows = []
        wan_list = [WanConnection.model_validate(r) for r in wan_rows]
        connected = [w for w in wan_list if (w.status or "").lower() == "connected"]
        if connected:
            for w in connected:
                rows.append(_health_row(
                    "ok", f"WAN/{w.name or '?'}",
                    f"{w.ip_address or '-'} via {w.gateway or '-'} · "
                    f"up {w.uptime_seconds if w.uptime_seconds is not None else '?'}s",
                ))
            summary["wan"] = {
                "status": "ok",
                "connected": [w.model_dump() for w in connected],
            }
        else:
            rows.append(_health_row("fail", "WAN", "no Connected interface"))
            summary["wan"] = {"status": "fail", "connected": []}

        # --- VoIP SIP lines -------------------------------------------------
        # SIP rows carry the registered phone number (``AuthUserName``) and
        # the Italian-language state (``IsOnline``: ``Registrato`` /
        # ``Non registrato``), which is what the health view needs.
        try:
            voip_data = api.get_voip_status()
        except Exception:
            voip_data = {}
        sip_rows = voip_data.get("OBJ_VOIPSIPLINE_ID", []) if voip_data else []
        sip_lines = [VoipSipLine.model_validate(r) for r in sip_rows]
        voip_summary = []
        for sl in sip_lines:
            state_label = (sl.is_online or "").strip()
            lower = state_label.lower()
            registered = lower.startswith("registrat") and "non" not in lower
            status = "ok" if registered else "warn"
            label = sl.phone_name or (sl.id or "SIP?")
            number = sl.auth_username or "-"
            rows.append(_health_row(
                status, f"VoIP/{label}",
                f"{number} · {state_label or 'unknown'}",
            ))
            voip_summary.append({
                "id": sl.id,
                "phone_name": sl.phone_name,
                "number": sl.auth_username,
                "is_online": sl.is_online,
                "status": status,
            })
        summary["voip"] = voip_summary

        # --- Mesh / controller ---------------------------------------------
        try:
            topo = api.get_topology()
        except Exception:
            topo = {}
        ctrl = (topo or {}).get("controllerData") or {}
        layer1 = (topo or {}).get("agentlay1") or {}
        layer2 = (topo or {}).get("agentlay2") or {}
        agents = (layer1.get("MGET_INST_NUM") or 0) + (layer2.get("MGET_INST_NUM") or 0)
        if ctrl:
            rows.append(_health_row(
                "info" if agents == 0 else "ok",
                "Mesh",
                f"controller {ctrl.get('DeviceName', '?')} · "
                f"{ctrl.get('accdevCount', 0)} clients · {agents} agents",
            ))
            summary["mesh"] = {
                "controller": ctrl.get("DeviceName"),
                "associated_devices": ctrl.get("accdevCount"),
                "agents": agents,
            }
        else:
            rows.append(_health_row("warn", "Mesh", "no controller data"))
            summary["mesh"] = {"status": "warn"}

        if state.json:
            _emit_json(summary)
            return

        table = Table(title="H388X health overview")
        table.add_column("Status", no_wrap=True)
        table.add_column("Area", style="cyan", no_wrap=True)
        table.add_column("Detail", style="white")
        for r in rows:
            table.add_row(*r)
        console.print(table)
    finally:
        api.close()


# ---------------------------------------------------------------------- watch

@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def watch(
    ctx: typer.Context,
    interval: float = typer.Argument(
        ...,
        help="Refresh every N seconds (decimals allowed).",
        min=0.1,
    ),
    keep_going: bool = typer.Option(
        False,
        "--keep-going",
        help="Continue refreshing when the child command exits non-zero.",
    ),
    command: List[str] = typer.Argument(
        ...,
        help=(
            "h388x subcommand to repeat, with its own flags. "
            "Example: `h388x watch 5 voip` or `h388x watch 2 clients --leases`."
        ),
    ),
):
    """Re-run any h388x command in a loop (Unix watch(1) style).

    By default a failed child command stops the wrapper and propagates its
    exit status. Use ``--keep-going`` only when repeated retries are intended.
    """
    import shutil
    import subprocess

    h388x_bin = shutil.which("h388x")
    if h388x_bin:
        argv = [h388x_bin, *command]
    else:
        argv = [sys.executable, "-m", "h388x_cli.cli", *command]

    clear_cmd = "cls" if os.name == "nt" else "clear"
    try:
        while True:
            os.system(clear_cmd)
            result = subprocess.run(argv, check=False)
            if result.returncode and not keep_going:
                code = result.returncode if 1 <= result.returncode <= 255 else 1
                raise typer.Exit(code=code)
            if result.returncode and keep_going:
                console.print(
                    f"[yellow]Child command exited {result.returncode}; retrying.[/yellow]"
                )
            time.sleep(interval)
    except KeyboardInterrupt:
        return

# --------------------------------------------------------------------- logout

@app.command()
def logout(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Log out of the modem and clear the cached session for this host.

    A valid cached SID/token is enough: unlike ordinary commands, logout does
    not require the admin password merely to reuse and release that session.
    """
    resolved_password = password or os.environ.get("H388X_PASSWORD") or ""
    api = ZTEH388XAPI(
        host=host,
        username=user,
        password=resolved_password,
        verify_tls=not insecure,
    )
    try:
        if not api.has_cached_session:
            if not resolved_password:
                if state.json:
                    _emit_json({
                        "logout": "failed",
                        "error": "no cached session and no password available",
                    })
                else:
                    console.print(
                        "[red]No cached session and no password available.[/red]"
                    )
                raise typer.Exit(code=1)
            if not api.login():
                if state.json:
                    _emit_json({"logout": "failed", "error": "login failed"})
                else:
                    console.print("[red]Login failed.[/red]")
                raise typer.Exit(code=1)

        api.logout()
        if state.json:
            _emit_json({"logout": "ok"})
        else:
            console.print("[green]Session terminated and cache cleared.[/green]")
    except typer.Exit:
        raise
    except Exception as exc:
        if state.json:
            _emit_json({"logout": "failed", "error": str(exc)})
        else:
            console.print(f"[red]Logout failed: {exc}[/red]")
        raise typer.Exit(code=1)
    finally:
        try:
            api.close()
        except Exception:
            pass

# --------------------------------------------------------------------- reboot

@app.command()
def reboot(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Reboot the modem."""
    if not yes and not typer.confirm("Are you sure you want to reboot the modem?"):
        raise typer.Abort()
    api = get_api(host, user, password, insecure)
    try:
        ok = api.reboot()
        if state.json:
            _emit_json({"reboot": "ok" if ok else "failed"})
        elif ok:
            console.print(
                "[bold green]Reboot command sent. The modem is restarting...[/bold green]"
            )
        else:
            console.print("[red]Failed to send reboot command.[/red]")
        if not ok:
            raise typer.Exit(code=1)
    finally:
        api.close()


# --------------------------------------------------------------------- config

config_app = typer.Typer(
    help="Modem configuration management (backup).",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")


@config_app.command("backup")
def config_backup(
    file: Optional[str] = typer.Argument(
        None,
        help=(
            "Output file for the config backup. Defaults to "
            "`config-YYYYmmdd-HHMMSS.bin` in the current directory."
        ),
    ),
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Download the full modem configuration backup (config.bin).

    Read-only / non-destructive: it just exports the current settings.
    Keep this snapshot before any risky change as a safety net.
    """
    out = file or time.strftime("config-%Y%m%d-%H%M%S.bin")
    api = get_api(host, user, password, insecure)
    try:
        ok, result = api.download_config_backup()
    finally:
        api.close()

    if not ok:
        if state.json:
            _emit_json({"ok": False, "error": str(result)})
        else:
            console.print(f"[red]Backup failed:[/red] {result}")
        raise typer.Exit(code=1)

    data: bytes = result
    try:
        _write_private_bytes(Path(out), data)
    except FileExistsError:
        message = f"refusing to overwrite existing file: {out}"
        if state.json:
            _emit_json({"ok": False, "error": message})
        else:
            console.print(f"[red]Backup failed:[/red] {message}")
        raise typer.Exit(code=1)
    except OSError as exc:
        if state.json:
            _emit_json({"ok": False, "error": str(exc)})
        else:
            console.print(f"[red]Backup failed:[/red] {exc}")
        raise typer.Exit(code=1)
    digest = hashlib.sha256(data).hexdigest()

    if state.json:
        _emit_json({"ok": True, "file": out, "bytes": len(data), "sha256": digest})
    else:
        console.print(
            f"[green]Saved[/green] config backup to [bold]{out}[/bold] "
            f"({len(data)} bytes)"
        )
        console.print(f"  sha256: [dim]{digest}[/dim]")


# --------------------------------------------------------- network diagnostics

@app.command()
def ping(
    host: str = typer.Argument(..., help="Target host or IP to ping."),
    host_opt: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Ping a host from the modem (runs on the gateway, not this machine).

    The modem's ping form only takes a target host; count/size/timeout are
    fixed server-side (4 x 56 bytes).
    """
    api = get_api(host_opt, user, password, insecure)
    try:
        if state.json:
            ok, result = api.ping(host)
        else:
            with console.status(f"[bold green]Pinging {host} from the modem..."):
                ok, result = api.ping(host)
    finally:
        api.close()

    if state.json:
        _emit_json({"ok": ok, "host": host, "result": result})
        if not ok:
            raise typer.Exit(code=1)
        return
    if not ok:
        console.print(f"[red]Ping failed:[/red] {result}")
        raise typer.Exit(code=1)
    console.print(result, markup=False, emoji=False, highlight=False)


@app.command()
def traceroute(
    host: str = typer.Argument(..., help="Target host or IP to trace."),
    max_hops: int = typer.Option(30, "--max-hops", "-m", help="Maximum hop count."),
    timeout_ms: int = typer.Option(
        5000, "--timeout", help="Per-probe timeout in milliseconds."
    ),
    protocol: str = typer.Option("UDP", "--protocol", help="Probe protocol (UDP/ICMP)."),
    host_opt: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
):
    """Traceroute to a host from the modem (runs on the gateway)."""
    api = get_api(host_opt, user, password, insecure)
    try:
        if state.json:
            ok, result = api.traceroute(
                host, max_hops=max_hops,
                timeout_ms=timeout_ms, protocol=protocol,
            )
        else:
            with console.status(f"[bold green]Tracing route to {host} from the modem..."):
                ok, result = api.traceroute(
                    host, max_hops=max_hops,
                    timeout_ms=timeout_ms, protocol=protocol,
                )
    finally:
        api.close()

    if state.json:
        _emit_json({"ok": ok, "host": host, "result": result})
        if not ok:
            raise typer.Exit(code=1)
        return
    if not ok:
        console.print(f"[red]Traceroute failed:[/red] {result}")
        raise typer.Exit(code=1)
    console.print(result, markup=False, emoji=False, highlight=False)


# -------------------------------------------------------------- capabilities

@app.command()
def capabilities(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    report: str = typer.Option(
        "endpoints.json",
        "--report",
        "-r",
        help="Optional local discovery report used to mark observed endpoints.",
    ),
):
    """Show firmware identity and the read/write capability inventory.

    This command performs only authenticated GET requests. If ``--report``
    points to an existing discovery JSON, its endpoint observations are merged
    into the output without exposing report samples or serial numbers.
    """
    api = get_api(host, user, password, insecure)
    try:
        try:
            dev = api.get_device_info() or {}
        except Exception:
            dev = {}

        report_path = Path(report)
        discovery = None
        if report_path.exists():
            try:
                discovery = load_discovery_report(report_path)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                message = f"invalid discovery report {report}: {exc}"
                if state.json:
                    _emit_json({"ok": False, "error": message})
                else:
                    console.print(f"[red]Capabilities failed:[/red] {message}")
                raise typer.Exit(code=1)

        device = {
            "host": getattr(api, "base_url", host),
            "model": dev.get("ModelName"),
            "software": dev.get("SoftwareVer"),
            "hardware": dev.get("HardwareVer"),
            "boot": dev.get("BootVer"),
            "firmware_date": dev.get("VerDate"),
        }
        payload = build_capabilities(
            device=device,
            discovery=discovery,
            discovery_path=report_path if discovery is not None else None,
        )

        if state.json:
            _emit_json(payload)
            return

        table = Table(title="H388X capabilities")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="magenta")
        for key, label in (
            ("model", "Model"),
            ("software", "Firmware"),
            ("hardware", "Hardware"),
            ("boot", "Boot"),
            ("firmware_date", "Firmware date"),
        ):
            table.add_row(label, str(payload["device"].get(key) or "N/A"))
        table.add_row("Catalog entries", str(payload["coverage"]["total"]))
        if payload["discovery"] is not None:
            stats = payload["discovery"]["stats"]
            table.add_row("Discovery endpoints", str(stats.get("endpoint_count", "N/A")))
            table.add_row("Discovery with data", str(stats.get("endpoints_with_data", "N/A")))
        console.print(table)

        status_table = Table(title="Coverage by status")
        status_table.add_column("Status", style="cyan")
        status_table.add_column("Count", style="magenta")
        for status, count in payload["coverage"]["by_status"].items():
            status_table.add_row(status, str(count))
        console.print(status_table)
        gaps = [
            item for item in payload["capabilities"]
            if item["status"] != "covered"
        ]
        if gaps:
            gap_table = Table(title="Open gaps")
            gap_table.add_column("Capability", style="cyan")
            gap_table.add_column("Status", style="yellow")
            gap_table.add_column("Page", style="magenta")
            for item in gaps:
                gap_table.add_row(item["id"], item["status"], item["page"])
            console.print(gap_table)
    finally:
        api.close()


# ------------------------------------------------------------------- discover

@app.command()
def discover(
    host: str = _host_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    insecure: bool = _insecure_opt(),
    output: str = typer.Option(
        "endpoints.json",
        "--output",
        "-o",
        help="Where to write the discovery report (JSON).",
    ),
    max_requests: int = typer.Option(
        400, "--max-requests", min=1, help="Stop after this many HTTP requests."
    ),
    delay: float = typer.Option(
        0.15, "--delay", min=0.0, help="Seconds to sleep between HTTP requests."
    ),
    sample_chars: int = typer.Option(
        600,
        "--sample-chars",
        min=1,
        help="Per-endpoint response sample size (chars) saved in the report.",
    ),
    previous: Optional[str] = typer.Option(
        None,
        "--previous",
        help="Compare the new report with a previous discovery JSON file.",
    ),
):
    """
    Spider the modem web UI and dump every reachable
    `_type=...&_tag=...` endpoint to a JSON file.

    Read-only: only HTTP GET, mutating-looking tags are listed but not fetched.
    Useful to extend the CLI with new commands without guessing endpoints.
    """
    previous_report: Optional[Dict[str, Any]] = None
    if previous:
        try:
            previous_report = load_discovery_report(Path(previous))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            message = f"invalid previous discovery report {previous}: {exc}"
            if state.json:
                _emit_json({"ok": False, "error": message})
            else:
                console.print(f"[red]Discovery failed:[/red] {message}")
            raise typer.Exit(code=1)

    api = get_api(host, user, password, insecure)

    progress_msg = {"text": "starting..."}

    def cb(msg: str, done: int, total: int) -> None:
        progress_msg["text"] = f"{done}/{total}  {msg}"

    try:
        if state.json:
            spider = Spider(
                api,
                max_requests=max_requests,
                delay=delay,
                sample_chars=sample_chars,
            )
            result = spider.run()
        else:
            with console.status(
                "[bold green]Spidering modem web UI...",
                spinner="dots",
            ) as status:
                def cb_console(msg: str, done: int, total: int) -> None:
                    status.update(
                        f"[bold green]Spidering modem web UI[/bold green]  "
                        f"[dim]({done}/{total})[/dim]  {msg}"
                    )
                spider = Spider(
                    api,
                    max_requests=max_requests,
                    delay=delay,
                    sample_chars=sample_chars,
                    progress_cb=cb_console,
                )
                result = spider.run()

        # Tag the report with the device identity for context.
        try:
            dev = api.get_device_info() or {}
        except Exception:
            dev = {}
        result["device"] = {
            "host": api.base_url,
            "model": dev.get("ModelName"),
            "serial": dev.get("SerialNumber"),
            "software": dev.get("SoftwareVer"),
            "hardware": dev.get("HardwareVer"),
            "boot": dev.get("BootVer"),
            "firmware_date": dev.get("VerDate"),
        }
        result["comparison"] = (
            compare_discovery_reports(result, previous_report)
            if previous_report is not None
            else None
        )

        # Samples may contain serials and authenticated response data.
        payload = (json.dumps(result, indent=2, default=str) + "\n").encode("utf-8")
        try:
            _write_private_bytes(Path(output), payload)
        except FileExistsError:
            message = f"refusing to overwrite existing file: {output}"
            if state.json:
                _emit_json({"ok": False, "error": message})
            else:
                console.print(f"[red]Discovery failed:[/red] {message}")
            raise typer.Exit(code=1)
        except OSError as exc:
            if state.json:
                _emit_json({"ok": False, "error": str(exc)})
            else:
                console.print(f"[red]Discovery failed:[/red] {exc}")
            raise typer.Exit(code=1)

        if state.json:
            _emit_json({
                "output": output,
                "stats": result["stats"],
                "comparison": result["comparison"],
            })
            return

        s = result["stats"]
        console.print(f"[green]Wrote[/green] [bold]{output}[/bold]")
        table = Table(title="Discovery summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("HTTP requests", str(s["requests_made"]))
        table.add_row("HTTP errors", str(s["errors"]))
        table.add_row("Assets crawled", str(s["asset_count"]))
        table.add_row("Endpoints found", str(s["endpoint_count"]))
        table.add_row("Endpoints fetched", str(s["endpoint_fetched"]))
        table.add_row("With usable data", str(s["endpoints_with_data"]))
        for k, v in s["by_type"].items():
            table.add_row(f"  type={k}", str(v))
        for k, v in s["by_shape"].items():
            table.add_row(f"  shape={k}", str(v))
        for k, v in s["skipped"].items():
            table.add_row(f"  skipped: {k}", str(v))
        console.print(table)
        if result["comparison"] is not None:
            c = result["comparison"]["summary"]
            console.print(
                "[cyan]Comparison:[/cyan] "
                f"+{c['added']} added, -{c['removed']} removed, "
                f"~{c['changed']} changed"
            )
        console.print(
            "[dim]Tip: send the JSON file back so we can map new commands "
            "to the discovered endpoints.[/dim]"
        )
    finally:
        api.close()


def run_cli() -> None:
    """Console entry point with stable handling for operational API errors."""
    try:
        app()
    except H388XError as exc:
        if state.json:
            _emit_json({"ok": False, "error": {"type": exc.code, "message": str(exc)}})
        else:
            console.print(f"[red]{exc.code}:[/red] {exc}")
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    run_cli()
