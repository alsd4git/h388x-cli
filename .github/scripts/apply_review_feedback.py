from pathlib import Path


def replace_once(path_str: str, old: str, new: str) -> None:
    path = Path(path_str)
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"expected exactly one match in {path_str}, found {text.count(old)}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# P1: restore the pending-change review and explicit confirmation before any
# interactive devices edit mutation is sent to the modem.
replace_once(
    "h388x_cli/cli_devices.py",
    '''        table = Table(title="Pending changes")
        table.add_column("Action")
        table.add_column("Name", style="cyan")
        table.add_column("IP", style="green")
        table.add_column("MAC")
        applied = 0
''',
    '''        table = Table(title="Pending changes")
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
''',
)

# P2: the write validator accepts/canonicalizes common MAC spellings, so the
# post-write readback must use the same normalization instead of lower() only.
replace_once(
    "h388x_cli/cli.py",
    '''            if (r.get("MACAddr") or "").lower() == mac.lower()
''',
    '''            if _norm_mac(r.get("MACAddr")) == _norm_mac(mac)
''',
)

# P2: endpoint extras extracted from existing URLs are query data, not already
# canonical strings. Decode them first so Endpoint.url() does not double-encode
# percent escapes such as %20 -> %2520.
replace_once(
    "h388x_cli/discovery.py",
    '''from urllib.parse import quote, urlencode, urljoin, urlsplit
''',
    '''from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit
''',
)
replace_once(
    "h388x_cli/discovery.py",
    '''            for chunk in extra_str.split("&"):
                if "=" in chunk:
                    k, _, v = chunk.partition("=")
                    if k:
                        extras[k] = v
''',
    '''            for k, v in parse_qsl(extra_str.lstrip("&"), keep_blank_values=True):
                if k:
                    extras[k] = v
''',
)

# Focused regression test: declining the final interactive confirmation must
# perform zero writes, while still showing the queued changes for review.
path = Path("tests/test_devices_cli.py")
text = path.read_text(encoding="utf-8")
addition = '''

class _FakeEditApi(_FakeApi):
    def get_lan_clients(self):
        return []

    def get_wifi_clients(self):
        return []

    def get_dhcp_bindings(self):
        return [
            {
                "_OBJ_InstID": "DEV.V4DP.Sr.Pl1.Bd1",
                "Name": "Old name",
                "IPAddr": "192.168.1.50",
                "MACAddr": "aa:bb:cc:dd:ee:ff",
            }
        ]

    def edit_dhcp_reservation(self, reservation_id, *, name):
        self.calls.append(("edit", reservation_id, name))
        return True, "ok"


def test_devices_edit_shows_pending_changes_and_can_abort_before_write(monkeypatch):
    api = _FakeEditApi()
    monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)

    result = runner.invoke(cli.app, ["devices", "edit"], input="New name\\nn\\n")

    assert result.exit_code == 0, result.stdout
    assert "Pending changes" in result.stdout
    assert "Apply these changes?" in result.stdout
    assert "Aborted." in result.stdout
    assert api.calls == []
    assert api.closed is True
'''
if "test_devices_edit_shows_pending_changes_and_can_abort_before_write" in text:
    raise SystemExit("devices edit regression test already exists")
path.write_text(text + addition, encoding="utf-8")

# Focused regression test: a successful add with a hyphenated input MAC must
# match the modem's colon-form readback.
path = Path("tests/test_cli_smoke.py")
text = path.read_text(encoding="utf-8")
addition = '''


def test_dhcp_reserve_add_json_matches_normalized_mac_readback(fake_api):
    fake_api.add_dhcp_reservation.return_value = (True, "<IF_ERRORSTR>SUCC</IF_ERRORSTR>")
    fake_api.get_dhcp_bindings.return_value = [
        {
            "_OBJ_InstID": "DEV.V4DP.Sr.Pl1.Bd1",
            "Name": "Printer",
            "IPAddr": "192.168.1.60",
            "MACAddr": "aa:bb:cc:dd:ee:ff",
        }
    ]

    result = runner.invoke(
        app,
        [
            "--json",
            "dhcp-reserve-add",
            "AA-BB-CC-DD-EE-FF",
            "192.168.1.60",
            "Printer",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert len(payload["added"]) == 1
    assert payload["added"][0]["mac"] == "aa:bb:cc:dd:ee:ff"
'''
if "test_dhcp_reserve_add_json_matches_normalized_mac_readback" in text:
    raise SystemExit("DHCP readback regression test already exists")
path.write_text(text + addition, encoding="utf-8")

# Focused regression test: parsing + canonical URL serialization should be a
# stable decode/re-encode cycle, not a second percent-encoding pass.
path = Path("tests/test_discovery.py")
text = path.read_text(encoding="utf-8")
addition = '''


def test_discovered_query_values_decode_before_canonical_reencoding():
    found = Spider._extract_endpoints(
        '"/?_type=menuData&_tag=example.lua&name=a%20b&token=x%2By"'
    )

    assert found == [
        ("menuData", "example.lua", {"name": "a b", "token": "x+y"})
    ]
    tp, tag, extras = found[0]
    assert Endpoint(type=tp, tag=tag, extras=extras).url() == (
        "/?_type=menuData&_tag=example.lua&name=a%20b&token=x%2By"
    )
'''
if "test_discovered_query_values_decode_before_canonical_reencoding" in text:
    raise SystemExit("query decoding regression test already exists")
path.write_text(text + addition, encoding="utf-8")
