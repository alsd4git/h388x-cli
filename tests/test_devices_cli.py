import json

from typer.testing import CliRunner

from h388x_cli import cli


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
    monkeypatch.setattr(cli, "get_api", lambda *_args, **_kwargs: api)
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


def test_devices_import_json_partial_write_failure_is_not_success(monkeypatch, tmp_path):
    api = _FakeApi([(True, "ok"), (False, "rejected")])
    monkeypatch.setattr(cli, "get_api", lambda *_args, **_kwargs: api)
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
    monkeypatch.setattr(cli, "get_api", lambda *_args, **_kwargs: api)
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
