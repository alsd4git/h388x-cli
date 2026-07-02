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


# --- port-forwarding write actions -----------------------------------------

@responses.activate
def test_add_port_forwarding_rule_uses_apply_with_inst_id_minus_one(api):
    """The WebUI submits 'new' rows as ``IF_ACTION=Apply`` +
    ``OBJ_FWPM_ID._OBJ_InstID=-1``. Port number defaults must also
    propagate (internal_port = external_port, end-range = port)."""
    view = f"{HOST}{api.PORT_FORWARDING_VIEW_URL}"
    data = f"{HOST}{api.PORT_FORWARDING_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, body = api.add_port_forwarding_rule(
        description="ssh", protocol="tcp",
        external_port=22, internal_client="192.168.1.50",
    )
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    # protocol upper-cased
    assert "OBJ_FWPM_ID.Protocol=TCP" in sent
    # "new instance" magic marker
    assert "OBJ_FWPM_ID._OBJ_InstID=-1" in sent
    # port defaults: int port == ext port, end-range == port
    assert "OBJ_FWPM_ID.ExternalPort=22" in sent
    assert "OBJ_FWPM_ID.ExternalPortEndRange=22" in sent
    assert "OBJ_FWPM_ID.InternalPort=22" in sent
    # body must be prefixed with the OBJ root, not bare ParaNames
    assert "OBJ_FWPM_ID.Description=ssh" in sent
    # description+client present, no bare-name leaks
    assert "&Description=ssh" not in sent
    assert "OBJ_FWPM_ID.InternalClient=192.168.1.50" in sent


def test_add_port_forwarding_rejects_invalid_protocol(api):
    """Protocol validation runs entirely client-side; no HTTP traffic."""
    ok, body = api.add_port_forwarding_rule(
        description="x", protocol="GRE",
        external_port=80, internal_client="192.168.1.1",
    )
    assert ok is False
    assert "TCP/UDP/BOTH" in body


@responses.activate
def test_del_port_forwarding_rule_uses_delete_action(api):
    """Delete must POST ``IF_ACTION=Delete`` (the long form used by
    ``initial_button(buttonType='Delete')`` in home.html — NOT 'Del')."""
    view = f"{HOST}{api.PORT_FORWARDING_VIEW_URL}"
    data = f"{HOST}{api.PORT_FORWARDING_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.del_port_forwarding_rule("DEV.NAT.PtMapping7")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Delete" in sent
    # Defensive: must not regress to the wrong short form.
    assert "IF_ACTION=Del&" not in sent and not sent.endswith("IF_ACTION=Del")
    assert "OBJ_FWPM_ID._OBJ_InstID=DEV.NAT.PtMapping7" in sent


# --- DHCPv4 reservations write actions -------------------------------------

@responses.activate
def test_add_dhcp_reservation_uses_apply_with_inst_id_minus_one(api):
    """New reservations submit ``IF_ACTION=Apply`` +
    ``OBJ_DHCPBIND_ID._OBJ_InstID=-1`` with prefixed Name/IPAddr/MACAddr,
    matching the ``OBJ_DHCPBIND_ID.X:DHCPStaticRule`` form ids the
    modem's ``colonStripping()`` JS rewrites on submit."""
    view = f"{HOST}{api.DHCP_VIEW_URL}"
    data = f"{HOST}{api.DHCP_BINDINGS_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.add_dhcp_reservation(
        mac="AA:BB:CC:DD:EE:FF",
        ip_address="192.168.1.200",
        name="my-laptop",
    )
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "OBJ_DHCPBIND_ID._OBJ_InstID=-1" in sent
    assert "OBJ_DHCPBIND_ID.Name=my-laptop" in sent
    assert "OBJ_DHCPBIND_ID.IPAddr=192.168.1.200" in sent
    # MAC ":" url-encoded as %3A by requests; assert prefix + value parts.
    assert "OBJ_DHCPBIND_ID.MACAddr=" in sent
    assert "AA%3ABB%3ACC%3ADD%3AEE%3AFF" in sent
    # No bare (unprefixed) leak of the ParaNames.
    assert "&Name=my-laptop" not in sent
    assert "&IPAddr=" not in sent


@responses.activate
def test_del_dhcp_reservation_uses_delete_action(api):
    """Delete posts ``IF_ACTION=Delete`` with the prefixed instance id."""
    view = f"{HOST}{api.DHCP_VIEW_URL}"
    data = f"{HOST}{api.DHCP_BINDINGS_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.del_dhcp_reservation("DEV.V4DP.Sr.Pl1.Bd1")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Delete" in sent
    assert "IF_ACTION=Del&" not in sent and not sent.endswith("IF_ACTION=Del")
    # url-encoded "." stays "." in form bodies, no escape needed.
    assert "OBJ_DHCPBIND_ID._OBJ_InstID=DEV.V4DP.Sr.Pl1.Bd1" in sent


_DHCP_BIND_ROW = {
    "_OBJ_InstID": "DEV.V4DP.Sr.Pl1.Bd1",
    "Name": "old-name",
    "IPAddr": "192.168.1.50",
    "MACAddr": "AA:BB:CC:DD:EE:FF",
}


def _mock_dhcp_bind_read_then_post(api, row):
    """Mock the read (menuView+menuData) the edit does first, plus the
    token refresh + POST for OBJ_DHCPBIND_ID."""
    view = f"{HOST}{api.DHCP_VIEW_URL}"
    data = f"{HOST}{api.DHCP_BINDINGS_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"
    cells = "".join(f"<ParaName>{k}</ParaName><ParaValue>{v}</ParaValue>"
                    for k, v in row.items())
    xml = (
        "<ajax_response_xml_root><OBJ_DHCPBIND_ID><Instance>"
        f"{cells}</Instance></OBJ_DHCPBIND_ID></ajax_response_xml_root>"
    )
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body=xml, status=200)
    responses.add(responses.GET, login, json={"sess_token": "FRESH-TOKEN"}, status=200)
    responses.add(responses.POST, data, body=OK_XML, status=200)


@responses.activate
def test_edit_dhcp_reservation_overrides_only_given_fields(api):
    """A partial edit keeps untouched fields from the current row and
    re-posts a full Apply with the real InstID (not -1)."""
    _mock_dhcp_bind_read_then_post(api, _DHCP_BIND_ROW)

    ok, _ = api.edit_dhcp_reservation("DEV.V4DP.Sr.Pl1.Bd1", name="new-name")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    # real InstID, not the "new" marker
    assert "OBJ_DHCPBIND_ID._OBJ_InstID=DEV.V4DP.Sr.Pl1.Bd1" in sent
    assert "OBJ_DHCPBIND_ID._OBJ_InstID=-1" not in sent
    # changed field
    assert "OBJ_DHCPBIND_ID.Name=new-name" in sent
    # untouched fields preserved from the read-back row
    assert "OBJ_DHCPBIND_ID.IPAddr=192.168.1.50" in sent
    assert "AA%3ABB%3ACC%3ADD%3AEE%3AFF" in sent


@responses.activate
def test_edit_dhcp_reservation_unknown_id_fails_without_post(api):
    """Editing a missing reservation returns an error and issues no POST."""
    view = f"{HOST}{api.DHCP_VIEW_URL}"
    data = f"{HOST}{api.DHCP_BINDINGS_URL}"
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root/>", status=200)

    ok, msg = api.edit_dhcp_reservation("DEV.V4DP.Sr.Pl1.Bd9", name="x")
    assert ok is False
    assert "not found" in msg
    assert not [c for c in responses.calls if c.request.method == "POST"]


# --- firewall URL-filter write actions -------------------------------------

@responses.activate
def test_add_url_filter_rule_uses_apply_with_inst_id_minus_one(api):
    """New URL-filter rows submit ``IF_ACTION=Apply`` +
    ``OBJ_FWURL_ID._OBJ_InstID=-1`` with prefixed Name/Url fields."""
    view = f"{HOST}{api.FILTER_CRITERIA_VIEW_URL}"
    data = f"{HOST}{api.FW_URLFILTER_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.add_url_filter_rule(name="block-x", url="example.com")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "OBJ_FWURL_ID._OBJ_InstID=-1" in sent
    assert "OBJ_FWURL_ID.Name=block-x" in sent
    assert "OBJ_FWURL_ID.Url=example.com" in sent
    # no bare ParaName leak
    assert "&Name=block-x" not in sent
    assert "&Url=example.com" not in sent


@responses.activate
def test_del_url_filter_rule_uses_delete_action(api):
    """Delete posts ``IF_ACTION=Delete`` with the prefixed instance id."""
    view = f"{HOST}{api.FILTER_CRITERIA_VIEW_URL}"
    data = f"{HOST}{api.FW_URLFILTER_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.del_url_filter_rule("DEV.FW.CHAIN1.URLF1")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Delete" in sent
    assert "IF_ACTION=Del&" not in sent and not sent.endswith("IF_ACTION=Del")
    assert "OBJ_FWURL_ID._OBJ_InstID=DEV.FW.CHAIN1.URLF1" in sent


# --- firewall IP-filter write actions --------------------------------------

@responses.activate
def test_add_ip_filter_rule_uses_apply_with_inst_id_minus_one(api):
    """New IP-filter rows submit ``IF_ACTION=Apply`` +
    ``OBJ_FWIP_ID._OBJ_InstID=-1``. Protocol keyword maps to its number
    and is mirrored into both S_Protocol (UI helper) and Protocol."""
    view = f"{HOST}{api.FILTER_CRITERIA_VIEW_URL}"
    data = f"{HOST}{api.FW_IPFILTER_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.add_ip_filter_rule(name="blk", protocol="tcp", target="deny")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "OBJ_FWIP_ID._OBJ_InstID=-1" in sent
    assert "OBJ_FWIP_ID.Name=blk" in sent
    # tcp -> 6, mirrored into both helper + stored field
    assert "OBJ_FWIP_ID.Protocol=6" in sent
    assert "OBJ_FWIP_ID.S_Protocol=6" in sent
    # deny -> FilterTarget 0
    assert "OBJ_FWIP_ID.FilterTarget=0" in sent
    # enabled by default
    assert "OBJ_FWIP_ID.Enable=1" in sent


def test_add_ip_filter_rejects_invalid_protocol(api):
    """Protocol validation runs client-side; no HTTP traffic."""
    ok, body = api.add_ip_filter_rule(name="x", protocol="GRE")
    assert ok is False
    assert "ICMP/TCP/UDP" in body


def test_add_ip_filter_rejects_invalid_target(api):
    """Target validation runs client-side; no HTTP traffic."""
    ok, body = api.add_ip_filter_rule(name="x", protocol="tcp", target="maybe")
    assert ok is False
    assert "allow/deny" in body


@responses.activate
def test_del_ip_filter_rule_uses_delete_action(api):
    """Delete posts ``IF_ACTION=Delete`` with the prefixed instance id."""
    view = f"{HOST}{api.FILTER_CRITERIA_VIEW_URL}"
    data = f"{HOST}{api.FW_IPFILTER_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.del_ip_filter_rule("DEV.FW.CHAIN1.IPF1")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Delete" in sent
    assert "IF_ACTION=Del&" not in sent and not sent.endswith("IF_ACTION=Del")
    assert "OBJ_FWIP_ID._OBJ_InstID=DEV.FW.CHAIN1.IPF1" in sent


# --- enable/disable toggle (light InstSwitch) ------------------------------

@responses.activate
def test_set_port_forwarding_enabled_sends_only_enable_and_instid(api):
    """The on/off toggle must submit ``IF_ACTION=Apply`` with just the
    Enable flag + the real InstID (no other fields), so the modem keeps
    the rest of the row intact."""
    view = f"{HOST}{api.PORT_FORWARDING_VIEW_URL}"
    data = f"{HOST}{api.PORT_FORWARDING_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.set_port_forwarding_enabled("DEV.NAT.PtMapping7", True)
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "OBJ_FWPM_ID.Enable=1" in sent
    assert "OBJ_FWPM_ID._OBJ_InstID=DEV.NAT.PtMapping7" in sent
    # must NOT resend other fields (light InstSwitch, not full edit)
    assert "OBJ_FWPM_ID.Protocol" not in sent
    assert "OBJ_FWPM_ID.Description" not in sent


@responses.activate
def test_set_ip_filter_enabled_off_sends_enable_zero(api):
    """Disabling posts Enable=0 + the prefixed InstID for IP filters."""
    view = f"{HOST}{api.FILTER_CRITERIA_VIEW_URL}"
    data = f"{HOST}{api.FW_IPFILTER_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"

    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(
        responses.GET, login,
        json={"sess_token": "FRESH-TOKEN"}, status=200,
    )
    responses.add(responses.POST, data, body=OK_XML, status=200)

    ok, _ = api.set_ip_filter_enabled("DEV.FW.CHAIN1.IPF1", False)
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "OBJ_FWIP_ID.Enable=0" in sent
    assert "OBJ_FWIP_ID._OBJ_InstID=DEV.FW.CHAIN1.IPF1" in sent
    assert "OBJ_FWIP_ID.Protocol" not in sent


# --- full port-forward edit ------------------------------------------------

_PFWD_ROW = {
    "_OBJ_InstID": "DEV.NAT.PtMapping7",
    "Enable": "1",
    "Description": "ssh",
    "Protocol": "TCP",
    "ExternalPort": "22",
    "ExternalPortEndRange": "22",
    "InternalClient": "192.168.1.50",
    "InternalPort": "22",
    "RemoteHost": "0.0.0.0",
    "RemoteHostEndRange": "0.0.0.0",
}


def _mock_pfwd_read_then_post(api, row):
    """Mock the read (menuView+menuData) the edit does first, plus the
    token refresh + POST."""
    view = f"{HOST}{api.PORT_FORWARDING_VIEW_URL}"
    data = f"{HOST}{api.PORT_FORWARDING_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"
    # build an XML row the parser understands
    cells = "".join(f"<ParaName>{k}</ParaName><ParaValue>{v}</ParaValue>"
                    for k, v in row.items())
    xml = (
        "<ajax_response_xml_root><OBJ_FWPM_ID><Instance>"
        f"{cells}</Instance></OBJ_FWPM_ID></ajax_response_xml_root>"
    )
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body=xml, status=200)
    responses.add(responses.GET, login, json={"sess_token": "FRESH-TOKEN"}, status=200)
    responses.add(responses.POST, data, body=OK_XML, status=200)


@responses.activate
def test_edit_port_forwarding_overrides_only_given_fields(api):
    """A partial edit keeps untouched fields from the current row and
    re-posts a full Apply with the real InstID (not -1)."""
    _mock_pfwd_read_then_post(api, _PFWD_ROW)

    ok, _ = api.edit_port_forwarding_rule(
        "DEV.NAT.PtMapping7", external_port=2222, internal_port=22,
    )
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    # real InstID, not the "new" marker
    assert "OBJ_FWPM_ID._OBJ_InstID=DEV.NAT.PtMapping7" in sent
    assert "OBJ_FWPM_ID._OBJ_InstID=-1" not in sent
    # changed field
    assert "OBJ_FWPM_ID.ExternalPort=2222" in sent
    # untouched fields preserved from the read-back row
    assert "OBJ_FWPM_ID.Description=ssh" in sent
    assert "OBJ_FWPM_ID.Protocol=TCP" in sent
    assert "OBJ_FWPM_ID.InternalClient=192.168.1.50" in sent


@responses.activate
def test_edit_port_forwarding_unknown_id_fails_without_post(api):
    """Editing a missing rule returns an error and issues no POST."""
    view = f"{HOST}{api.PORT_FORWARDING_VIEW_URL}"
    data = f"{HOST}{api.PORT_FORWARDING_URL}"
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root/>", status=200)

    ok, msg = api.edit_port_forwarding_rule("DEV.NAT.PtMapping99", protocol="UDP")
    assert ok is False
    assert "not found" in msg
    assert not [c for c in responses.calls if c.request.method == "POST"]


# --- DHCP-pushed DNS set ---------------------------------------------------

_DHCP_CFG_ROW = {
    "_InstID": "IGD",
    "DNSServer1": "192.168.1.200",
    "DNSServer2": "192.168.1.201",
    "SubMask": "255.255.255.0",
    "IPAddr": "192.168.1.1",
    "DnsServerSource": "0",
    "MaxAddress": "192.168.1.200",
    "SubnetMask": "255.255.255.0",
    "LeaseTime": "86400",
    "ServerEnable": "1",
    "MinAddress": "192.168.1.10",
}


def _mock_dhcp_cfg_read_then_post(api, row):
    view = f"{HOST}{api.DHCP_VIEW_URL}"
    data = f"{HOST}{api.DHCP_CONFIG_URL}"
    login = f"{HOST}/?_type=loginData&_tag=login_entry"
    cells = "".join(f"<ParaName>{k}</ParaName><ParaValue>{v}</ParaValue>"
                    for k, v in row.items())
    xml = (
        "<ajax_response_xml_root><OBJ_Br0AndDhcpsHosCfg_ID><Instance>"
        f"{cells}</Instance></OBJ_Br0AndDhcpsHosCfg_ID></ajax_response_xml_root>"
    )
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body=xml, status=200)
    responses.add(responses.GET, login, json={"sess_token": "FRESH-TOKEN"}, status=200)
    responses.add(responses.POST, data, body=OK_XML, status=200)


@responses.activate
def test_set_dhcp_dns_swaps_only_dns_keeps_pool(api):
    """Setting DNS must preserve every other DHCP field (pool/lease/IP)
    and force DnsServerSource=0 (manual)."""
    _mock_dhcp_cfg_read_then_post(api, _DHCP_CFG_ROW)

    ok, _ = api.set_dhcp_dns(dns1="1.1.1.1", dns2="1.0.0.1")
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "IF_ACTION=Apply" in sent
    assert "DNSServer1=1.1.1.1" in sent
    assert "DNSServer2=1.0.0.1" in sent
    assert "DnsServerSource=0" in sent
    # untouched fields resubmitted verbatim
    assert "MinAddress=192.168.1.10" in sent
    assert "MaxAddress=192.168.1.200" in sent
    assert "LeaseTime=86400" in sent
    assert "IPAddr=192.168.1.1" in sent


@responses.activate
def test_set_dhcp_dns_from_wan_sets_source_one(api):
    """--from-wan flips DnsServerSource to 1 without needing servers."""
    _mock_dhcp_cfg_read_then_post(api, _DHCP_CFG_ROW)

    ok, _ = api.set_dhcp_dns(from_wan=True)
    assert ok is True

    post = [c for c in responses.calls if c.request.method == "POST"][0]
    sent = post.request.body
    assert "DnsServerSource=1" in sent


# --- config backup (download_config_backup) --------------------------------

_USRCFG_VIEW_HTML = (
    '<html><body>'
    '<form name="fDownload" id="fDownload" method="POST" '
    'enctype="multipart/form-data">'
    '<input type="hidden" name="config" id="config">'
    '<input type="hidden" id="TOKEN_DOWNLOAD" name="TOKEN_DOWNLOAD" '
    'value="&#51;&#49;&#53;">'  # HTML-entity encoded "315"
    '</form></body></html>'
)

# The "fake 404" reload page the view returns when not freshly armed.
_FAKE_404_HTML = (
    '<html><head><script>top.location.href = top.location.href;</script>'
    '</head><body><h2>404 Not Found</h2></body></html>'
)

_CONFIG_BYTES = b"\x04\x03\x02\x01\x00\x00\x00\x00\x00\x00\x00\x05H388X" + b"\x00" * 64


@responses.activate
def test_download_config_backup_happy_path(api):
    """Arm view -> read TOKEN_DOWNLOAD -> multipart POST -> octet-stream."""
    view = f"{HOST}{api.USRCFG_VIEW_URL}"
    dl = f"{HOST}{api.CONFIG_DOWNLOAD_URL}"
    responses.add(responses.GET, view, body=_USRCFG_VIEW_HTML, status=200)
    responses.add(
        responses.POST, dl, body=_CONFIG_BYTES, status=200,
        content_type="application/octet-stream",
    )

    ok, data = api.download_config_backup()
    assert ok is True
    assert data == _CONFIG_BYTES

    # The multipart POST carries the *decoded* TOKEN_DOWNLOAD ("315").
    post = [c for c in responses.calls if c.request.method == "POST"][0]
    body = post.request.body
    body = body.decode("latin-1") if isinstance(body, bytes) else body
    assert "TOKEN_DOWNLOAD" in body
    assert "315" in body


@responses.activate
def test_download_config_backup_relogins_when_view_not_armed(api):
    """A fake-404 view (no TOKEN_DOWNLOAD) triggers one login() + retry."""
    view = f"{HOST}{api.USRCFG_VIEW_URL}"
    dl = f"{HOST}{api.CONFIG_DOWNLOAD_URL}"
    # First view GET = fake-404, second (after relogin) = armed.
    responses.add(responses.GET, view, body=_FAKE_404_HTML, status=200)
    responses.add(responses.GET, view, body=_USRCFG_VIEW_HTML, status=200)
    responses.add(
        responses.POST, dl, body=_CONFIG_BYTES, status=200,
        content_type="application/octet-stream",
    )

    calls = {"n": 0}

    def fake_login():
        calls["n"] += 1
        return True

    api.login = fake_login  # type: ignore[assignment]
    ok, data = api.download_config_backup()
    assert ok is True
    assert data == _CONFIG_BYTES
    assert calls["n"] == 1  # relogged in exactly once


@responses.activate
def test_download_config_backup_fails_without_relogin_loop(api):
    """If the view stays unarmed even after relogin, return (False, msg)."""
    view = f"{HOST}{api.USRCFG_VIEW_URL}"
    responses.add(responses.GET, view, body=_FAKE_404_HTML, status=200)

    api.login = lambda: True  # type: ignore[assignment]
    ok, msg = api.download_config_backup()
    assert ok is False
    assert "TOKEN_DOWNLOAD" in msg
    # No POST attempted when the token was never found.
    assert not [c for c in responses.calls if c.request.method == "POST"]
