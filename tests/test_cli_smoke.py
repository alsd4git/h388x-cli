"""Smoke tests for the Typer CLI wiring (no network).

These complement ``test_api_flow.py`` (which mocks HTTP at the API layer)
by exercising the *CLI* layer instead:

- every registered command and sub-command must render ``--help`` cleanly
  (catches option/typing wiring errors across the whole surface);
- a few representative commands must produce well-formed ``--json`` output
  when the API is stubbed, so command → API → JSON plumbing is covered.

The API is replaced by a fake via ``h388x_cli.cli.get_api`` so nothing
touches a real modem.
"""

import json
import os
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from h388x_cli import cli
from h388x_cli.cli import app


runner = CliRunner()


def _all_command_paths():
    """Yield the argv prefix for every command and sub-command."""
    for c in app.registered_commands:
        yield [c.name or c.callback.__name__]
    for group in app.registered_groups:
        gname = group.name
        for c in group.typer_instance.registered_commands:
            yield [gname, c.name or c.callback.__name__]


COMMAND_PATHS = list(_all_command_paths())


@pytest.mark.parametrize("path", COMMAND_PATHS, ids=lambda p: " ".join(p))
def test_command_help_renders(path):
    """Every command exposes a working ``--help`` (exit 0, non-empty)."""
    result = runner.invoke(app, [*path, "--help"])
    assert result.exit_code == 0, result.stdout
    assert "Usage:" in result.stdout


def test_root_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "info" in result.stdout
    assert "ping" in result.stdout


@pytest.fixture
def fake_api(monkeypatch):
    """Patch ``get_api`` to hand every command the same MagicMock.

    Tests configure the return values of the specific method a command
    calls; ``close()`` is a no-op mock so the ``finally`` blocks are happy.
    """
    api = MagicMock()
    monkeypatch.setattr(cli, "get_api", lambda *a, **k: api)
    return api


def test_info_json(fake_api):
    fake_api.get_device_info.return_value = {
        "ModelName": "H388X",
        "SerialNumber": "SN123",
        "SoftwareVer": "1.4.4",
    }
    result = runner.invoke(app, ["--json", "info"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["model"] == "H388X"
    assert payload["serial_number"] == "SN123"
    fake_api.close.assert_called_once()


def test_capabilities_json_is_versioned_and_redacts_serial(fake_api, tmp_path):
    fake_api.base_url = "http://modem.test"
    fake_api.get_device_info.return_value = {
        "ModelName": "H388X",
        "SerialNumber": "SECRET-SERIAL",
        "SoftwareVer": "AGZHM_1.4.4",
    }
    report = tmp_path / "endpoints.json"
    report.write_text(
        json.dumps(
            {
                "device": {"serial": "SECRET-SERIAL"},
                "stats": {"endpoint_count": 1, "endpoints_with_data": 1},
                "endpoints": [
                    {
                        "type": "menuData",
                        "tag": "devmgr_statusmgr_lua.lua",
                        "extras": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--json", "capabilities", "--report", str(report)])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "2"
    assert payload["device"]["software"] == "AGZHM_1.4.4"
    assert payload["discovery"]["stats"]["endpoint_count"] == 1
    assert "SECRET-SERIAL" not in result.stdout
    info = next(item for item in payload["capabilities"] if item["id"] == "device.info")
    assert info["detected"] is True
    fake_api.close.assert_called_once()


def test_ping_json(fake_api):
    fake_api.ping.return_value = (True, "4 packets transmitted, 4 received")
    result = runner.invoke(app, ["--json", "ping", "1.1.1.1"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload == {
        "ok": True,
        "host": "1.1.1.1",
        "result": "4 packets transmitted, 4 received",
    }
    fake_api.ping.assert_called_once_with("1.1.1.1")


def test_ping_json_failure_exits_nonzero(fake_api):
    fake_api.ping.return_value = (False, "could not start diagnostic")
    result = runner.invoke(app, ["--json", "ping", "1.1.1.1"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False


def test_traceroute_json_passes_options(fake_api):
    fake_api.traceroute.return_value = (True, "traceroute to 1.1.1.1")
    result = runner.invoke(
        app, ["--json", "traceroute", "1.1.1.1", "-m", "5", "--protocol", "ICMP"]
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    fake_api.traceroute.assert_called_once_with(
        "1.1.1.1", max_hops=5, timeout_ms=5000, protocol="ICMP"
    )


def test_config_backup_writes_private_new_file(fake_api, tmp_path):
    output = tmp_path / "config.bin"
    fake_api.download_config_backup.return_value = (True, b"modem-config")

    result = runner.invoke(app, ["config", "backup", str(output)])

    assert result.exit_code == 0, result.stdout
    assert output.read_bytes() == b"modem-config"
    assert os.stat(output).st_mode & 0o777 == 0o600
    fake_api.close.assert_called_once()


def test_config_backup_refuses_to_overwrite_existing_file(fake_api, tmp_path):
    output = tmp_path / "config.bin"
    output.write_bytes(b"keep me")
    fake_api.download_config_backup.return_value = (True, b"new-config")

    result = runner.invoke(app, ["--json", "config", "backup", str(output)])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["ok"] is False
    assert output.read_bytes() == b"keep me"


def test_dhcp_reserve_add_json_matches_normalized_mac_readback(fake_api):
    fake_api.add_dhcp_reservation.return_value = (
        True,
        "<IF_ERRORSTR>SUCC</IF_ERRORSTR>",
    )
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
