import json
import os
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from h388x_cli import cli, cli_devices


runner = CliRunner()
DELETE_CASES = [
    (
        ["port-forward-del", "1"],
        "get_port_forwarding_rules",
        "del_port_forwarding_rule",
        "DEV.NAT.PtMapping1",
    ),
    (
        ["dhcp-reserve-del", "1"],
        "get_dhcp_bindings",
        "del_dhcp_reservation",
        "DEV.V4DP.Sr.Pl1.Bd1",
    ),
    (
        ["firewall-urlfilter-del", "1"],
        "get_firewall_urlfilter",
        "del_url_filter_rule",
        "DEV.FW.CHAIN1.URLF1",
    ),
    (
        ["firewall-ipfilter-del", "1"],
        "get_firewall_ipfilter",
        "del_ip_filter_rule",
        "DEV.FW.CHAIN1.IPF1",
    ),
    (
        ["devices", "clear", "02:00:00:00:00:01"],
        "get_dhcp_bindings",
        "del_dhcp_reservation",
        "DEV.V4DP.Sr.Pl1.Bd1",
    ),
]


@pytest.mark.parametrize("args", [case[0] for case in DELETE_CASES] + [["reboot"]])
def test_destructive_json_requires_yes_before_contacting_modem(monkeypatch, args):
    get_api = MagicMock(side_effect=AssertionError("must not contact modem"))
    monkeypatch.setattr(cli, "get_api", get_api)
    monkeypatch.setattr(cli_devices, "get_api", get_api)

    result = runner.invoke(cli.app, ["--json", *args])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["type"] == "confirmation_required"
    get_api.assert_not_called()


@pytest.mark.parametrize("args,read,write,identifier", DELETE_CASES)
def test_confirmed_json_deletion_redacts_modem_error(
    monkeypatch, args, read, write, identifier
):
    api = MagicMock()
    row = {"_OBJ_InstID": identifier, "MACAddr": "02:00:00:00:00:01"}
    getattr(api, read).return_value = (
        {"rules": [row]} if read == "get_firewall_ipfilter" else [row]
    )
    getattr(api, write).return_value = (
        False,
        "<root><IF_ERRORID>-1452</IF_ERRORID><sess_token>secret-token</sess_token><Password>secret-password</Password></root>",
    )
    monkeypatch.setattr(cli, "get_api", lambda *args, **kwargs: api)
    monkeypatch.setattr(cli_devices, "get_api", lambda *args, **kwargs: api)

    result = runner.invoke(cli.app, ["--json", *args, "--yes"])

    assert result.exit_code == 1, result.stdout
    assert "secret-token" not in result.stdout
    assert "secret-password" not in result.stdout
    assert "-1452" in json.loads(result.stdout)["error"]
    getattr(api, write).assert_called_once_with(identifier)


def test_devices_export_creates_private_file_and_preserves_existing_file(
    monkeypatch, tmp_path
):
    api = MagicMock()
    api.get_dhcp_bindings.return_value = []
    monkeypatch.setattr(cli_devices, "get_api", lambda *args, **kwargs: api)
    path = tmp_path / "reservations.json"

    first = runner.invoke(cli.app, ["--json", "devices", "export", str(path)])
    assert first.exit_code == 0
    assert json.loads(first.stdout)["ok"] is True
    assert json.loads(path.read_text()) == []
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    path.write_text("keep this file")

    second = runner.invoke(cli.app, ["--json", "devices", "export", str(path)])
    assert second.exit_code == 1
    assert json.loads(second.stdout)["ok"] is False
    assert path.read_text() == "keep this file"
