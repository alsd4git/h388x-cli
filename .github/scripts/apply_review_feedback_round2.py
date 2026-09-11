from pathlib import Path


def replace_once(path_str: str, old: str, new: str) -> None:
    path = Path(path_str)
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one match in {path_str}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# Reviewer P1: keep concatenated destructive/mutating endpoint names out of
# the read-only discovery queue without reintroducing generic `set*` matching
# (which would classify benign setting/settings tags as mutating).
replace_once(
    "h388x_cli/discovery.py",
    '''_MUTATING_COMPOUND_PREFIXES = (
    "restartmgr",
    "rebootmgr",
    "resetmgr",
    "upgrademgr",
    "download",
    "upload",
    "backup",
    "restore",
)''',
    '''_MUTATING_COMPOUND_PREFIXES = (
    "factoryreset",
    "factorydefault",
    "delete",
    "remove",
    "disable",
    "enable",
    "clear",
    "wipe",
    "restart",
    "reboot",
    "reset",
    "upgrade",
    "download",
    "upload",
    "backup",
    "restore",
    "import",
    "export",
    "apply",
    "submit",
    "kick",
    "block",
)''',
)

replace_once(
    "tests/test_discovery.py",
    '''    assert Spider._looks_mutating("devmgr_restartmgr_lua.lua") is True
    assert Spider._looks_mutating("firmwareUpdate.lua") is True
''',
    '''    assert Spider._looks_mutating("devmgr_restartmgr_lua.lua") is True
    assert Spider._looks_mutating("firmwareUpdate.lua") is True
    assert Spider._looks_mutating("factoryreset_lua.lua") is True
    assert Spider._looks_mutating("deleteentry_lua.lua") is True
    assert Spider._looks_mutating("disablewifi_lua.lua") is True


def test_concatenated_mutating_tags_are_recorded_but_never_queued():
    api = MagicMock()
    spider = Spider(api, delay=0)

    for tag in ("factoryreset_lua.lua", "deleteentry_lua.lua", "disablewifi_lua.lua"):
        ep = spider._record_endpoint("menuData", tag, {}, source="test")
        assert ep is not None
        assert ep.skipped_reason == "mutating-name"

    assert list(spider._endpoint_queue) == []
''',
)

# Reviewer P1: a typed operational exception raised by an individual write
# (notably edit_dhcp_reservation's preliminary read) must be folded into the
# bulk write-result contract so earlier successful changes remain visible as
# a partial application rather than escaping to the global error boundary.
replace_once(
    "h388x_cli/devices.py",
    '''from .models import Client, DhcpBinding
''',
    '''from .errors import H388XError
from .models import Client, DhcpBinding
''',
)

replace_once(
    "h388x_cli/devices.py",
    '''        if action == "add":
            ok, body = api.add_dhcp_reservation(
                mac=item["mac"], ip_address=item["ip"], name=item["name"]
            )
        else:
            ok, body = api.edit_dhcp_reservation(
                item["id"], name=item["name"], ip_address=item["ip"]
            )

        item["ok"] = bool(ok)
''',
    '''        try:
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
''',
)

replace_once(
    "tests/test_devices_cli.py",
    '''from h388x_cli import cli, cli_devices
''',
    '''from h388x_cli import cli, cli_devices
from h388x_cli.errors import TransportError
''',
)

addition = '''\n\nclass _PartialReadFailureApi(_FakeApi):
    def get_dhcp_bindings(self):
        return [
            {
                "_OBJ_InstID": "DEV.V4DP.Sr.Pl1.Bd1",
                "Name": "Old",
                "IPAddr": "192.168.1.20",
                "MACAddr": "de:ad:be:ef:00:01",
            }
        ]

    def add_dhcp_reservation(self, *, mac, ip_address, name):
        self.calls.append(("add", mac, ip_address, name))
        return True, "ok"

    def edit_dhcp_reservation(self, reservation_id, *, name, ip_address):
        self.calls.append(("edit", reservation_id, ip_address, name))
        raise TransportError("binding refresh failed")


def test_devices_import_reports_partial_state_when_write_raises_typed_error(
    monkeypatch, tmp_path
):
    api = _PartialReadFailureApi()
    monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)
    path = _write_import(
        tmp_path,
        [
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "One"},
            {"mac": "de:ad:be:ef:00:01", "ip": "192.168.1.20", "name": "Renamed"},
            {"mac": "aa:bb:cc:00:11:24", "ip": "192.168.1.52", "name": "Three"},
        ],
    )

    result = runner.invoke(cli.app, ["--json", "devices", "import", str(path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["summary"] == {
        "applied": 1,
        "failed": 1,
        "skipped": 1,
        "partial": True,
        "preflight_errors": 0,
    }
    assert payload["plan"][0]["ok"] is True
    assert payload["plan"][1]["ok"] is False
    assert "transport_error" in payload["plan"][1]["raw"]
    assert payload["plan"][2]["skipped"] == "previous write failed"
    assert len(api.calls) == 2
    assert api.closed is True
'''

path = Path("tests/test_devices_cli.py")
text = path.read_text(encoding="utf-8")
if "test_devices_import_reports_partial_state_when_write_raises_typed_error" in text:
    raise SystemExit("round2 devices CLI test already present")
path.write_text(text + addition, encoding="utf-8")
