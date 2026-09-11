"""Tests for pydantic model alias mapping.

Each model maps the cryptic ZTE field names (mixed camelCase, snake,
prefixes, ``_InstID``) to friendly Python attributes. These tests
lock down the alias contract so a future rename of an attribute (or a
typo in an ``alias=``) can be caught without a live modem.

The fixtures are tiny ``dict``s that mirror the rows returned by
``ZTEH388XAPI._parse_instances`` (already covered separately in
``test_parsers.py``).
"""

from h388x_cli.models import (
    AdminUser,
    DslInterface,
    MobileWanInfo,
    PublicLan,
    SntpConfig,
    TopologyController,
    WebLoginTimeout,
    WifiSsidConfig,
)


def test_admin_user_aliases():
    u = AdminUser.model_validate(
        {"_InstID": "IGD.AU1", "Username": "admin", "Right": "1"}
    )
    assert u.id == "IGD.AU1"
    assert u.username == "admin"
    assert u.right == "1"


def test_web_login_timeout_coerces_int():
    """``Timeout`` arrives as a string; pydantic should coerce to int."""
    t = WebLoginTimeout.model_validate({"_InstID": "IGD", "Timeout": "5"})
    assert t.timeout == 5
    assert isinstance(t.timeout, int)


def test_public_lan_disabled_default():
    p = PublicLan.model_validate(
        {
            "_InstID": "IGD",
            "Enable": "Disabled",
            "PublicIP": "0.0.0.0",
            "PublicMask": "0.0.0.0",
        }
    )
    assert p.enabled == "Disabled"
    assert p.public_ip == "0.0.0.0"


def test_mobile_wan_info_empty_dongle():
    info = MobileWanInfo.model_validate(
        {
            "_InstID": "IGD",
            "MobileName": "",
            "SignalStrength": "0",
            "IMEI": "",
            "NetWorkMode": "",
            "MobileAlarm": "0",
        }
    )
    assert info.operator == ""
    assert info.signal_strength == 0
    assert info.alarm == 0


def test_topology_controller_aliases():
    c = TopologyController.model_validate(
        {
            "instID": "MESH.CONTROLLER",
            "SoftwareVer": "AGZHM_1.4.4",
            "BhStaRssi": "0",
            "LinkSpeed": "0",
            "accdevCount": 15,
            "MacAddr": "02:00:00:00:00:02",
            "DeviceName": "TEST-MODEM-0001",
            "AccessType": "Connecting",
            "Manufacturer": "ZTE",
            "IpAddr": "192.168.1.1",
        }
    )
    assert c.inst_id == "MESH.CONTROLLER"
    assert c.software_version == "AGZHM_1.4.4"
    assert c.associated_devices == 15
    assert c.mac == "02:00:00:00:00:02"


def test_topology_controller_allows_extra_fields():
    """The JSON view may carry extra scalars (e.g. ``IF_ERRORID``); model
    config ``extra='allow'`` keeps them in the dump for visibility."""
    c = TopologyController.model_validate(
        {
            "instID": "MESH.CONTROLLER",
            "IF_ERRORID": 0,
        }
    )
    dumped = c.model_dump()
    assert dumped.get("IF_ERRORID") == 0


def test_dsl_interface_full_row():
    d = DslInterface.model_validate(
        {
            "_InstID": "IGD.WD1.LINE0",
            "Enable": "1",
            "Status": "Up",
            "Module_type": "VDSL2",
            "CurrentProfile": "17a",
            "Data_path": "Fast/Interleaved",
            "tLinkEncapsulationUsed": "G.993.2_Annex_K_PTM",
            "Showtime_start": "124332",
            "Upstream_current_rate": "13641",
            "Upstream_max_rate": "13627",
            "Upstream_noise_margin": "54",
            "Upstream_power": "46",
            "Upstream_attenuation": "18",
            "Downstream_current_rate": "39805",
            "Downstream_max_rate": "39909",
            "Downstream_noise_margin": "58",
            "Downstream_power": "126",
            "Downstream_attenuation": "137",
            "Link_retrain": "0",
            "Fec_errors": "125875295",
        }
    )
    assert d.module_type == "VDSL2"
    assert d.profile == "17a"
    assert d.encapsulation == "G.993.2_Annex_K_PTM"
    assert d.downstream_current_rate == 39805
    assert d.upstream_noise_margin == 54
    assert d.fec_errors == 125875295


def test_wifi_ssid_config_adds_hidden_and_max_users():
    """``ESSIDHideEnable`` and ``MaxUserNum`` are the two fields the SSID
    config view exposes on top of the status view."""
    s = WifiSsidConfig.model_validate(
        {
            "_InstID": "DEV.WIFI.AP1",
            "Enable": "1",
            "WLANViewName": "DEV.WIFI.RD1",
            "Alias": "SSID1",
            "ESSID": "Your Wi is in another Fi",
            "ESSIDHideEnable": "0",
            "MaxUserNum": "64",
            "BeaconType": "11i",
            "WPAAuthMode": "PSKAuthentication",
            "11iAuthMode": "PSKAuthentication",
            "11iEncryptType": "AESEncryption",
        }
    )
    assert s.alias == "SSID1"
    assert s.essid == "Your Wi is in another Fi"
    assert s.hidden == 0
    assert s.max_users == 64
    assert s.wpa2_encrypt == "AESEncryption"


def test_sntp_config_aliases():
    cfg = SntpConfig.model_validate(
        {
            "_InstID": "IGD",
            "CurrentLocalTime": "2026-05-22T11:11:57",
            "NtpServer1": "ntp-tr069-1.interbusiness.it",
            "NtpServer2": "ntp-tr069-2.interbusiness.it",
            "NtpServer3": "time.fwa.tim.it",
            "NtpServer4": "",
            "NtpServer5": "",
            "ZoneIndex": "14",
            "AutoSetTzname": "0",
            "DaylightSavingsUsed": "1",
            "PollTimeInterval": "86400",
            "Dscp": "-1",
        }
    )
    assert cfg.current_local_time == "2026-05-22T11:11:57"
    assert cfg.ntp_server_1 == "ntp-tr069-1.interbusiness.it"
    assert cfg.zone_index == 14
    assert cfg.daylight_savings_used == 1
    assert cfg.poll_time_interval == 86400
    assert cfg.dscp == -1
