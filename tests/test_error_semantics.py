import json

import pytest
import requests
import responses

from h388x_cli import cli
from h388x_cli.api import ZTEH388XAPI
from h388x_cli.errors import ParseError, ProtocolError, TransportError


HOST = "http://modem.test"


def test_parse_instances_distinguishes_valid_empty_from_invalid_xml():
    assert ZTEH388XAPI._parse_instances("<root/>", "OBJ_X") == []
    with pytest.raises(ParseError):
        ZTEH388XAPI._parse_instances("not xml", "OBJ_X")


def test_parse_instances_rejects_mismatched_name_value_cardinality():
    body = (
        "<root><OBJ_X><Instance>"
        "<ParaName>A</ParaName><ParaValue>1</ParaValue>"
        "<ParaName>B</ParaName>"
        "</Instance></OBJ_X></root>"
    )
    with pytest.raises(ParseError, match="ParaName"):
        ZTEH388XAPI._parse_instances(body, "OBJ_X")


@responses.activate
def test_menudata_transport_failure_is_explicit(tmp_path):
    api = ZTEH388XAPI(HOST, cache_enabled=False, cache_dir=tmp_path)
    responses.add(
        responses.GET,
        f"{HOST}{api.ADMIN_USERS_VIEW_URL}",
        body=requests.ConnectionError("offline"),
    )
    with pytest.raises(TransportError, match="offline"):
        api.get_admin_users(retry=False)


@responses.activate
def test_menudata_http_failure_is_protocol_error(tmp_path):
    api = ZTEH388XAPI(HOST, cache_enabled=False, cache_dir=tmp_path)
    responses.add(
        responses.GET,
        f"{HOST}{api.ADMIN_USERS_VIEW_URL}",
        body="broken",
        status=503,
    )
    with pytest.raises(ProtocolError, match="HTTP 503"):
        api.get_admin_users(retry=False)


@pytest.mark.parametrize(
    "host",
    [
        "ftp://192.168.1.1",
        "http://admin:secret@192.168.1.1",
        "http://192.168.1.1/admin",
        "http://192.168.1.1?x=1",
    ],
)
def test_constructor_rejects_unsafe_or_ambiguous_base_urls(host):
    with pytest.raises(ProtocolError):
        ZTEH388XAPI(host, cache_enabled=False)


@responses.activate
def test_post_action_does_not_post_without_fresh_csrf_token(tmp_path):
    api = ZTEH388XAPI(
        HOST, "admin", "password", cache_enabled=False, cache_dir=tmp_path
    )
    api.session_token = "STALE"
    responses.add(responses.GET, f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}", body="<root/>")
    responses.add(
        responses.GET,
        f"{HOST}/?_type=loginData&_tag=login_entry",
        body="not-json",
    )
    api.login = lambda: False  # type: ignore[assignment]

    ok, message = api.set_web_login_timeout(10)

    assert ok is False
    assert "write was not attempted" in message
    assert not [call for call in responses.calls if call.request.method == "POST"]


@responses.activate
def test_post_action_parses_success_structurally(tmp_path):
    api = ZTEH388XAPI(
        HOST, "admin", "password", cache_enabled=False, cache_dir=tmp_path
    )
    api.session_token = "OLD"
    responses.add(responses.GET, f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}", body="<root/>")
    responses.add(
        responses.GET,
        f"{HOST}/?_type=loginData&_tag=login_entry",
        json={"sess_token": "FRESH"},
    )
    responses.add(
        responses.POST,
        f"{HOST}{api.WEB_TIMEOUT_URL}",
        body="<root><IF_ERRORSTR>  SUCC  </IF_ERRORSTR><IF_ERRORID>0</IF_ERRORID></root>",
    )
    ok, _ = api.set_web_login_timeout(10)
    assert ok is True


def test_console_entrypoint_turns_api_error_into_stable_human_exit(monkeypatch, capsys):
    cli.state.json = False

    def fail():
        raise TransportError("modem offline")

    monkeypatch.setattr(cli, "app", fail)
    with pytest.raises(SystemExit) as caught:
        cli.run_cli()
    assert caught.value.code == 1
    assert "transport_error" in capsys.readouterr().out


def test_console_entrypoint_turns_api_error_into_json(monkeypatch, capsys):
    cli.state.json = True

    def fail():
        raise ParseError("broken payload")

    monkeypatch.setattr(cli, "app", fail)
    with pytest.raises(SystemExit) as caught:
        cli.run_cli()
    assert caught.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "ok": False,
        "error": {"type": "parse_error", "message": "broken payload"},
    }
