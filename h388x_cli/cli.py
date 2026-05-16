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
    Client,
    DeviceInfo,
    Dmz,
    DSLStats,
    FirewallDos,
    FirewallLevel,
    PortForwardingRule,
    UrlFilterGlobal,
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

def _ip_opt() -> str:
    return typer.Option(os.getenv("H388X_IP", "192.168.1.1"), help="Modem IP address")


def _user_opt() -> str:
    return typer.Option(os.getenv("H388X_USER", "admin"), help="Admin username")


def _pwd_opt() -> Optional[str]:
    return typer.Option(None, help="Admin password (or set H388X_PASSWORD)")


def get_api(ip: str, user: str, password: Optional[str]) -> ZTEH388XAPI:
    password = password or os.getenv("H388X_PASSWORD", "")
    if not password:
        console.print(
            "[red]Error: Password is required. "
            "Set H388X_PASSWORD in .env or use --password.[/red]"
        )
        raise typer.Exit(code=1)

    api = ZTEH388XAPI(ip=ip, username=user, password=password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    watch: Optional[float] = typer.Option(
        None,
        "--watch",
        "-w",
        help="Refresh stats every N seconds (Ctrl+C to stop).",
    ),
):
    """Display DSL line statistics (optionally live with --watch)."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
):
    """Display device information (model, firmware, serial)."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all WAN connections (default: only Connected ones).",
    ),
):
    """Show WAN connections (public IP, gateway, DNS, uptime)."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    leases: bool = typer.Option(
        False,
        "--leases",
        "-L",
        help="Show full DHCP lease table instead of currently-connected devices.",
    ),
):
    """List currently connected devices (LAN + Wi-Fi), or DHCP leases."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
):
    """Show Wi-Fi radios (2.4/5 GHz) and configured SSIDs (main + guest)."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
):
    """Show firewall summary: level, anti-DoS, URL filter, DMZ."""
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    all_: bool = typer.Option(
        False,
        "--all",
        "-a",
        help="Show all rules (default: only Enabled ones).",
    ),
):
    """List configured port-forwarding rules (NAT)."""
    api = get_api(ip, user, password)
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


# --------------------------------------------------------------------- reboot

@app.command()
def reboot(
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Reboot the modem."""
    if not yes and not typer.confirm("Are you sure you want to reboot the modem?"):
        raise typer.Abort()
    api = get_api(ip, user, password)
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
    ip: str = _ip_opt(),
    user: str = _user_opt(),
    password: Optional[str] = _pwd_opt(),
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
    api = get_api(ip, user, password)

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
