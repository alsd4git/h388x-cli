from unittest.mock import Mock

from h388x_cli.api import ZTEH388XAPI


def _api():
    api = ZTEH388XAPI(cache_enabled=False)
    api._post_action = Mock(side_effect=AssertionError("write must not be attempted"))
    return api


def test_invalid_dhcp_reservation_never_reaches_post_action():
    api = _api()
    ok, message = api.add_dhcp_reservation("bad-mac", "192.168.1.20", "NAS")
    assert ok is False
    assert "validation error" in message
    api._post_action.assert_not_called()


def test_invalid_port_forward_never_reaches_post_action():
    api = _api()
    ok, message = api.add_port_forwarding_rule(
        description="bad",
        protocol="TCP",
        external_port=70000,
        internal_client="192.168.1.10",
    )
    assert ok is False
    assert "external_port" in message
    api._post_action.assert_not_called()


def test_invalid_url_filter_never_reaches_post_action():
    api = _api()
    ok, message = api.add_url_filter_rule("x" * 33, "example.test")
    assert ok is False
    assert "name" in message
    api._post_action.assert_not_called()


def test_invalid_ip_filter_never_reaches_post_action():
    api = _api()
    ok, message = api.add_ip_filter_rule("rule", "TCP", filter_index=99)
    assert ok is False
    assert "filter_index" in message
    api._post_action.assert_not_called()


def test_dhcp_edit_validates_final_payload_before_write():
    api = _api()
    api.get_dhcp_bindings = Mock(
        return_value=[
            {
                "_OBJ_InstID": "DEV.V4DP.Sr.Pl1.Bd1",
                "Name": "NAS",
                "IPAddr": "192.168.1.20",
                "MACAddr": "aa:bb:cc:dd:ee:ff",
            }
        ]
    )

    ok, message = api.edit_dhcp_reservation(
        "DEV.V4DP.Sr.Pl1.Bd1", ip_address="not-an-ip"
    )

    assert ok is False
    assert "ip_address" in message
    api._post_action.assert_not_called()
