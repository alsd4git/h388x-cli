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


class DnsLocal(BaseModel):
    """Modem-side DNS server config (OBJ_DNS_ID).

    ``SerIPAddress1`` / ``SerIPAddress2`` set to ``0.0.0.0`` mean the modem
    is using DNS servers from the WAN connection (no manual override).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    server1: Optional[str] = Field(None, alias="SerIPAddress1")
    server2: Optional[str] = Field(None, alias="SerIPAddress2")
    domain_name: Optional[str] = Field(None, alias="DomainName")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class DnsHostname(BaseModel):
    """A DNS-bound host known to the modem (ALLDNSHOST/Instance).

    On AGZHM 1.4.4 the modem exposes the union of DHCP-learned + manually
    bound hostnames here. ``LeaseTime`` is in seconds (``0`` for static).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    hostname: Optional[str] = Field(None, alias="HostName")
    ip_address: Optional[str] = Field(None, alias="IPAddress")
    mac: Optional[str] = Field(None, alias="MacAddr")
    lease_time: Optional[int] = Field(None, alias="LeaseTime")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class WifiRadioAdvanced(BaseModel):
    """Per-radio advanced config (OBJ_WLANSETTING_ID/Instance, ``basicadconf``).

    Same root as ``WifiRadio`` but a different ZTE endpoint that exposes
    the channel/bandwidth/power knobs instead of the on/off state.
    ``BandWidth`` is e.g. ``Auto``, ``20MHz``, ``40MHz``, ``80MHz``.
    ``TxPower`` is the raw string the modem stores (``100%``, ``75%``...).
    ``CountryCode`` is the ZTE 3-letter region code (``ITI`` = Italy).
    ``CardMode`` / ``Standard`` are comma-separated PHY mode lists.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    band: Optional[str] = Field(None, alias="Band")
    auto_channel: Optional[int] = Field(None, alias="AutoChannelEnabled")
    channel: Optional[int] = Field(None, alias="Channel")
    bandwidth: Optional[str] = Field(None, alias="BandWidth")
    side_band: Optional[str] = Field(None, alias="SideBand")
    tx_power: Optional[str] = Field(None, alias="TxPower")
    country_code: Optional[str] = Field(None, alias="CountryCode")
    standard: Optional[str] = Field(None, alias="Standard")
    card_mode: Optional[str] = Field(None, alias="CardMode")
    beacon_interval: Optional[int] = Field(None, alias="BeaconInterval")
    short_gi: Optional[int] = Field(None, alias="SGIEnabled")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class WifiAclPolicy(BaseModel):
    """Per-AP MAC filter policy (OBJ_WLANACL_ID/Instance).

    Eight rows total (one per AP). ``ACLPolicy`` is the modem's string:
    ``Disabled`` (no filter), ``Allow`` (whitelist), ``Deny`` (blacklist).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    alias: Optional[str] = Field(None, alias="Alias")
    policy: Optional[str] = Field(None, alias="ACLPolicy")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class WifiAclRule(BaseModel):
    """A single MAC ACL entry (OBJ_ACLCFG_ID/Instance).

    No live rules were observed to lock the schema; the modem usually
    exposes a MAC plus a parent-AP reference. ``extra='allow'`` keeps
    any extra columns surfaced in the JSON output.
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    mac: Optional[str] = Field(None, alias="MACAddress")
    ap_id: Optional[str] = Field(None, alias="ParentAclID")
    model_config = {"populate_by_name": True, "extra": "allow"}


class WifiSchedule(BaseModel):
    """A Wi-Fi scheduling entry (OBJ_WLAN_WIFISCHEDULE/Instance).

    One row per AP. The schedule is a recurring weekly window:
    ``StartHour``:``StartMin`` -> ``EndHour``:``EndMin`` on the
    days where ``Time_Day_M/T/We/Th/Fri/Sa/Su`` = 1.

    ``Action`` is the modem's encoding of what to do during the
    window (typically 0 = turn the SSID OFF inside the window).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="WLANWiFiScheduleEnable")
    action: Optional[int] = Field(None, alias="Action")
    start_hour: Optional[int] = Field(None, alias="StartHour")
    start_min: Optional[int] = Field(None, alias="StartMin")
    end_hour: Optional[int] = Field(None, alias="EndHour")
    end_min: Optional[int] = Field(None, alias="EndMin")
    day_mon: Optional[int] = Field(None, alias="Time_Day_M")
    day_tue: Optional[int] = Field(None, alias="Time_Day_T")
    day_wed: Optional[int] = Field(None, alias="Time_Day_We")
    day_thu: Optional[int] = Field(None, alias="Time_Day_Th")
    day_fri: Optional[int] = Field(None, alias="Time_Day_Fri")
    day_sat: Optional[int] = Field(None, alias="Time_Day_Sa")
    day_sun: Optional[int] = Field(None, alias="Time_Day_Su")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class EasyMeshState(BaseModel):
    """EasyMesh master switch (OBJ_EASYMESHENABLE_ID, single)."""

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="EasyMeshEnable")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class BandSteeringState(BaseModel):
    """Band steering master switch (OBJ_BANDSTEERENABLE_ID, single)."""

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="BandSteeringEnable")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class Dms(BaseModel):
    """DLNA / DMS media-server config (OBJ_DMS_ID, single instance).

    On AGZHM 1.4.4 the server is off by default; ``PathRoot`` /
    ``ContentList`` point at ``/mnt`` (where the modem mounts attached
    USB storage). ``RescanTime`` is in seconds; ``0`` means no periodic
    rescan (only on demand).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    name: Optional[str] = Field(None, alias="DmsName")
    path_root: Optional[str] = Field(None, alias="PathRoot")
    content_list: Optional[str] = Field(None, alias="ContentList")
    rescan_time: Optional[int] = Field(None, alias="RescanTime")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class FtpServer(BaseModel):
    """FTP server master switch (OBJ_FMFTPSERVERCFG_ID, single)."""

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    enabled: Optional[int] = Field(None, alias="FtpEnable")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class FtpUser(BaseModel):
    """A single FTP user (OBJ_FMFTPUSER_ID/Instance)."""

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    username: Optional[str] = Field(None, alias="Username")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class NanoCdnStatus(BaseModel):
    """NanoCDN runtime stats (OBJ_NANOCDN_STATUS_ID, single instance).

    NanoCDN is the TIM/IPTV multicast-to-unicast offload baked into the
    Hub+. ``Status`` is a numeric state (``1`` = running on observed
    units); ``McastFrame`` is the lifetime counter of multicast frames
    the offload has processed. The Min/Max bitrate fields are in bps.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    status: Optional[int] = Field(None, alias="Status")
    sessions: Optional[int] = Field(None, alias="SessionNumber")
    min_sessions: Optional[int] = Field(None, alias="MinSessionNumber")
    max_sessions: Optional[int] = Field(None, alias="MaxSessionNumber")
    mcast_bitrate: Optional[int] = Field(None, alias="MulticastsBitrate")
    min_mcast_bitrate: Optional[int] = Field(None, alias="MinMulticastsBitrate")
    max_mcast_bitrate: Optional[int] = Field(None, alias="MaxMulticastsBitrate")
    mcast_frames: Optional[int] = Field(None, alias="McastFrame")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class UpnpConfig(BaseModel):
    """UPnP IGD master switch (OBJ_UPNPCONFIG_ID, single instance)."""

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    enabled: Optional[int] = Field(None, alias="EnableUPnPIGD")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class UpnpPortMapping(BaseModel):
    """A live UPnP IGD port mapping (OBJ_UPNPPORTMAP_ID/Instance).

    No live mappings were observed on this firmware to lock the schema
    down, so the field aliases match the ZTE/IGD common naming and any
    additional fields the modem emits are kept (``extra='allow'``) so
    the JSON view stays complete even when our typed accessors miss
    a column.
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    description: Optional[str] = Field(None, alias="Description")
    protocol: Optional[str] = Field(None, alias="Protocol")
    external_port: Optional[int] = Field(None, alias="ExternalPort")
    internal_client: Optional[str] = Field(None, alias="InternalClient")
    internal_port: Optional[int] = Field(None, alias="InternalPort")
    enabled: Optional[int] = Field(None, alias="PortMappingEnabled")
    lease_duration: Optional[int] = Field(None, alias="PortMappingLeaseDuration")
    model_config = {"populate_by_name": True, "extra": "allow"}


class VoipLine(BaseModel):
    """A virtual VoIP line from OBJ_VOIPVPLINE_ID/Instance.

    Two such instances exist (IGD.SV.VS1.VP1.VL1, .VL2). ``IsOnline`` is
    the localized state the modem renders in the UI; on AGZHM 1.4.4 (TIM)
    typical values are ``Registrato`` and ``Non registrato``.

    ``PhyList`` (only populated by the flexible-binding endpoint) lists
    the physical TEL jack indices bound to this virtual line, e.g.
    ``"0,1"`` = both phone ports ring on this line.
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    id_alt: Optional[str] = Field(None, alias="_InstID")
    is_online: Optional[str] = Field(None, alias="IsOnline")
    phy_list: Optional[str] = Field(None, alias="PhyList")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class VoipSipLine(BaseModel):
    """A SIP user-agent line from OBJ_VOIPSIPLINE_ID/Instance.

    Two instances (LS suffix of each VL). Carries the user-visible phone
    name (``Telefono1``/``Telefono2``) and the registered SIP auth user,
    which on TIM lines is the E.164 phone number (``+39...``).
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    phone_name: Optional[str] = Field(None, alias="PhoneName")
    auth_username: Optional[str] = Field(None, alias="AuthUserName")
    is_online: Optional[str] = Field(None, alias="IsOnline")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class Dhcp6Server(BaseModel):
    """LAN DHCPv6 server configuration (OBJ_DHCP6S_ID, single instance).

    On AGZHM 1.4.4:
    - ``IANAEnable`` enables IA_NA (stateful address assignment).
    - ``IsPrefixAutoMode`` = 1 means the modem uses the prefix delegated
      by the WAN; when 0, ``IANAManualPrefixes`` lists the local prefix.
    - ``ManualDNSEnable`` toggles between auto-DNS and the manual
      ``DNSAddr1/2/3`` values pushed via DHCPv6.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    iana_enabled: Optional[int] = Field(None, alias="IANAEnable")
    prefix_auto: Optional[int] = Field(None, alias="IsPrefixAutoMode")
    manual_prefixes: Optional[str] = Field(None, alias="IANAManualPrefixes")
    manual_dns: Optional[int] = Field(None, alias="ManualDNSEnable")
    dns1: Optional[str] = Field(None, alias="DNSAddr1")
    dns2: Optional[str] = Field(None, alias="DNSAddr2")
    dns3: Optional[str] = Field(None, alias="DNSAddr3")
    dns_refresh_time: Optional[int] = Field(None, alias="DnsRefreshTime")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class RouterAdvertisement(BaseModel):
    """IPv6 Router Advertisement service (OBJ_RAIS_ID, single instance).

    Standard RFC 4861 flags from the RA daemon:
    - ``AdvManagedFlag`` (M flag): clients use DHCPv6 for addresses.
    - ``AdvOtherConfigFlag`` (O flag): clients use DHCPv6 for other config.
    - ``IsPrefixAutoMode`` = 1 means advertise the WAN-delegated prefix;
      otherwise ``ManualPrefixes`` is advertised.
    - ``MinRtrAdvInterval`` / ``MaxRtrAdvInterval`` in seconds.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    managed_flag: Optional[int] = Field(None, alias="AdvManagedFlag")
    other_config_flag: Optional[int] = Field(None, alias="AdvOtherConfigFlag")
    prefix_auto: Optional[int] = Field(None, alias="IsPrefixAutoMode")
    manual_prefixes: Optional[str] = Field(None, alias="ManualPrefixes")
    min_interval: Optional[int] = Field(None, alias="MinRtrAdvInterval")
    max_interval: Optional[int] = Field(None, alias="MaxRtrAdvInterval")
    adv_mtu_enabled: Optional[int] = Field(None, alias="AdvLinkMTUEnable")
    adv_mtu: Optional[int] = Field(None, alias="AdvLinkMTU")
    preferred_router_flag: Optional[int] = Field(None, alias="AdvPreferredRouterFlag")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class DhcpConfig(BaseModel):
    """LAN DHCPv4 server configuration (OBJ_Br0AndDhcpsHosCfg_ID, single row).

    ``IPAddr`` is the modem's own LAN IP (the gateway handed out to clients).
    ``MinAddress`` / ``MaxAddress`` define the dynamic pool.
    ``DNSServer1`` / ``DNSServer2`` are the DNS servers pushed to clients;
    ``DnsServerSource`` is the source mode (manual vs. inherited from WAN).
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="ServerEnable")
    router_ip: Optional[str] = Field(None, alias="IPAddr")
    subnet_mask: Optional[str] = Field(None, alias="SubnetMask")
    pool_min: Optional[str] = Field(None, alias="MinAddress")
    pool_max: Optional[str] = Field(None, alias="MaxAddress")
    lease_time: Optional[int] = Field(None, alias="LeaseTime")
    dns_source: Optional[int] = Field(None, alias="DnsServerSource")
    dns1: Optional[str] = Field(None, alias="DNSServer1")
    dns2: Optional[str] = Field(None, alias="DNSServer2")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class DhcpBinding(BaseModel):
    """A single DHCPv4 reservation (OBJ_DHCPBIND_ID/Instance).

    These are static "this MAC always gets this IP" bindings configured
    in the LAN DHCP page, distinct from live leases (which `clients`
    surfaces via OBJ_DHCPHOSTINFO_ID).
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    name: Optional[str] = Field(None, alias="Name")
    ip_address: Optional[str] = Field(None, alias="IPAddr")
    mac: Optional[str] = Field(None, alias="MACAddr")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class EthInterface(BaseModel):
    """A single ethernet interface (OBJ_ETH_ID/Instance).

    Used both for the 4 LAN ports (IGD.LD1.ETH1..ETH4, with ``AliasName``
    = LAN1..LAN4) and for the eth-WAN port (IGD.WD3.ETH5, which has no
    ``AliasName`` and exposes a few extra optical/SFP-style fields like
    ``singleStatus`` / ``singleRXStrength`` that the modem uses when the
    WAN connector is wired to an SFP cage on similar TIM gear).

    ``LinkSpeed`` is in Mbps (``1000`` = gigabit, ``10`` = idle/no-link).
    ``BytesReceived`` / ``BytesSent`` are 64-bit byte counters.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    alias: Optional[str] = Field(None, alias="AliasName")
    status: Optional[str] = Field(None, alias="Status")
    link_speed: Optional[int] = Field(None, alias="LinkSpeed")
    link_duplex: Optional[str] = Field(None, alias="LinkDuplex")
    mac: Optional[str] = Field(None, alias="MACAddress")
    bytes_rx: Optional[int] = Field(None, alias="BytesReceived")
    bytes_tx: Optional[int] = Field(None, alias="BytesSent")
    packets_rx: Optional[int] = Field(None, alias="PacketsReceived")
    packets_tx: Optional[int] = Field(None, alias="PacketsSent")
    single_status: Optional[str] = Field(None, alias="singleStatus")
    single_rx_strength: Optional[str] = Field(None, alias="singleRXStrength")
    single_tx_strength: Optional[str] = Field(None, alias="singleTXStrength")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class Ddns(BaseModel):
    """DDNS client state (OBJ_DDNSCLIENT_ID/Instance, single client IGD.DDNSC1).

    ``Service`` is the provider tag chosen in the UI (e.g. ``dyndns``,
    ``no-ip``, ``zte``); empty when DDNS is disabled and never configured.
    ``Status`` is the modem's textual state (``Disconnected``, ``Connected``,
    ``ConnectFailed``, ...). ``Hash`` and ``Password`` are intentionally
    not exposed even though the endpoint emits an ``<encode>Password</encode>``
    hint.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    service: Optional[str] = Field(None, alias="Service")
    username: Optional[str] = Field(None, alias="Username")
    domain: Optional[str] = Field(None, alias="DomainName")
    status: Optional[str] = Field(None, alias="Status")
    last_error: Optional[str] = Field(None, alias="LastError")
    user_type: Optional[int] = Field(None, alias="UserType")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class ArpEntry(BaseModel):
    """A single ARP cache entry (OBJ_GETARPINST_ID/Instance).

    No ``_InstID`` is reported by AGZHM 1.4.4. ``Status`` is the raw
    numeric value returned by the modem (semantics not documented; on the
    web UI it is rendered with a localized string, so it is left as int
    to avoid an unverified mapping).
    """

    dest_ip: Optional[str] = Field(None, alias="DestIP")
    mac: Optional[str] = Field(None, alias="MACAddr")
    interface: Optional[str] = Field(None, alias="Interface")
    status: Optional[int] = Field(None, alias="Status")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class MacTableEntry(BaseModel):
    """A single L2 forwarding-table entry (OBJ_GETMACINST_ID/Instance).

    Each row is what the modem's bridge currently sees on a physical
    LAN/WLAN port. ``LanName`` is the bridge interface (e.g. ``LAN1``,
    ``SSID1``); ``AgingTm`` is the time in seconds since the MAC was
    last refreshed in the FDB.
    """

    id: Optional[str] = Field(None, alias="_InstID")
    mac: Optional[str] = Field(None, alias="MACAddr")
    vlan_id: Optional[int] = Field(None, alias="VlanID")
    interface: Optional[str] = Field(None, alias="LanName")
    # AGZHM 1.4.4 reports AgingTm as a float-string in seconds (e.g. "271.77").
    aging_time: Optional[float] = Field(None, alias="AgingTm")
    model_config = {"populate_by_name": True, "extra": "ignore"}


class PortForwardingRule(BaseModel):
    """A single port-forwarding rule (OBJ_FWPM_ID).

    Notes from the H388X firmware:
    - ``Protocol`` is one of ``TCP``, ``UDP``, ``BOTH``.
    - ``RemoteHost`` / ``RemoteHostEndRange`` ``0.0.0.0`` means "any source".
    - ``ExternalPort`` and ``ExternalPortEndRange`` define the WAN port range
      (``EndRange`` equals ``Port`` for single-port rules).
    """

    id: Optional[str] = Field(None, alias="_OBJ_InstID")
    enabled: Optional[int] = Field(None, alias="Enable")
    description: Optional[str] = Field(None, alias="Description")
    protocol: Optional[str] = Field(None, alias="Protocol")
    external_port: Optional[int] = Field(None, alias="ExternalPort")
    external_port_end: Optional[int] = Field(None, alias="ExternalPortEndRange")
    internal_client: Optional[str] = Field(None, alias="InternalClient")
    internal_port: Optional[int] = Field(None, alias="InternalPort")
    remote_host: Optional[str] = Field(None, alias="RemoteHost")
    remote_host_end: Optional[str] = Field(None, alias="RemoteHostEndRange")
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
