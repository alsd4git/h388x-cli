"""Typer sub-application for MAC-keyed device naming workflows."""

from __future__ import annotations

import json
from typing import List, Optional

import typer
from rich.table import Table
from rich.text import Text

from .cli_runtime import (
    _emit_json,
    _host_opt,
    _insecure_opt,
    _pwd_opt,
    _user_opt,
    console,
    get_api,
    state,
)
from .devices import (
    apply_import_plan as _apply_import_plan,
    merge_devices as _merge_devices,
    norm_mac as _norm_mac,
    plan_import as _plan_import,
    reservations_export as _reservations_export,
)
from .models import Client, DhcpBinding

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
        clients = [Client.model_validate(r) for r in api.get_lan_clients()] + [
            Client.model_validate(r) for r in api.get_wifi_clients()
        ]
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
            _emit_json(
                {
                    "ok": apply_ok,
                    "dry_run": dry_run,
                    "summary": summary,
                    "plan": plan,
                }
            )
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
                console.print(
                    "[red]Preflight failed; no modem changes were attempted.[/red]"
                )
            raise typer.Exit(code=1)
    finally:
        api.close()


@devices_app.command("set")
def devices_set(
    mac: str = typer.Argument(..., help="Client MAC address."),
    name: str = typer.Argument(..., help="Friendly name to assign."),
    ip_address: Optional[str] = typer.Option(
        None,
        "--ip",
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
            (
                b
                for b in (
                    DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()
                )
                if _norm_mac(b.mac) == key
            ),
            None,
        )

        if existing is not None:
            ok, body = api.edit_dhcp_reservation(
                existing.id,
                name=name,
                ip_address=ip_address,
            )
            action = "updated"
            target_ip = ip_address or existing.ip_address
        else:
            target_ip = ip_address
            if not target_ip:
                # Discover the device's current IP from connected clients.
                clients = [Client.model_validate(r) for r in api.get_lan_clients()] + [
                    Client.model_validate(r) for r in api.get_wifi_clients()
                ]
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
                mac=mac,
                ip_address=target_ip,
                name=name,
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
            _emit_json(
                {
                    "ok": True,
                    "action": action,
                    "mac": mac,
                    "ip": target_ip,
                    "name": name,
                }
            )
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
        False,
        "-y",
        "--yes",
        help="Skip the confirmation prompt.",
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
            (
                b
                for b in (
                    DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()
                )
                if _norm_mac(b.mac) == key
            ),
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
        clients = [Client.model_validate(r) for r in api.get_lan_clients()] + [
            Client.model_validate(r) for r in api.get_wifi_clients()
        ]
        bindings = [DhcpBinding.model_validate(r) for r in api.get_dhcp_bindings()]
        rows = sorted(
            _merge_devices(clients, bindings), key=lambda r: r.get("ipv4") or ""
        )

        console.print(
            "[bold]Interactive device naming[/bold] (route A: DHCP reservations)"
        )
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
        for kind, r, new in actions:
            label = (new if new is not None else r["name"]) or "-"
            table.add_row(kind, label, r["ipv4"] or "-", r["mac"] or "-")
        console.print()
        console.print(table)
        if not typer.confirm("Apply these changes?"):
            console.print("[yellow]Aborted.[/yellow]")
            return

        applied = 0
        for index, (kind, r, new) in enumerate(actions):
            if kind == "edit":
                ok, body = api.edit_dhcp_reservation(r["reservation_id"], name=new)
            elif kind == "add":
                ok, body = api.add_dhcp_reservation(
                    mac=r["mac"],
                    ip_address=r["ipv4"],
                    name=new,
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
