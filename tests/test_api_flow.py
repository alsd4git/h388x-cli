"""End-to-end-ish tests for ``ZTEH388XAPI`` using ``responses`` to mock HTTP.

These exercise the ``menuView → menuData → parse`` dance for the most
common helpers without touching the modem. They cover:

- the auto re-login path on ``SessionTimeout``;
- raw and JSON variants (``_menudata_raw`` + ``get_topology``);
- ``hiddenData`` endpoints (``get_sntp``);
- a normal happy path against an XML row endpoint.
"""

import re

import pytest
import responses

from h388x_cli.api import ZTEH388XAPI


HOST = "http://modem.test"


@pytest.fixture
def api(tmp_path):
    """Build an API client without performing the real login handshake.

    We pre-seed the session token so the methods that look at it
    (logout, reboot) don't trip over a missing value, and we let each
    test register its own ``responses`` mocks. ``cache_dir`` points to
    an isolated temp directory so tests never touch the real
    ``~/.cache/h388x-cli``.
    """
    api = ZTEH388XAPI(
        HOST, "admin", "password",
        cache_enabled=False, cache_dir=tmp_path,
    )
    api.session_token = "FAKE-TOKEN"
    return api


# --- session expired detection wired through _menudata ---------------------

@responses.activate
def test_menudata_returns_empty_on_session_timeout_when_no_relogin(api):
    """If we say ``retry=False`` and the modem says SessionTimeout, we get []."""
    view = f"{HOST}/?_type=menuView&_tag=accountMgr&Menu3Location=0"
    data = f"{HOST}/?_type=menuData&_tag=devauth_accountmgr_lua.lua"
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root>SessionTimeout</root>", status=200)

    rows = api._menudata(
        "/?_type=menuView&_tag=accountMgr&Menu3Location=0",
        "/?_type=menuData&_tag=devauth_accountmgr_lua.lua",
        "OBJ_USERINFO_ID",
        retry=False,
    )
    assert rows == []


# --- happy path against the admin-users endpoint ---------------------------

ADMIN_USERS_XML = (
    "<ajax_response_xml_root>"
    "<IF_ERRORID>0</IF_ERRORID>"
    "<OBJ_USERINFO_ID>"
    "<Instance>"
    "<ParaName>_InstID</ParaName><ParaValue>IGD.AU1</ParaValue>"
    "<ParaName>Username</ParaName><ParaValue>admin</ParaValue>"
    "<ParaName>Right</ParaName><ParaValue>1</ParaValue>"
    "</Instance>"
    "</OBJ_USERINFO_ID>"
    "</ajax_response_xml_root>"
)


@responses.activate
def test_get_admin_users_parses_row(api):
    responses.add(
        responses.GET,
        f"{HOST}{api.ADMIN_USERS_VIEW_URL}",
        body="<root/>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HOST}{api.ADMIN_USERS_URL}",
        body=ADMIN_USERS_XML,
        status=200,
        content_type="text/xml",
    )
    rows = api.get_admin_users(retry=False)
    assert rows == [{"_InstID": "IGD.AU1", "Username": "admin", "Right": "1"}]


# --- raw + JSON path: topology endpoint ------------------------------------

TOPOLOGY_JSON = (
    '{"controllerData":{"DeviceName":"TEST-MODEM-0001",'
    '"SoftwareVer":"AGZHM_1.4.4","MacAddr":"02:00:00:00:00:02",'
    '"IpAddr":"192.168.1.1","accdevCount":15,"instID":"MESH.CONTROLLER",'
    '"AccessType":"Connecting","LinkSpeed":"0","BhStaRssi":"0",'
    '"Manufacturer":"ZTE","IF_ERRORID":0},'
    '"agentlay1":{"MGET_INST_NUM":0},"agentlay2":{"MGET_INST_NUM":0}}'
)


@responses.activate
def test_get_topology_parses_json(api):
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_VIEW_URL}",
        body="<root/>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_URL}",
        body=TOPOLOGY_JSON,
        status=200,
        content_type="application/json",
    )
    data = api.get_topology(retry=False)
    assert data["controllerData"]["DeviceName"] == "TEST-MODEM-0001"
    assert data["agentlay1"]["MGET_INST_NUM"] == 0


@responses.activate
def test_get_topology_returns_empty_on_invalid_json(api):
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_VIEW_URL}",
        body="<root/>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_URL}",
        body="not json {{{",
        status=200,
    )
    assert api.get_topology(retry=False) == {}


# --- hidden endpoint: SNTP -------------------------------------------------

SNTP_XML = (
    "<ajax_response_xml_root>"
    "<OBJ_SNTP_ID><Instance>"
    "<ParaName>_InstID</ParaName><ParaValue>IGD</ParaValue>"
    "<ParaName>NtpServer1</ParaName><ParaValue>ntp.example.org</ParaValue>"
    "<ParaName>ZoneIndex</ParaName><ParaValue>14</ParaValue>"
    "<ParaName>DaylightSavingsUsed</ParaName><ParaValue>1</ParaValue>"
    "<ParaName>PollTimeInterval</ParaName><ParaValue>86400</ParaValue>"
    "<ParaName>Dscp</ParaName><ParaValue>-1</ParaValue>"
    "<ParaName>AutoSetTzname</ParaName><ParaValue>0</ParaValue>"
    "<ParaName>CurrentLocalTime</ParaName><ParaValue>2026-05-22T12:00:00</ParaValue>"
    "</Instance></OBJ_SNTP_ID>"
    "</ajax_response_xml_root>"
)


@responses.activate
def test_get_sntp_no_view_arming(api):
    """``hiddenData`` endpoints should NOT trigger a preliminary menuView GET."""
    responses.add(
        responses.GET,
        f"{HOST}{api.SNTP_URL}",
        body=SNTP_XML,
        status=200,
        content_type="text/xml",
    )
    row = api.get_sntp(retry=False)
    assert row["NtpServer1"] == "ntp.example.org"
    assert row["ZoneIndex"] == "14"
    # exactly one HTTP call — no view arming
    assert len(responses.calls) == 1


# --- session re-login path -------------------------------------------------

@responses.activate
def test_menudata_relogins_on_session_timeout(api):
    """First call hits SessionTimeout; the helper should re-login then retry."""
    view = f"{HOST}{api.ADMIN_USERS_VIEW_URL}"
    data = f"{HOST}{api.ADMIN_USERS_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    # 1st view + 1st data = SessionTimeout, then login OK, then 2nd view+data OK.
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root>SessionTimeout</root>", status=200)
    responses.add(responses.GET, login, body="<root/>", status=200)
    # The real login() does several GET/POST steps and reads a token; we
    # don't have to model all of it — just make sure the retry branch is
    # reached and returns the second payload.
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body=ADMIN_USERS_XML, status=200)

    # Monkey-patch login() to a no-op success since the real handshake
    # is far more elaborate than this test needs to cover.
    api.login = lambda: True  # type: ignore[assignment]
    rows = api.get_admin_users(retry=True)
    assert rows and rows[0]["Username"] == "admin"


# --- write actions (_post_action) ------------------------------------------

OK_XML = (
    "<ajax_response_xml_root>"
    "<IF_ERRORSTR>SUCC</IF_ERRORSTR>"
    "<IF_ERRORID>0</IF_ERRORID>"
    "<sess_token>NEW-TOKEN</sess_token>"
    "</ajax_response_xml_root>"
)

ERR_PAGE_EXPIRED_XML = (
    "<ajax_response_xml_root>"
    "<IF_ERRORSTR>Page expired</IF_ERRORSTR>"
    "<IF_ERRORID>-1452</IF_ERRORID>"
    "</ajax_response_xml_root>"
)


@responses.activate
def test_set_web_login_timeout_happy_path(api):
    """Arm view -> refresh token via login_entry -> POST Apply -> OK."""
    view = f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}"
    data = f"{HOST}{api.WEB_TIMEOUT_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, body = api.set_web_login_timeout(10)
    assert ok is True
    assert "SUCC" in body
    # Session token rotated from the response.
    assert api.session_token == "NEW-TOKEN"

    # Verify the POST body contains the exact convention from the JS.
    post_call = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post_call.request.body
    assert "IF_ACTION=Apply" in sent
    assert "Timeout=10" in sent
    assert "_InstID=IGD" in sent
    # Token sent must be the freshly-fetched one, not the cached one.
    assert "_sessionTOKEN=FRESH-TOKEN" in sent


@responses.activate
def test_set_web_login_timeout_surfaces_modem_error(api):
    """Non-SUCC response → ok=False, body returned verbatim."""
    view = f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}"
    data = f"{HOST}{api.WEB_TIMEOUT_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=ERR_PAGE_EXPIRED_XML, status=200)

    ok, body = api.set_web_login_timeout(10)
    assert ok is False
    assert "-1452" in body


@responses.activate
def test_post_action_retries_on_session_timeout(api):
    """SessionTimeout on the POST should trigger a re-login + replay."""
    view = f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}"
    data = f"{HOST}{api.WEB_TIMEOUT_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    # First attempt:
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "T1"}, status=200,
    )
    responses.add(
        responses.POST, data,
        body="<root>SessionTimeout</root>", status=200,
    )
    # After re-login (mocked):
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "T2"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    api.login = lambda: True  # type: ignore[assignment]
    ok, body = api.set_web_login_timeout(7)
    assert ok is True
    assert "SUCC" in body
