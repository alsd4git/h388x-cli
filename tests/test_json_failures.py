import json
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from h388x_cli import cli, cli_runtime


runner = CliRunner()


def test_missing_password_is_json_without_contacting_modem(monkeypatch):
    monkeypatch.delenv("H388X_PASSWORD", raising=False)
    constructor = MagicMock(side_effect=AssertionError("must not contact modem"))
    monkeypatch.setattr(cli_runtime, "ZTEH388XAPI", constructor)

    result = runner.invoke(cli.app, ["--json", "info"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["type"] == "authentication_error"
    constructor.assert_not_called()


def test_failed_login_is_json_and_closes_session(monkeypatch):
    api = MagicMock()
    api.has_cached_session = False
    api.login.return_value = False
    monkeypatch.setenv("H388X_PASSWORD", "private-password")
    monkeypatch.setattr(cli_runtime, "ZTEH388XAPI", lambda **kwargs: api)

    result = runner.invoke(cli.app, ["--json", "info"])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["type"] == "authentication_error"
    assert "private-password" not in result.stdout
    api.session.close.assert_called_once()
    api.get_device_info.assert_not_called()


@pytest.mark.parametrize(
    "args", [["info"], ["stats"], ["stats", "--watch", "1"], ["wan"], ["wifi"]]
)
def test_unexpected_empty_response_is_json_and_closes_api(monkeypatch, args):
    api = MagicMock()
    api.get_device_info.return_value = {}
    api.get_dsl_stats.return_value = {}
    api.get_wan_connections.return_value = []
    api.get_wifi_radios.return_value = []
    api.get_wifi_aps.return_value = []
    monkeypatch.setattr(cli, "get_api", lambda *args, **kwargs: api)

    result = runner.invoke(cli.app, ["--json", *args])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["type"] == "empty_response"
    api.close.assert_called_once()


@pytest.mark.parametrize("args", [["dns-set"], ["port-forward-edit", "1"]])
def test_missing_write_inputs_are_json_without_contacting_modem(monkeypatch, args):
    get_api = MagicMock(side_effect=AssertionError("must not contact modem"))
    monkeypatch.setattr(cli, "get_api", get_api)

    result = runner.invoke(cli.app, ["--json", *args])

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"]["type"] == "validation_error"
    get_api.assert_not_called()
