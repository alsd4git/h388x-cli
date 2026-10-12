import json

from typer.testing import CliRunner

from h388x_cli import cli, cli_devices
from h388x_cli.errors import TransportError


runner = CliRunner()


class _FakeApi:
    def __init__(self, outcomes=None):
        self.outcomes = iter(outcomes or [])
        self.calls = []
        self.closed = False

    def get_dhcp_bindings(self):
        return []

    def add_dhcp_reservation(self, *, mac, ip_address, name):
        self.calls.append((mac, ip_address, name))
        return next(self.outcomes, (True, "ok"))

    def edit_dhcp_reservation(self, *_args, **_kwargs):
        raise AssertionError("unexpected edit")

    def close(self):
        self.closed = True


def _write_import(tmp_path, entries):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_devices_import_json_preflight_failure_does_not_write(monkeypatch, tmp_path):
    api = _FakeApi()
    monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)
    path = _write_import(
        tmp_path,
        [
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "Good"},
            {"mac": "bad", "ip": "192.168.1.51", "name": "Bad"},
        ],
    )

    result = runner.invoke(cli.app, ["--json", "devices", "import", str(path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["summary"]["preflight_errors"] == 1
    assert api.calls == []
    assert api.closed is True


def test_devices_import_json_partial_write_failure_is_not_success(
    monkeypatch, tmp_path
):
    api = _FakeApi([(True, "ok"), (False, "rejected")])
    monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)
    path = _write_import(
        tmp_path,
        [
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "One"},
            {"mac": "aa:bb:cc:00:11:23", "ip": "192.168.1.51", "name": "Two"},
            {"mac": "aa:bb:cc:00:11:24", "ip": "192.168.1.52", "name": "Three"},
        ],
    )

    result = runner.invoke(cli.app, ["--json", "devices", "import", str(path)])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["summary"]["applied"] == 1
    assert payload["summary"]["failed"] == 1
    assert payload["summary"]["skipped"] == 1
    assert payload["summary"]["partial"] is True
    assert len(api.calls) == 2
    assert payload["plan"][2]["skipped"] == "previous write failed"
    assert api.closed is True


def test_devices_import_dry_run_with_valid_plan_is_success(monkeypatch, tmp_path):
    api = _FakeApi()
    monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)
    path = _write_import(
        tmp_path,
        [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "Laptop"}],
    )

    result = runner.invoke(
        cli.app, ["--json", "devices", "import", str(path), "--dry-run"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert api.calls == []


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

    result = runner.invoke(cli.app, ["devices", "edit"], input="New name\nn\n")

    assert result.exit_code == 0, result.stdout
    assert "Pending changes" in result.stdout
    assert "Apply these changes?" in result.stdout
    assert "Aborted." in result.stdout
    assert api.calls == []
    assert api.closed is True


class _PartialReadFailureApi(_FakeApi):
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
    assert payload["plan"][1]["error"] == "Modem rejected the operation."
    assert payload["plan"][2]["skipped"] == "previous write failed"
    assert len(api.calls) == 2
    assert api.closed is True
