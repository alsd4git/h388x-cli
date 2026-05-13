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
