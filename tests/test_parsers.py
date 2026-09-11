"""Tests for the low-level XML parsing helpers in ``h388x_cli.api``.

These tests do not touch the network. They feed fixed XML payloads
(captured live from the modem during reverse engineering) into the
parser to lock down the behaviour we depend on across all the
``get_*`` API methods.
"""

import pytest

from h388x_cli.api import ZTEH388XAPI
from h388x_cli.errors import ParseError


# --- _strip_prefix ----------------------------------------------------------


@pytest.mark.parametrize(
    "name,expected",
    [
        ("OBJ_DHCPHOSTINFO_ID.IPAddr", "IPAddr"),
        ("OBJ_FWDMZ_ID._OBJ_InstID", "_OBJ_InstID"),
        ("Username", "Username"),
        ("", ""),
    ],
)
def test_strip_prefix(name, expected):
    assert ZTEH388XAPI._strip_prefix(name) == expected


# --- _is_session_expired ----------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("<root>SessionTimeout</root>", True),
        (
            "<ajax_response_xml_root><IF_ERRORID>0</IF_ERRORID></ajax_response_xml_root>",
            False,
        ),
        ("", False),
    ],
)
def test_is_session_expired(text, expected):
    assert ZTEH388XAPI._is_session_expired(text) is expected


# --- _parse_instances -------------------------------------------------------

SIMPLE_XML = (
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


def test_parse_single_instance():
    rows = ZTEH388XAPI._parse_instances(SIMPLE_XML, "OBJ_USERINFO_ID")
    assert rows == [
        {"_InstID": "IGD.AU1", "Username": "admin", "Right": "1"},
    ]


PREFIXED_XML = (
    "<ajax_response_xml_root>"
    "<OBJ_FWDMZ_ID>"
    "<Instance>"
    "<ParaName>OBJ_FWDMZ_ID.Enable</ParaName><ParaValue>0</ParaValue>"
    "<ParaName>OBJ_FWDMZ_ID._OBJ_InstID</ParaName><ParaValue>IGD.FWDMZ.FWDMZ1</ParaValue>"
    "<ParaName>OBJ_FWDMZ_ID.InternalClient</ParaName><ParaValue></ParaValue>"
    "</Instance>"
    "</OBJ_FWDMZ_ID>"
    "</ajax_response_xml_root>"
)


def test_parse_instance_with_prefixed_field_names():
    """ZTE sometimes emits ``Root.Field`` ParaNames; we should drop the prefix."""
    rows = ZTEH388XAPI._parse_instances(PREFIXED_XML, "OBJ_FWDMZ_ID")
    assert rows == [
        {"Enable": "0", "_OBJ_InstID": "IGD.FWDMZ.FWDMZ1", "InternalClient": ""},
    ]


MULTI_INSTANCE_XML = (
    "<ajax_response_xml_root>"
    "<OBJ_VOIPPOSENABLE_ID>"
    "<Instance>"
    "<ParaName>_InstID</ParaName><ParaValue>IGD.SV.VS1.VY1</ParaValue>"
    "<ParaName>VoipPosEnable</ParaName><ParaValue>0</ParaValue>"
    "</Instance>"
    "<Instance>"
    "<ParaName>_InstID</ParaName><ParaValue>IGD.SV.VS1.VY2</ParaValue>"
    "<ParaName>VoipPosEnable</ParaName><ParaValue>1</ParaValue>"
    "</Instance>"
    "</OBJ_VOIPPOSENABLE_ID>"
    "</ajax_response_xml_root>"
)


def test_parse_multiple_instances():
    rows = ZTEH388XAPI._parse_instances(MULTI_INSTANCE_XML, "OBJ_VOIPPOSENABLE_ID")
    assert len(rows) == 2
    assert rows[0]["_InstID"].endswith("VY1")
    assert rows[1]["VoipPosEnable"] == "1"


def test_parse_empty_root_returns_empty_list():
    """A present-but-empty wrapper element must yield zero rows."""
    xml = (
        "<ajax_response_xml_root><OBJ_FWURL_ID></OBJ_FWURL_ID></ajax_response_xml_root>"
    )
    assert ZTEH388XAPI._parse_instances(xml, "OBJ_FWURL_ID") == []


def test_parse_unknown_root_returns_empty_list():
    """If the wrapper element isn't present we don't blow up."""
    assert ZTEH388XAPI._parse_instances(SIMPLE_XML, "OBJ_DOES_NOT_EXIST") == []


def test_parse_malformed_xml_raises_parse_error():
    """Bad XML is a protocol failure, not a legitimate empty collection."""
    with pytest.raises(ParseError):
        ZTEH388XAPI._parse_instances("not xml at all <<", "OBJ_X")


def test_parse_multi_root_payload():
    """voip_sipmedia_lua.lua ships TWO wrappers (one per VL line). We must
    collect Instance rows from all of them when scanning by root name."""
    xml = (
        "<ajax_response_xml_root>"
        "<OBJ_VOIPLINEVMEDAI_ID>"
        "<Instance>"
        "<ParaName>_InstID</ParaName><ParaValue>VL1.CL1</ParaValue>"
        "<ParaName>MediaVPri</ParaName><ParaValue>3</ParaValue>"
        "</Instance>"
        "</OBJ_VOIPLINEVMEDAI_ID>"
        "<OBJ_VOIPLINEVMEDAI_ID>"
        "<Instance>"
        "<ParaName>_InstID</ParaName><ParaValue>VL2.CL1</ParaValue>"
        "<ParaName>MediaVPri</ParaName><ParaValue>3</ParaValue>"
        "</Instance>"
        "</OBJ_VOIPLINEVMEDAI_ID>"
        "</ajax_response_xml_root>"
    )
    rows = ZTEH388XAPI._parse_instances(xml, "OBJ_VOIPLINEVMEDAI_ID")
    assert [r["_InstID"] for r in rows] == ["VL1.CL1", "VL2.CL1"]
