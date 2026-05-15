from typing import Optional

from pydantic import BaseModel, Field


class DSLStats(BaseModel):
    """DSL line statistics from OBJ_DSLINTERFACE_ID/Instance.

    NOTE: on AGZHM_1.4.4 the modem reports SNR/attenuation/power as deci-units
    (e.g. ``Downstream_noise_margin = 61`` means 6.1 dB). The CLI applies the
    /10 conversion on display.
    """

    status: Optional[str] = Field(None, alias="Status")
    profile: Optional[str] = Field(None, alias="CurrentProfile")
    module_type: Optional[str] = Field(None, alias="Module_type")
    data_path: Optional[str] = Field(None, alias="Data_path")

    downstream_curr_rate: Optional[int] = Field(None, alias="Downstream_current_rate")
    upstream_curr_rate: Optional[int] = Field(None, alias="Upstream_current_rate")
    downstream_max_rate: Optional[int] = Field(None, alias="Downstream_max_rate")
    upstream_max_rate: Optional[int] = Field(None, alias="Upstream_max_rate")

    # Deci-units: divide by 10 for human-readable dB / dBm.
    downstream_noise_margin: Optional[int] = Field(None, alias="Downstream_noise_margin")
    upstream_noise_margin: Optional[int] = Field(None, alias="Upstream_noise_margin")
    downstream_attenuation: Optional[int] = Field(None, alias="Downstream_attenuation")
    upstream_attenuation: Optional[int] = Field(None, alias="Upstream_attenuation")
    downstream_power: Optional[int] = Field(None, alias="Downstream_power")
    upstream_power: Optional[int] = Field(None, alias="Upstream_power")

    fec_errors: Optional[int] = Field(None, alias="Fec_errors")
    showtime_start: Optional[int] = Field(None, alias="Showtime_start")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class DeviceInfo(BaseModel):
    """Device information from OBJ_DEVINFO_ID/Instance (AGZHM firmware)."""

    model: Optional[str] = Field(None, alias="ModelName")
    serial_number: Optional[str] = Field(None, alias="SerialNumber")
    software_version: Optional[str] = Field(None, alias="SoftwareVer")
    hardware_version: Optional[str] = Field(None, alias="HardwareVer")
    boot_version: Optional[str] = Field(None, alias="BootVer")
    firmware_date: Optional[str] = Field(None, alias="VerDate")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class WanConnection(BaseModel):
    """Single WAN connection entry from ID_WAN_COMFIG/Instance."""

    name: Optional[str] = Field(None, alias="WANCName")
    status: Optional[str] = Field(None, alias="ConnStatus")
    error: Optional[str] = Field(None, alias="ConnError")
    ip_address: Optional[str] = Field(None, alias="IPAddress")
    subnet_mask: Optional[str] = Field(None, alias="SubnetMask")
    gateway: Optional[str] = Field(None, alias="GateWay")
    dns1: Optional[str] = Field(None, alias="DNS1")
    dns2: Optional[str] = Field(None, alias="DNS2")
    dns3: Optional[str] = Field(None, alias="DNS3")
    uptime_seconds: Optional[int] = Field(None, alias="UpTime")
    mac: Optional[str] = Field(None, alias="WorkIFMac")
    mtu: Optional[int] = Field(None, alias="MTU")
    vlan_id: Optional[int] = Field(None, alias="VLANID")
    is_nat: Optional[int] = Field(None, alias="IsNAT")
    mode: Optional[str] = Field(None, alias="mode")
    ip_mode: Optional[str] = Field(None, alias="IpMode")
    services: Optional[str] = Field(None, alias="StrServList")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class Client(BaseModel):
    """Connected device (LAN or Wi-Fi) from OBJ_ACCESSDEV_ID/Instance."""

    hostname: Optional[str] = Field(None, alias="HostName")
    ipv4: Optional[str] = Field(None, alias="IPAddress")
    ipv6: Optional[str] = Field(None, alias="IPV6Address")
    mac: Optional[str] = Field(None, alias="MACAddress")
    interface: Optional[str] = Field(None, alias="AliasName")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class WifiRadio(BaseModel):
    """A single WLAN radio (2.4 GHz / 5 GHz) from OBJ_WLANSETTING_ID/Instance.

    On AGZHM 1.4.4 the modem reports just ``RadioStatus`` (1 = on, 0 = off)
    and ``Band`` (e.g. ``2.4GHz`` / ``5GHz``).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    band: Optional[str] = Field(None, alias="Band")
    radio_on: Optional[int] = Field(None, alias="RadioStatus")

    model_config = {"populate_by_name": True, "extra": "ignore"}


class FirewallLevel(BaseModel):
    """Active firewall preset (OBJ_FWLEVEL_ID)."""

    id: Optional[str] = Field(None, alias="_InstID")
    level: Optional[str] = Field(None, alias="Level")  # Low | Middle | High
    model_config = {"populate_by_name": True, "extra": "ignore"}


class FirewallDos(BaseModel):
    """DoS protection state (OBJ_FWDOS_ID)."""

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    threshold: Optional[int] = Field(None, alias="Threshold")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class UrlFilterGlobal(BaseModel):
    """URL-filter master switch + global target action (OBJ_FWBASE_ID).

    ``target`` is a ZTE-encoded action; on AGZHM 1.4.4 ``0`` = block listed
    URLs, ``1`` = allow only listed URLs.
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    enabled: Optional[int] = Field(None, alias="UrlFilterEnable")
    target: Optional[int] = Field(None, alias="UrlFilterTarget")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class Dmz(BaseModel):
    """DMZ state (OBJ_FWDMZ_ID)."""

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    internal_client: Optional[str] = Field(None, alias="InternalClient")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class WifiAP(BaseModel):
    """A single WLAN AP/SSID from OBJ_WLANAP_ID/Instance (``wlan_status``).

    Each radio exposes 4 APs (Main + 3 guest), so an H388X reports 8 entries
    total. ``radio_id`` (``WLANViewName``) is e.g. ``DEV.WIFI.RD1`` and links
    the AP back to a ``WifiRadio.id``.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    radio_id: Optional[str] = Field(None, alias="WLANViewName")
    alias: Optional[str] = Field(None, alias="Alias")
    essid: Optional[str] = Field(None, alias="ESSID")
    beacon_type: Optional[str] = Field(None, alias="BeaconType")
    wpa_auth_mode: Optional[str] = Field(None, alias="WPAAuthMode")
    wpa_encrypt: Optional[str] = Field(None, alias="WPAEncryptType")
    wpa2_auth_mode: Optional[str] = Field(None, alias="11iAuthMode")
    wpa2_encrypt: Optional[str] = Field(None, alias="11iEncryptType")

    model_config = {"populate_by_name": True, "extra": "ignore"}
