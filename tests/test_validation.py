import pytest
from pydantic import ValidationError

from h388x_cli.validation import (
    DhcpReservationSpec,
    IpFilterSpec,
    PortForwardSpec,
    UrlFilterSpec,
    validation_error_message,
)


def test_dhcp_reservation_normalizes_mac_and_ipv4():
    spec = DhcpReservationSpec(
        mac="AA-BB-CC-DD-EE-FF",
        ip_address="192.168.1.20",
        name="NAS",
    )
    assert spec.mac == "aa:bb:cc:dd:ee:ff"
    assert spec.ip_address == "192.168.1.20"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mac", "not-a-mac"),
        ("ip_address", "999.1.1.1"),
        ("name", ""),
    ],
)
def test_dhcp_reservation_rejects_invalid_core_fields(field, value):
    data = {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip_address": "192.168.1.20",
        "name": "NAS",
    }
    data[field] = value
    with pytest.raises(ValidationError):
        DhcpReservationSpec(**data)


def test_port_forward_normalizes_protocol_and_validates_range():
    spec = PortForwardSpec(
        description="HTTPS",
        protocol="tcp",
        external_port=443,
        external_port_end=444,
        internal_client="192.168.1.10",
        internal_port=443,
    )
    assert spec.protocol == "TCP"

    with pytest.raises(ValidationError):
        PortForwardSpec(
            description="bad",
            protocol="tcp",
            external_port=5000,
            external_port_end=4000,
            internal_client="192.168.1.10",
            internal_port=5000,
        )


@pytest.mark.parametrize("port", [0, 65536])
def test_port_forward_rejects_out_of_range_ports(port):
    with pytest.raises(ValidationError):
        PortForwardSpec(
            description="bad",
            protocol="tcp",
            external_port=port,
            external_port_end=port,
            internal_client="192.168.1.10",
            internal_port=443,
        )


def test_url_filter_enforces_observed_webui_limits():
    UrlFilterSpec(name="ads", url="example.test")

    with pytest.raises(ValidationError):
        UrlFilterSpec(name="x" * 33, url="example.test")
    with pytest.raises(ValidationError):
        UrlFilterSpec(name="caffè", url="example.test")
    with pytest.raises(ValidationError):
        UrlFilterSpec(name="ads", url="x" * 129)


def test_ip_filter_normalizes_aliases_and_numeric_fields():
    spec = IpFilterSpec(
        name="allow-dns",
        protocol="udp",
        target="permit",
        filter_index=3,
        ip_version="4",
        source_ip="192.168.1.20",
        min_dst_port="53",
        max_dst_port="53",
        dscp="0",
    )
    assert spec.protocol == "UDP"
    assert spec.target == "allow"
    assert spec.min_dst_port == "53"
    assert spec.dscp == "0"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"protocol": "999"},
        {"target": "maybe"},
        {"filter_index": 21},
        {"ip_version": "5"},
        {"source_ip": "bad-ip"},
        {"min_dst_port": "0"},
        {"dscp": "64"},
        {"min_src_port": "200", "max_src_port": "100"},
    ],
)
def test_ip_filter_rejects_invalid_values(kwargs):
    data = {"name": "rule", "protocol": "TCP"}
    data.update(kwargs)
    with pytest.raises(ValidationError):
        IpFilterSpec(**data)


def test_validation_error_message_is_compact():
    with pytest.raises(ValidationError) as caught:
        DhcpReservationSpec(mac="bad", ip_address="bad", name="")
    message = validation_error_message(caught.value)
    assert "mac:" in message
    assert "ip_address:" in message
    assert "name:" in message
