import re


from .api_firewall import FirewallMixin
from .api_lan import LanMixin
from .api_services import ServicesMixin
from .api_system import SystemMixin
from .api_wan import WanDslMixin
from .api_wifi import WifiMixin
from .transport import H388XTransport, _default_cache_dir as _default_cache_dir


class ZTEH388XAPI(
    H388XTransport,
    WanDslMixin,
    LanMixin,
    WifiMixin,
    FirewallMixin,
    ServicesMixin,
    SystemMixin,
):
    """
    Minimal client for the ZTE H388X (TIM HUB+, firmware AGZHM_*).

    Auth flow (reverse engineered from masoneff3/ha_zteh388x):
        1. GET /?_type=loginData&_tag=login_entry  -> JSON { sess_token }
        2. GET /?_type=loginData&_tag=login_token  -> XML <root>SALT</root>
        3. POST /?_type=loginData&_tag=login_entry with
              Username, Password=sha256(password+salt), _sessionTOKEN, action=login
           -> the modem sets the SID cookie on the session jar.
    """

    DSL_INIT_URL = "/?_type=menuView&_tag=dslWanStatus"
    DSL_STATS_URL = "/?_type=menuData&_tag=dsl_interface_status_lua.lua"
    WAN_INTERNET_URL = (
        "/?_type=menuData&_tag=wan_internet_lua.lua&TypeUplink=1&pageType=1"
    )
    DEV_INFO_VIEW_URL = "/?_type=menuView&_tag=statusMgr&Menu3Location=0"
    DEV_INFO_URL = "/?_type=menuData&_tag=devmgr_statusmgr_lua.lua"
    REBOOT_VIEW_URL = "/?_type=menuView&_tag=rebootAndReset&Menu3Location=0"
    REBOOT_URL = "/?_type=menuData&_tag=devmgr_restartmgr_lua.lua"
    DHCP_VIEW_URL = "/?_type=menuView&_tag=lanMgrIpv4&Menu3Location=0"
    DHCP_LEASES_URL = "/?_type=menuData&_tag=dhcp4s_dhcphostinfo_m.lua"
    LOCALNET_VIEW_URL = "/?_type=menuView&_tag=localNetStatus&Menu3Location=0"
    LAN_CLIENTS_URL = "/?_type=menuData&_tag=accessdev_landevs_lua.lua"
    WIFI_CLIENTS_URL = "/?_type=menuData&_tag=accessdev_ssiddev_lua.lua"

    # --- Wi-Fi (group A: read-only) -------------------------------------
    WLAN_BASIC_VIEW_URL = "/?_type=menuView&_tag=wlanBasic&Menu3Location=0"
    WLAN_RADIOS_URL = "/?_type=menuData&_tag=wlan_basiconoff_lua.lua"
    WLAN_APS_URL = "/?_type=menuData&_tag=wlan_status_lua.lua"

    # --- Firewall (group A: read-only) ----------------------------------
    FIREWALL_VIEW_URL = "/?_type=menuView&_tag=firewall&Menu3Location=0"
    FIREWALL_LEVEL_URL = "/?_type=menuData&_tag=firewall_config_lua.lua"
    FIREWALL_DOS_URL = "/?_type=menuData&_tag=firewall_dos_lua.lua"
    FILTER_CRITERIA_VIEW_URL = "/?_type=menuView&_tag=filterCriteria&Menu3Location=0"
    FIREWALL_FILTER_GLOBAL_URL = "/?_type=menuData&_tag=firewall_filterglobal_m.lua"
    DMZ_VIEW_URL = "/?_type=menuView&_tag=dmzMenu&Menu3Location=0"
    FIREWALL_DMZ_URL = "/?_type=menuData&_tag=firewall_dmz_m.lua"
    PORT_FORWARDING_VIEW_URL = (
        "/?_type=menuView&_tag=portForwardingMenu&Menu3Location=0"
    )
    PORT_FORWARDING_URL = "/?_type=menuData&_tag=firewall_portforwarding_m.lua"

    # --- DNS (group A: read-only) ---------------------------------------
    DNS_VIEW_URL = "/?_type=menuView&_tag=dns&Menu3Location=0"
    DNS_LOCAL_URL = "/?_type=menuData&_tag=dns_localdns_lua.lua"
    DNS_HOSTNAMES_URL = "/?_type=menuData&_tag=dns_hostname_lua.lua"

    # --- MAC table (group A: read-only) ---------------------------------
    MAC_TABLE_VIEW_URL = "/?_type=menuView&_tag=macTable&Menu3Location=0"
    MAC_TABLE_URL = "/?_type=menuData&_tag=macinfo_mactable_lua.lua"

    # --- ARP table (group B: read-only) ---------------------------------
    ARP_VIEW_URL = "/?_type=menuView&_tag=arpTable&Menu3Location=0"
    ARP_URL = "/?_type=menuData&_tag=arp_arptable_lua.lua"

    # --- DDNS (group B: read-only) --------------------------------------
    DDNS_VIEW_URL = "/?_type=menuView&_tag=ddns&Menu3Location=0"
    DDNS_URL = "/?_type=menuData&_tag=ddns_lua.lua"

    # --- Ethernet ports (group B: read-only) ----------------------------
    # LAN port list lives behind the local-network status view.
    ETH_LAN_URL = "/?_type=menuData&_tag=eth_lanstatus_lua.lua"
    # The eth-WAN port (IGD.WD3.ETH5, optical/SFP-style WAN uplink) lives
    # behind its own view.
    ETH_WAN_VIEW_URL = "/?_type=menuView&_tag=ethWanStatus&Menu3Location=0"
    ETH_WAN_URL = "/?_type=menuData&_tag=eth_interface_status_lua.lua"

    # --- DHCPv4 server (group B: read-only) -----------------------------
    DHCP_CONFIG_URL = "/?_type=menuData&_tag=dhcp4s_dhcpbasiccfg_lua.lua"
    DHCP_BINDINGS_URL = "/?_type=menuData&_tag=dhcp4s_dhcpbinding_m.lua"

    # --- DHCPv6 + RA (group B: read-only) -------------------------------
    DHCP6_VIEW_URL = "/?_type=menuView&_tag=lanMgrIpv6&Menu3Location=0"
    DHCP6_SERVER_URL = "/?_type=menuData&_tag=dhcp6s_dhcpserver_lua.lua"
    DHCP6_HOSTS_URL = "/?_type=menuData&_tag=dhcp6s_hostinfo_lua.lua"
    RA_URL = "/?_type=menuData&_tag=ra_raservice_lua.lua"

    # --- VoIP (group C: read-only) --------------------------------------
    VOIP_STATUS_VIEW_URL = "/?_type=menuView&_tag=voipStatus&Menu3Location=0"
    VOIP_STATUS_URL = "/?_type=menuData&_tag=voip_voipstatus_m.lua"
    VOIP_FLEX_BIND_VIEW_URL = "/?_type=menuView&_tag=flexibleBind&Menu3Location=0"
    VOIP_FLEX_BIND_URL = "/?_type=menuData&_tag=voip_flexiblebinding_lua.lua"

    # --- UPnP (group C: read-only) --------------------------------------
    UPNP_VIEW_URL = "/?_type=menuView&_tag=upnp&Menu3Location=0"
    UPNP_CONFIG_URL = "/?_type=menuData&_tag=upnp_upnp_m.lua"
    UPNP_PORTS_URL = "/?_type=menuData&_tag=upnp_portmapping_lua.lua"

    # --- DLNA / DMS (group C: read-only) --------------------------------
    DMS_VIEW_URL = "/?_type=menuView&_tag=dms&Menu3Location=0"
    DMS_URL = "/?_type=menuData&_tag=dms_dms_lua.lua"

    # --- FTP server (group C: read-only) --------------------------------
    FTP_VIEW_URL = "/?_type=menuView&_tag=ftp&Menu3Location=0"
    FTP_URL = "/?_type=menuData&_tag=ftp_ftpserver_m.lua"

    # --- NanoCDN status (group C: read-only) ----------------------------
    NANOCDN_VIEW_URL = "/?_type=menuView&_tag=mabrNanoCDN&Menu3Location=0"
    NANOCDN_URL = "/?_type=menuData&_tag=nanocdn_lua.lua"

    # --- Mesh topology (group E: read-only) -----------------------------
    TOPOLOGY_VIEW_URL = "/?_type=menuView&_tag=mmTopology&Menu3Location=0"
    TOPOLOGY_URL = "/?_type=menuData&_tag=topo_lua.lua"

    # --- System / admin (group F: read-only) ----------------------------
    ADMIN_USERS_VIEW_URL = "/?_type=menuView&_tag=accountMgr&Menu3Location=0"
    ADMIN_USERS_URL = "/?_type=menuData&_tag=devauth_accountmgr_lua.lua"
    WEB_TIMEOUT_VIEW_URL = "/?_type=menuView&_tag=loginTimeoutMgr&Menu3Location=0"
    WEB_TIMEOUT_URL = "/?_type=menuData&_tag=web_login_timeout_lua.lua"
    MOBILE_WAN_VIEW_URL = "/?_type=menuView&_tag=wan3gStatus&Menu3Location=0"
    MOBILE_WAN_URL = "/?_type=menuData&_tag=wwan_mobile_status_lua.lua"
    PUBLIC_LAN_VIEW_URL = "/?_type=menuView&_tag=localNetStatus&Menu3Location=0"
    PUBLIC_LAN_URL = "/?_type=menuData&_tag=publiclan_status_lua.lua"

    # --- DSL physical line status (group G) -----------------------------
    DSL_IF_VIEW_URL = "/?_type=menuView&_tag=dslWanStatus&Menu3Location=0"
    DSL_IF_URL = "/?_type=menuData&_tag=dsl_interface_status_lua.lua"

    # --- VoIP extra (group M) -------------------------------------------
    SIP_MEDIA_VIEW_URL = "/?_type=menuView&_tag=sipMedia&Menu3Location=0"
    SIP_MEDIA_URL = "/?_type=menuData&_tag=voip_sipmedia_lua.lua"
    VOIP_POS_VIEW_URL = "/?_type=menuView&_tag=posOnoff&Menu3Location=0"
    VOIP_POS_URL = "/?_type=menuData&_tag=voip_posonoff_lua.lua"

    # --- SNTP / time (hidden endpoint, read-only) -----------------------
    # ``hiddenData`` endpoints don't need a menuView arming step. The
    # SNTP page is reachable directly with a plain authenticated GET.
    SNTP_URL = "/?_type=hiddenData&_tag=sntp_data"

    # --- USB devices (group N) ------------------------------------------
    # USB list shares the LAN status parent view (``localNetStatus``).
    USB_DEVS_URL = "/?_type=menuData&_tag=usb_usbdevs_lua.lua"

    # --- Wi-Fi SSID full config (group L) -------------------------------
    # Same OBJ root as the SSID status view (``wlan_status_lua.lua``),
    # but the ``wlanBasic`` parent view exposes the configuration page
    # which adds ``ESSIDHideEnable`` and ``MaxUserNum``.
    WLAN_SSID_CONF_URL = "/?_type=menuData&_tag=wlan_sssidconf_lua.lua"

    # --- IPv6 prefix + EDNS0 (group J) ----------------------------------
    EDNS0_VIEW_URL = "/?_type=menuView&_tag=smEdns0&Menu3Location=0"
    EDNS0_URL = "/?_type=menuData&_tag=edns0_lua.lua"
    IPV6_PREFIX_VIEW_URL = "/?_type=menuView&_tag=lanMgrIpv6&Menu3Location=0"
    IPV6_PREFIX_POOL_URL = "/?_type=menuData&_tag=prefix_prefixpool_lua.lua"
    IPV6_STATIC_PREFIX_URL = "/?_type=menuData&_tag=prefix_staticprefix_lua.lua"

    # --- Firewall extra rules (group H) ---------------------------------
    # ``filterCriteria`` view (already declared above) arms both IP-filter
    # rules and the URL-filter rule list, plus the IP-filter priority
    # slot. ``parentCtrl`` is its own page. All four lists are empty by
    # default on TIM Hub+ — they populate only when the user adds rules
    # in the web UI.
    FW_IPFILTER_URL = "/?_type=menuData&_tag=firewall_ipfilter_m.lua"
    FW_IPFILTER_PRIORITY_URL = (
        "/?_type=menuData&_tag=firewall_ipfilter_priority_lua.lua"
    )
    FW_URLFILTER_URL = "/?_type=menuData&_tag=firewall_urlfilter_m.lua"
    PARENT_CTRL_VIEW_URL = "/?_type=menuView&_tag=parentCtrl&Menu3Location=0"
    PARENT_CTRL_URL = "/?_type=menuData&_tag=firewall_parentctrl_lua.lua"

    # --- Wi-Fi advanced (group D: read-only) ----------------------------
    # wlanBasic is already used as WLAN_BASIC_VIEW_URL for the radios list;
    # the same parent view also arms the advanced radio config endpoint.
    WLAN_ADV_RADIOS_URL = "/?_type=menuData&_tag=wlan_basicadconf_lua.lua"
    WLAN_ADVANCED_VIEW_URL = "/?_type=menuView&_tag=wlanAdvanced&Menu3Location=0"
    WLAN_MAC_FILTER_POLICY_URL = "/?_type=menuData&_tag=wlan_macfilteraclpolicy_lua.lua"
    WLAN_MAC_FILTER_RULES_URL = "/?_type=menuData&_tag=wlan_macfilterrule_m.lua"
    WLAN_SCHEDULE_VIEW_URL = "/?_type=menuView&_tag=WlanWiFiSchedule&Menu3Location=0"
    WLAN_SCHEDULE_URL = "/?_type=menuData&_tag=wlan_wifi_schedule_lua.lua"
    WLAN_BSS_STEERING_VIEW_URL = (
        "/?_type=menuView&_tag=wlanBssSteeringOnoff&Menu3Location=0"
    )
    WLAN_BSS_STEERING_URL = "/?_type=menuData&_tag=wlan_BssSteeringOnoff_lua.lua"

    # --- User config backup (read-only export of the whole modem config) -
    # The "Backup configurazione utente" page (``usrCfgMgr`` view) renders
    # a per-render ``TOKEN_DOWNLOAD`` and a multipart form that POSTs to
    # ``do_download_usercfg.lua`` to stream ``config.bin``. The view only
    # arms (returns the real template instead of the "fake 404" reload
    # page) right after a fresh login, so the backup flow forces a relogin
    # if the token isn't present.
    USRCFG_VIEW_URL = "/?_type=menuView&_tag=usrCfgMgr&Menu3Location=0"
    CONFIG_DOWNLOAD_URL = "/?_type=menuData&_tag=do_download_usercfg.lua"

    # --- Network diagnostics (ping / traceroute run *from* the modem) -----
    # TR-069-style async diagnostics: POST ``IF_ACTION=<PingDiagnosis|
    # TraceRouteDiagnosis>`` to start, then poll the same endpoint until
    # the result field is populated. Non-mutating (no config change).
    NETDIAG_VIEW_URL = "/?_type=menuView&_tag=networkDiag&Menu3Location=0"
    PING_URL = "/?_type=menuData&_tag=networkdiag_ping_lua.lua"
    TRACEROUTE_URL = "/?_type=menuData&_tag=networkdiag_traceroute_lua.lua"

    # ------------------------------------------------------------- cache I/O

    # ------------------------------------------------------------------ login

    # ----------------------------------------------------------------- helpers

    # ---------------------------------------------------------------- DSL stats

    # --------------------------------------------------------------- device info

    # --------------------------------------------------------------------- WAN

    # ----------------------------------------------------------------- clients

    # ---------------------------------------------------------------- Wi-Fi

    # ------------------------------------------------------------- Firewall

    # OBJ_FWPM_ID exposes its ParaNames prefixed with the root in the GET
    # response (e.g. ``OBJ_FWPM_ID.Enable``). The WebUI's ``dataPost``
    # mirrors that on the POST side: every form input id keeps the prefix,
    # so we have to do the same here or the modem silently drops the row.
    _PFWD_PREFIX = "OBJ_FWPM_ID"

    # --- DHCPv4 static reservations write actions ---
    # Same prefixed-ParaName convention as port-forwarding (the form
    # template renders <input id="OBJ_DHCPBIND_ID.Name:DHCPStaticRule">
    # and the colonStripping rule strips the suffix on submit).
    _DHCP_BIND_PREFIX = "OBJ_DHCPBIND_ID"

    # ------------------------------------------------------------------- DNS

    # ------------------------------------------------------------- MAC table

    # ------------------------------------------------------------- ARP table

    # ------------------------------------------------------------------- DDNS

    # -------------------------------------------------------- Ethernet ports

    # --------------------------------------------------------- DHCPv4 server

    # ----------------------------------------------------------- DHCPv6 + RA

    # -------------------------------------------------------------------- VoIP

    # -------------------------------------------------------------------- UPnP

    # ---------------------------------------------------------- DLNA / DMS

    # ------------------------------------------------------------ FTP server

    # -------------------------------------------------- NanoCDN (TIM IPTV)

    # ----------------------------------------------------- Wi-Fi advanced

    # --------------------------------------------------------- Mesh topology

    # --------------------------------------------------- System / admin (F)

    # --- Firewall URL-filter write actions ---
    # Same prefixed-ParaName + Apply/-1 convention. The filterCriteria
    # view renders <input id="OBJ_FWURL_ID.Name:URLFilter"> /
    # ".Url:URLFilter"; colonStripping() drops the suffix on submit.
    # Client-side validation: Name 1..32 ASCII, Url 1..128 (url format).
    _FWURL_PREFIX = "OBJ_FWURL_ID"

    # --- Firewall IP-filter write actions ---
    # filterCriteria view renders many <input id="OBJ_FWIP_ID.X:IPFilter">.
    # Server-side required: Name (1..32 ASCII), FilterIndex (1..20),
    # Protocol (1..255). ``S_Protocol`` is a UI-only helper (not stored;
    # comes back empty on read), but the WebUI still submits it so we
    # mirror that. ``FilterTarget`` default is 1=allow in the form, which
    # is the safe default (an allow rule never blocks existing traffic).
    _FWIP_PREFIX = "OBJ_FWIP_ID"
    _IP_PROTO_MAP = {"ICMP": "1", "TCP": "6", "UDP": "17"}

    # ------------------------------------------------------------------ reboot

    # -------------------------------------------------------- config backup

    _TOKEN_DOWNLOAD_RE = re.compile(r'id="TOKEN_DOWNLOAD"[^>]*value="([^"]*)"')

    # ---------------------------------------------------- network diagnostics

    # --------------------------------------------------------- close / logout
