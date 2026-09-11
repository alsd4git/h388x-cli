from pathlib import Path
from textwrap import dedent, indent


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement.rstrip() + "\n\n" + text[j:]


def method(source: str) -> str:
    return indent(dedent(source).strip() + "\n", "    ")


api_path = Path("h388x_cli/api.py")
api = api_path.read_text(encoding="utf-8")

api = api.replace(
    "import requests\n",
    "import requests\nfrom pydantic import ValidationError\n\n"
    "from .validation import (\n"
    "    DhcpReservationSpec,\n"
    "    IpFilterSpec,\n"
    "    PortForwardSpec,\n"
    "    UrlFilterSpec,\n"
    "    validation_error_message,\n"
    ")\n",
    1,
)

api = replace_between(
    api,
    "    def add_port_forwarding_rule(\n",
    "    def del_port_forwarding_rule(",
    method(
        '''
        def add_port_forwarding_rule(
            self,
            description: str,
            protocol: str,
            external_port: int,
            internal_client: str,
            internal_port: Optional[int] = None,
            external_port_end: Optional[int] = None,
            remote_host: str = "0.0.0.0",
            remote_host_end: str = "0.0.0.0",
            enable: bool = True,
        ) -> Tuple[bool, str]:
            """Create a new port-forwarding rule after local validation."""
            ext_end = external_port_end if external_port_end is not None else external_port
            int_port = internal_port if internal_port is not None else external_port
            try:
                spec = PortForwardSpec(
                    description=description,
                    protocol=protocol,
                    external_port=external_port,
                    external_port_end=ext_end,
                    internal_client=internal_client,
                    internal_port=int_port,
                    remote_host=remote_host,
                    remote_host_end=remote_host_end,
                )
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"

            fields = self._prefixed(self._PFWD_PREFIX, {
                "_OBJ_InstID": "-1",
                "Enable": "1" if enable else "0",
                "Description": spec.description,
                "Protocol": spec.protocol,
                "ExternalPort": str(spec.external_port),
                "ExternalPortEndRange": str(spec.external_port_end),
                "InternalClient": spec.internal_client,
                "InternalPort": str(spec.internal_port),
                "RemoteHost": spec.remote_host,
                "RemoteHostEndRange": spec.remote_host_end,
            })
            return self._post_action(
                self.PORT_FORWARDING_VIEW_URL,
                self.PORT_FORWARDING_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)

api = replace_between(
    api,
    "    def edit_port_forwarding_rule(\n",
    "    # --- DHCPv4 static reservations write actions ---",
    method(
        '''
        def edit_port_forwarding_rule(
            self,
            inst_id: str,
            *,
            description: Optional[str] = None,
            protocol: Optional[str] = None,
            external_port: Optional[int] = None,
            internal_client: Optional[str] = None,
            internal_port: Optional[int] = None,
            external_port_end: Optional[int] = None,
            remote_host: Optional[str] = None,
            remote_host_end: Optional[str] = None,
            enable: Optional[bool] = None,
        ) -> Tuple[bool, str]:
            """Edit a port-forwarding rule after validating the final payload."""
            current = next(
                (r for r in self.get_port_forwarding_rules()
                 if r.get("_OBJ_InstID") == inst_id),
                None,
            )
            if current is None:
                return False, f"rule {inst_id!r} not found"

            def pick(new: object, key: str) -> str:
                return str(new) if new is not None else current.get(key, "")

            try:
                spec = PortForwardSpec(
                    description=pick(description, "Description"),
                    protocol=pick(protocol, "Protocol"),
                    external_port=pick(external_port, "ExternalPort"),
                    external_port_end=pick(external_port_end, "ExternalPortEndRange"),
                    internal_client=pick(internal_client, "InternalClient"),
                    internal_port=pick(internal_port, "InternalPort"),
                    remote_host=pick(remote_host, "RemoteHost"),
                    remote_host_end=pick(remote_host_end, "RemoteHostEndRange"),
                )
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"

            enable_val = current.get("Enable", "1") if enable is None else ("1" if enable else "0")
            fields = self._prefixed(self._PFWD_PREFIX, {
                "_OBJ_InstID": inst_id,
                "Enable": enable_val,
                "Description": spec.description,
                "Protocol": spec.protocol,
                "ExternalPort": str(spec.external_port),
                "ExternalPortEndRange": str(spec.external_port_end),
                "InternalClient": spec.internal_client,
                "InternalPort": str(spec.internal_port),
                "RemoteHost": spec.remote_host,
                "RemoteHostEndRange": spec.remote_host_end,
            })
            return self._post_action(
                self.PORT_FORWARDING_VIEW_URL,
                self.PORT_FORWARDING_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)

api = replace_between(
    api,
    "    def add_dhcp_reservation(\n",
    "    def del_dhcp_reservation(",
    method(
        '''
        def add_dhcp_reservation(
            self, mac: str, ip_address: str, name: str
        ) -> Tuple[bool, str]:
            """Create a static DHCPv4 reservation after local validation."""
            try:
                spec = DhcpReservationSpec(mac=mac, ip_address=ip_address, name=name)
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"
            fields = self._prefixed(self._DHCP_BIND_PREFIX, {
                "_OBJ_InstID": "-1",
                "Name": spec.name,
                "IPAddr": spec.ip_address,
                "MACAddr": spec.mac,
            })
            return self._post_action(
                self.DHCP_VIEW_URL,
                self.DHCP_BINDINGS_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)

api = replace_between(
    api,
    "    def edit_dhcp_reservation(\n",
    "    # ------------------------------------------------------------------- DNS",
    method(
        '''
        def edit_dhcp_reservation(
            self,
            inst_id: str,
            *,
            name: Optional[str] = None,
            ip_address: Optional[str] = None,
            mac: Optional[str] = None,
        ) -> Tuple[bool, str]:
            """Edit a DHCPv4 reservation after validating its final payload."""
            current = next(
                (r for r in self.get_dhcp_bindings()
                 if r.get("_OBJ_InstID") == inst_id),
                None,
            )
            if current is None:
                return False, f"binding {inst_id!r} not found"

            def pick(new: object, key: str) -> str:
                return str(new) if new is not None else current.get(key, "")

            try:
                spec = DhcpReservationSpec(
                    name=pick(name, "Name"),
                    ip_address=pick(ip_address, "IPAddr"),
                    mac=pick(mac, "MACAddr"),
                )
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"
            fields = self._prefixed(self._DHCP_BIND_PREFIX, {
                "_OBJ_InstID": inst_id,
                "Name": spec.name,
                "IPAddr": spec.ip_address,
                "MACAddr": spec.mac,
            })
            return self._post_action(
                self.DHCP_VIEW_URL,
                self.DHCP_BINDINGS_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)

api = replace_between(
    api,
    "    def add_url_filter_rule(",
    "    def del_url_filter_rule(",
    method(
        '''
        def add_url_filter_rule(self, name: str, url: str) -> Tuple[bool, str]:
            """Create a URL-filter rule after observed WebUI validation."""
            try:
                spec = UrlFilterSpec(name=name, url=url)
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"
            fields = self._prefixed(self._FWURL_PREFIX, {
                "_OBJ_InstID": "-1",
                "Name": spec.name,
                "Url": spec.url,
            })
            return self._post_action(
                self.FILTER_CRITERIA_VIEW_URL,
                self.FW_URLFILTER_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)

api = replace_between(
    api,
    "    def add_ip_filter_rule(\n",
    "    def del_ip_filter_rule(",
    method(
        '''
        def add_ip_filter_rule(
            self,
            name: str,
            protocol: str,
            *,
            target: str = "allow",
            filter_index: int = 1,
            enable: bool = True,
            ip_version: str = "4",
            source_ip: str = "",
            source_mask: str = "",
            dest_ip: str = "",
            dest_mask: str = "",
            min_src_port: str = "",
            max_src_port: str = "",
            min_dst_port: str = "",
            max_dst_port: str = "",
            in_iface: str = "",
            out_iface: str = "",
            dscp: str = "",
        ) -> Tuple[bool, str]:
            """Create an IP-filter rule after known WebUI validation."""
            try:
                spec = IpFilterSpec(
                    name=name,
                    protocol=protocol,
                    target=target,
                    filter_index=filter_index,
                    ip_version=ip_version,
                    source_ip=source_ip,
                    dest_ip=dest_ip,
                    min_src_port=min_src_port,
                    max_src_port=max_src_port,
                    min_dst_port=min_dst_port,
                    max_dst_port=max_dst_port,
                    dscp=dscp,
                )
            except ValidationError as exc:
                return False, f"validation error: {validation_error_message(exc)}"

            proto_num = self._IP_PROTO_MAP.get(spec.protocol, spec.protocol)
            target_num = "1" if spec.target == "allow" else "0"
            fields = self._prefixed(self._FWIP_PREFIX, {
                "_OBJ_InstID": "-1",
                "Enable": "1" if enable else "0",
                "Name": spec.name,
                "FilterTarget": target_num,
                "FilterIndex": str(spec.filter_index),
                "IPVersion": spec.ip_version,
                "SourceIP": spec.source_ip,
                "SourceIPMask": source_mask,
                "DestIP": spec.dest_ip,
                "DestIPMask": dest_mask,
                "S_Protocol": proto_num,
                "Protocol": proto_num,
                "MinSrcPort": spec.min_src_port,
                "MaxSrcPort": spec.max_src_port,
                "MinDstPort": spec.min_dst_port,
                "MaxDstPort": spec.max_dst_port,
                "INCViewName": in_iface,
                "OUTCViewName": out_iface,
                "DSCP": spec.dscp,
            })
            return self._post_action(
                self.FILTER_CRITERIA_VIEW_URL,
                self.FW_IPFILTER_URL,
                action="Apply",
                fields=fields,
            )
        '''
    ),
)
api_path.write_text(api, encoding="utf-8")


cli_path = Path("h388x_cli/cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = cli.replace(
    "from .devices import (\n",
    "from .devices import (\n    apply_import_plan as _apply_import_plan,\n",
    1,
)

import_block = dedent(
    '''
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
    '''
).strip()
cli = replace_between(
    cli,
    '@devices_app.command("import")\n',
    '@devices_app.command("set")',
    import_block,
)

edit_start = "        for kind, r, new in actions:\n"
edit_end = "    finally:\n        api.close()"
edit_loop = dedent(
    '''
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
    '''
).rstrip()
cli = replace_between(cli, edit_start, edit_end, edit_loop)
cli_path.write_text(cli, encoding="utf-8")
