import json
import os
from unittest.mock import MagicMock

import requests
from typer.testing import CliRunner

from h388x_cli import cli
from h388x_cli.cli import app
from h388x_cli.discovery import Endpoint, Spider, compare_discovery_reports


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
    monkeypatch.setattr(
        cli, "Spider", lambda *args, **kwargs: MagicMock(run=lambda: result)
    )
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


def test_compare_discovery_reports_is_deterministic_and_ignores_samples():
    previous = {
        "endpoints": [
            {
                "type": "menuData",
                "tag": "old.lua",
                "extras": {},
                "fetched": True,
                "status": 200,
                "shape": "xml-empty",
                "sample": "old sample",
                "bytes": 12,
            },
            {
                "type": "menuData",
                "tag": "changed.lua",
                "extras": {"InstNum": "1"},
                "fetched": True,
                "status": 200,
                "shape": "xml-instances",
                "instance_count": 1,
                "field_names": ["Enable"],
            },
        ]
    }
    current = {
        "endpoints": [
            {
                "type": "menuData",
                "tag": "changed.lua",
                "extras": {"InstNum": "1"},
                "fetched": True,
                "status": 200,
                "shape": "xml-instances",
                "instance_count": 2,
                "field_names": ["Enable", "SSID"],
                "sample": "new sample",
                "bytes": 99,
            },
            {
                "type": "menuData",
                "tag": "new.lua",
                "extras": {},
                "fetched": False,
                "skipped_reason": "mutating-tag",
            },
        ]
    }

    diff = compare_discovery_reports(current, previous)

    assert diff["summary"] == {"added": 1, "removed": 1, "changed": 1}
    assert diff["added"][0]["tag"] == "new.lua"
    assert diff["removed"][0]["tag"] == "old.lua"
    assert diff["changed"][0]["fields"]["instance_count"] == {
        "previous": 1,
        "current": 2,
    }


def test_discover_previous_emits_comparison(monkeypatch, tmp_path):
    previous = tmp_path / "previous.json"
    previous.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "type": "menuData",
                        "tag": "old.lua",
                        "extras": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    current = {
        "endpoints": [
            {
                "type": "menuData",
                "tag": "new.lua",
                "extras": {},
            }
        ],
        "stats": {
            "requests_made": 0,
            "errors": 0,
            "asset_count": 0,
            "endpoint_count": 1,
            "endpoint_fetched": 0,
            "endpoints_with_data": 0,
            "by_type": {},
            "by_shape": {},
            "skipped": {},
        },
    }
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.get_device_info.return_value = {}
    monkeypatch.setattr(cli, "get_api", lambda *args, **kwargs: api)
    monkeypatch.setattr(
        cli, "Spider", lambda *args, **kwargs: MagicMock(run=lambda: current)
    )
    output = tmp_path / "current.json"

    result = CliRunner().invoke(
        app,
        ["--json", "discover", "--previous", str(previous), "--output", str(output)],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["comparison"]["summary"] == {
        "added": 1,
        "removed": 1,
        "changed": 0,
    }
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["comparison"] == payload["comparison"]


def test_endpoint_url_encodes_extra_query_values_without_mangling_tag():
    ep = Endpoint(
        type="menuData",
        tag="foo/bar.lua",
        extras={"name": "a b&c", "value": "x=y"},
    )
    assert ep.url() == "/?_type=menuData&_tag=foo/bar.lua&name=a%20b%26c&value=x%3Dy"


def test_asset_paths_resolve_relative_to_referring_asset():
    assert (
        Spider._normalize_path("../common/app.js", "/js/pages/status.html")
        == "/js/common/app.js"
    )
    assert (
        Spider._normalize_path("./widget.js?cache=1#x", "/js/pages/status.html")
        == "/js/pages/widget.js"
    )
    assert (
        Spider._normalize_path("/root/app.js", "/js/pages/status.html")
        == "/root/app.js"
    )
    assert (
        Spider._normalize_path("https://evil.example/x.js", "/js/pages/status.html")
        == ""
    )
    assert Spider._normalize_path("//evil.example/x.js", "/js/pages/status.html") == ""


def test_mutating_classifier_uses_semantic_tokens_not_substrings():
    assert Spider._looks_mutating("settings_status_lua.lua") is False
    assert Spider._looks_mutating("wlan_setting_lua.lua") is False
    assert Spider._looks_mutating("firewall_add_rule_lua.lua") is True
    assert Spider._looks_mutating("do_download_usercfg.lua") is True
    assert Spider._looks_mutating("devmgr_restartmgr_lua.lua") is True
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


def test_session_timeout_relogin_retries_and_records_only_final_payload():
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.NO_CACHE = {}
    timeout = MagicMock()
    timeout.status_code = 200
    timeout.headers = {"Content-Type": "text/xml"}
    timeout.text = "<root>SessionTimeout</root>"
    success = MagicMock()
    success.status_code = 200
    success.headers = {"Content-Type": "text/xml"}
    success.text = "<root><OBJ_X></OBJ_X></root>"
    api.session.get.side_effect = [timeout, success]
    api._is_session_expired.side_effect = lambda body: "SessionTimeout" in body
    api.login.return_value = True
    spider = Spider(api, max_requests=2, delay=0)
    ep = Endpoint(type="menuView", tag="statusMgr")

    body = spider._do_fetch_endpoint(ep)

    assert body == success.text
    assert api.login.call_count == 1
    assert api.session.get.call_count == 2
    assert spider._requests_made == 2
    assert ep.shape == "xml-empty"
    assert ep.sample == success.text
    assert ep.error is None


def test_session_timeout_failed_relogin_is_recorded_as_error():
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.NO_CACHE = {}
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "text/xml"}
    response.text = "<root>SessionTimeout</root>"
    api.session.get.return_value = response
    api._is_session_expired.return_value = True
    api.login.return_value = False
    spider = Spider(api, max_requests=2, delay=0)
    ep = Endpoint(type="menuView", tag="statusMgr")

    assert spider._do_fetch_endpoint(ep) is None
    assert ep.shape == "session-timeout"
    assert "re-login failed" in ep.error
    assert spider._errors == 1


def test_session_retry_respects_spider_request_budget():
    api = MagicMock()
    api.base_url = "http://modem.test"
    api.NO_CACHE = {}
    response = MagicMock()
    response.status_code = 200
    response.headers = {"Content-Type": "text/xml"}
    response.text = "<root>SessionTimeout</root>"
    api.session.get.return_value = response
    api._is_session_expired.return_value = True
    api.login.return_value = True
    spider = Spider(api, max_requests=1, delay=0)
    ep = Endpoint(type="menuView", tag="statusMgr")

    assert spider._do_fetch_endpoint(ep) is None
    assert api.session.get.call_count == 1
    assert "request budget" in ep.error
    assert spider._requests_made == 1


def test_discovered_query_values_decode_before_canonical_reencoding():
    found = Spider._extract_endpoints(
        '"/?_type=menuData&_tag=example.lua&name=a%20b&token=x%2By"'
    )

    assert found == [("menuData", "example.lua", {"name": "a b", "token": "x+y"})]
    tp, tag, extras = found[0]
    assert Endpoint(type=tp, tag=tag, extras=extras).url() == (
        "/?_type=menuData&_tag=example.lua&name=a%20b&token=x%2By"
    )
