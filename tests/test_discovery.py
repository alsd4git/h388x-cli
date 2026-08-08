import os
from unittest.mock import MagicMock

import requests
from typer.testing import CliRunner

from h388x_cli import cli
from h388x_cli.cli import app
from h388x_cli.discovery import Endpoint, Spider


def test_parent_view_arming_honors_absolute_request_budget():
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.NO_CACHE = {"Cache-Control": "no-cache"}
    api.session.get.return_value.status_code = 200
    api.session.get.return_value.headers = {"Content-Type": "text/xml"}
    api.session.get.return_value.text = "<root />"
    spider = Spider(api, max_requests=1, delay=0)
    spider._data_parent_view["child.lua"] = "parent"

    child = Endpoint(type="menuData", tag="child.lua")
    spider._fetch_endpoint(child)

    assert api.session.get.call_count == 1
    assert spider._requests_made == 1
    assert child.fetched is False
    assert child.skipped_reason == "request-budget"


def test_failed_request_still_consumes_budget():
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.NO_CACHE = {}
    api.session.get.side_effect = requests.RequestException("offline")
    spider = Spider(api, max_requests=1, delay=0)

    spider._do_fetch_endpoint(Endpoint(type="menuView", tag="one"))
    spider._do_fetch_endpoint(Endpoint(type="menuView", tag="two"))

    assert api.session.get.call_count == 1
    assert spider._requests_made == 1


def test_discover_writes_private_file_and_refuses_overwrite(monkeypatch, tmp_path):
    result = {
        "stats": {
            "requests_made": 0,
            "errors": 0,
            "asset_count": 0,
            "endpoint_count": 0,
            "endpoint_fetched": 0,
            "endpoints_with_data": 0,
            "by_type": {},
            "by_shape": {},
            "skipped": {},
        }
    }
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.get_device_info.return_value = {}
    monkeypatch.setattr(cli, "get_api", lambda *args, **kwargs: api)
    monkeypatch.setattr(cli, "Spider", lambda *args, **kwargs: MagicMock(run=lambda: result))
    output = tmp_path / "report.json"
    runner = CliRunner()

    first = runner.invoke(app, ["--json", "discover", "--output", str(output)])
    second = runner.invoke(app, ["--json", "discover", "--output", str(output)])

    assert first.exit_code == 0, first.stdout
    assert os.stat(output).st_mode & 0o777 == 0o600
    assert second.exit_code == 1
    assert output.exists()


def test_discover_rejects_invalid_limits():
    runner = CliRunner()
    for args in (
        ["discover", "--max-requests", "0"],
        ["discover", "--delay", "-1"],
        ["discover", "--sample-chars", "0"],
    ):
        assert runner.invoke(app, args).exit_code == 2
