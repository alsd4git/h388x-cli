import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.table import Table

from .api import ZTEH388XAPI
from .discovery import Spider
from .models import (
    ArpEntry,
    Client,
    Ddns,
    DeviceInfo,
    Dhcp6Server,
    DhcpBinding,
    DhcpConfig,
    EthInterface,
    RouterAdvertisement,
    Dmz,
    DnsHostname,
    DnsLocal,
    DSLStats,
    FirewallDos,
    FirewallLevel,
    MacTableEntry,
    PortForwardingRule,
    UrlFilterGlobal,
    VoipLine,
    VoipSipLine,
    WanConnection,
    WifiAP,
    WifiRadio,
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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
        api.logout()


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
                    {**l.model_dump(), "phy_list": phy_by_id.get(l.id_alt or l.id)}
                    for l in lines
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

        for l in lines:
            vl_id = l.id or l.id_alt
            sip = sip_by_vl.get(vl_id) if vl_id else None
            table.add_row(
                _short_line_id(vl_id),
                (sip.phone_name if sip else None) or "-",
                (sip.auth_username if sip else None) or "[dim]not set[/dim]",
                _voip_status_style(l.is_online),
                _phy_jacks(phy_by_id.get(l.id_alt or l.id)),
            )
        console.print(table)
    finally:
        api.logout()


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
        api.logout()


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
        400, "--max-requests", help="Stop after this many HTTP requests."
    ),
    delay: float = typer.Option(
        0.15, "--delay", help="Seconds to sleep between HTTP requests."
    ),
    sample_chars: int = typer.Option(
        600,
        "--sample-chars",
        help="Per-endpoint response sample size (chars) saved in the report.",
    ),
):
    """
    Spider the modem web UI and dump every reachable
    `_type=...&_tag=...` endpoint to a JSON file.

    Read-only: only HTTP GET, mutating-looking tags are listed but not fetched.
    Useful to extend the CLI with new commands without guessing endpoints.
    """
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
            "ip": ip,
            "model": dev.get("ModelName"),
            "serial": dev.get("SerialNumber"),
            "software": dev.get("SoftwareVer"),
            "hardware": dev.get("HardwareVer"),
            "boot": dev.get("BootVer"),
            "firmware_date": dev.get("VerDate"),
        }

        # Write the file.
        with open(output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
            f.write("\n")

        if state.json:
            _emit_json({"output": output, "stats": result["stats"]})
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
        console.print(
            "[dim]Tip: send the JSON file back so we can map new commands "
            "to the discovered endpoints.[/dim]"
        )
    finally:
        api.logout()


if __name__ == "__main__":
    app()
