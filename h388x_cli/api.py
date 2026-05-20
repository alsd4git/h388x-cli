import hashlib
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List

import requests


class ZTEH388XAPI:
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
    WAN_INTERNET_URL = "/?_type=menuData&_tag=wan_internet_lua.lua&TypeUplink=1&pageType=1"
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
    PORT_FORWARDING_VIEW_URL = "/?_type=menuView&_tag=portForwardingMenu&Menu3Location=0"
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

    # --- Wi-Fi advanced (group D: read-only) ----------------------------
    # wlanBasic is already used as WLAN_BASIC_VIEW_URL for the radios list;
    # the same parent view also arms the advanced radio config endpoint.
    WLAN_ADV_RADIOS_URL = "/?_type=menuData&_tag=wlan_basicadconf_lua.lua"
    WLAN_ADVANCED_VIEW_URL = "/?_type=menuView&_tag=wlanAdvanced&Menu3Location=0"
    WLAN_MAC_FILTER_POLICY_URL = "/?_type=menuData&_tag=wlan_macfilteraclpolicy_lua.lua"
    WLAN_MAC_FILTER_RULES_URL = "/?_type=menuData&_tag=wlan_macfilterrule_m.lua"
    WLAN_SCHEDULE_VIEW_URL = "/?_type=menuView&_tag=WlanWiFiSchedule&Menu3Location=0"
    WLAN_SCHEDULE_URL = "/?_type=menuData&_tag=wlan_wifi_schedule_lua.lua"
    WLAN_BSS_STEERING_VIEW_URL = "/?_type=menuView&_tag=wlanBssSteeringOnoff&Menu3Location=0"
    WLAN_BSS_STEERING_URL = "/?_type=menuData&_tag=wlan_BssSteeringOnoff_lua.lua"

    NO_CACHE = {"Cache-Control": "no-cache"}

    def __init__(
        self,
        host: str = "192.168.1.1",
        username: str = "admin",
        password: str = "",
        verify_tls: bool = True,
    ):
        """
        ``host`` can be a bare IP/hostname (``192.168.1.1``,
        ``modem.example.com``) or a full URL with explicit scheme
        (``http://192.168.1.1``, ``https://modem.example.com:8443``).
        When the scheme is omitted, ``http://`` is assumed; any trailing
        slash is stripped so ``base_url`` is safe to concatenate with
        absolute paths.
        """
        host = (host or "").strip()
        if "://" in host:
            self.base_url = host.rstrip("/")
        else:
            self.base_url = f"http://{host}".rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = verify_tls
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            # The modem's CSRF check refuses menuData requests whose Origin
            # / Referer doesn't match its own host. On direct LAN access this
            # is set automatically by the browser; over HTTPS reverse proxies
            # (or anywhere the requests session isn't a real browser) we
            # have to set them explicitly or every menuData returns
            # SessionTimeout even with a valid SID cookie.
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        })
        self.session_token: Optional[str] = None

    # ------------------------------------------------------------------ login

    def login(self) -> bool:
        try:
            self.session.get(f"{self.base_url}/", timeout=8)

            r1 = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_entry", timeout=8
            )
            self.session_token = r1.json().get("sess_token")
            if not self.session_token:
                return False

            r2 = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_token", timeout=8
            )
            try:
                salt = (ET.fromstring(r2.text).text or "").strip()
            except ET.ParseError:
                m = re.search(r"<[^>]+>(.*?)</[^>]+>", r2.text)
                salt = m.group(1).strip() if m else ""
            if not salt:
                return False

            hashed_pw = hashlib.sha256(f"{self.password}{salt}".encode()).hexdigest()
            payload = {
                "Username": self.username,
                "Password": hashed_pw,
                "_sessionTOKEN": self.session_token,
                "action": "login",
            }
            r3 = self.session.post(
                f"{self.base_url}/?_type=loginData&_tag=login_entry",
                data=payload,
                timeout=8,
            )

            try:
                new_token = r3.json().get("sess_token")
                if new_token:
                    self.session_token = new_token
            except ValueError:
                pass

            return self.session.cookies.get("SID") is not None
        except requests.RequestException:
            return False

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _strip_prefix(name: str) -> str:
        # Some endpoints (e.g. dhcp4s_dhcphostinfo_m.lua) prefix every ParaName
        # with the root element name, e.g. ``OBJ_DHCPHOSTINFO_ID.IPAddr``.
        # Normalize to the bare field name.
        if "." in name:
            return name.rsplit(".", 1)[-1]
        return name

    @classmethod
    def _parse_instances(cls, xml_text: str, root_element: str) -> List[Dict[str, str]]:
        try:
            tree = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        out: List[Dict[str, str]] = []
        for instance in tree.findall(f".//{root_element}/Instance"):
            names = [cls._strip_prefix(n.text or "") for n in instance.findall("ParaName")]
            values = [v.text or "" for v in instance.findall("ParaValue")]
            out.append(dict(zip(names, values)))
        return out

    @staticmethod
    def _is_session_expired(text: str) -> bool:
        return "SessionTimeout" in text

    def _menudata(
        self,
        view_url: str,
        data_url: str,
        root_element: str,
        retry: bool = True,
    ) -> List[Dict[str, str]]:
        """Generic menuView + menuData fetcher with auto re-login on timeout."""
        try:
            self.session.get(
                f"{self.base_url}{view_url}", headers=self.NO_CACHE, timeout=8
            )
            resp = self.session.get(
                f"{self.base_url}{data_url}", headers=self.NO_CACHE, timeout=8
            )

            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata(view_url, data_url, root_element, retry=False)
                return []

            return self._parse_instances(resp.text, root_element)
        except requests.RequestException:
            return []

    def _menudata_multi(
        self,
        view_url: str,
        data_url: str,
        root_elements: List[str],
        retry: bool = True,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Like ``_menudata`` but parses multiple root elements from a single
        response. Returns ``{root: [instances]}`` so a single HTTP roundtrip
        can populate sibling collections (e.g. voipstatus exposes both
        OBJ_VOIPVPLINE_ID and OBJ_VOIPSIPLINE_ID in the same payload)."""
        try:
            self.session.get(
                f"{self.base_url}{view_url}", headers=self.NO_CACHE, timeout=8
            )
            resp = self.session.get(
                f"{self.base_url}{data_url}", headers=self.NO_CACHE, timeout=8
            )

            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata_multi(view_url, data_url, root_elements, retry=False)
                return {root: [] for root in root_elements}

            return {
                root: self._parse_instances(resp.text, root)
                for root in root_elements
            }
        except requests.RequestException:
            return {root: [] for root in root_elements}

    # ---------------------------------------------------------------- DSL stats

    def get_dsl_stats(self, retry: bool = True) -> Dict[str, str]:
        instances = self._menudata(
            self.DSL_INIT_URL, self.DSL_STATS_URL, "OBJ_DSLINTERFACE_ID", retry
        )
        return instances[0] if instances else {}

    # --------------------------------------------------------------- device info

    def get_device_info(self, retry: bool = True) -> Dict[str, str]:
        instances = self._menudata(
            self.DEV_INFO_VIEW_URL, self.DEV_INFO_URL, "OBJ_DEVINFO_ID", retry
        )
        return instances[0] if instances else {}

    # --------------------------------------------------------------------- WAN

    def get_wan_connections(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return ALL WAN connections (INTERNET_VD/AD, IPTV_VD/AD, ...)."""
        return self._menudata(
            self.DSL_INIT_URL,
            "/?_type=menuData&_tag=wan_internet_lua.lua&TypeUplink=1&pageType=1",
            "ID_WAN_COMFIG",
            retry,
        )

    # ----------------------------------------------------------------- clients

    def get_dhcp_leases(self, retry: bool = True) -> List[Dict[str, str]]:
        return self._menudata(
            self.DHCP_VIEW_URL, self.DHCP_LEASES_URL, "OBJ_DHCPHOSTINFO_ID", retry
        )

    def get_lan_clients(self, retry: bool = True) -> List[Dict[str, str]]:
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.LAN_CLIENTS_URL, "OBJ_ACCESSDEV_ID", retry
        )

    def get_wifi_clients(self, retry: bool = True) -> List[Dict[str, str]]:
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.WIFI_CLIENTS_URL, "OBJ_ACCESSDEV_ID", retry
        )

    # ---------------------------------------------------------------- Wi-Fi

    def get_wifi_radios(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the two WLAN radios (2.4 GHz / 5 GHz) and their on/off state."""
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL, self.WLAN_RADIOS_URL,
            "OBJ_WLANSETTING_ID", retry,
        )

    def get_wifi_aps(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return all WLAN access points (SSIDs) with ESSID, auth and encryption."""
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.WLAN_APS_URL,
            "OBJ_WLANAP_ID", retry,
        )

    # ------------------------------------------------------------- Firewall

    def get_firewall_level(self, retry: bool = True) -> Dict[str, str]:
        """Return the active firewall level (Low/Middle/High) from OBJ_FWLEVEL_ID."""
        rows = self._menudata(
            self.FIREWALL_VIEW_URL, self.FIREWALL_LEVEL_URL,
            "OBJ_FWLEVEL_ID", retry,
        )
        return rows[0] if rows else {}

    def get_firewall_dos(self, retry: bool = True) -> Dict[str, str]:
        """Return DoS protection state (Enable + Threshold) from OBJ_FWDOS_ID."""
        rows = self._menudata(
            self.FIREWALL_VIEW_URL, self.FIREWALL_DOS_URL,
            "OBJ_FWDOS_ID", retry,
        )
        return rows[0] if rows else {}

    def get_url_filter_global(self, retry: bool = True) -> Dict[str, str]:
        """Return URL-filter master switch + target action from OBJ_FWBASE_ID."""
        rows = self._menudata(
            self.FILTER_CRITERIA_VIEW_URL, self.FIREWALL_FILTER_GLOBAL_URL,
            "OBJ_FWBASE_ID", retry,
        )
        return rows[0] if rows else {}

    def get_dmz(self, retry: bool = True) -> Dict[str, str]:
        """Return DMZ state (Enable + InternalClient) from OBJ_FWDMZ_ID."""
        rows = self._menudata(
            self.DMZ_VIEW_URL, self.FIREWALL_DMZ_URL,
            "OBJ_FWDMZ_ID", retry,
        )
        return rows[0] if rows else {}

    def get_port_forwarding_rules(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return all port-forwarding rules (OBJ_FWPM_ID) configured in NAT."""
        return self._menudata(
            self.PORT_FORWARDING_VIEW_URL, self.PORT_FORWARDING_URL,
            "OBJ_FWPM_ID", retry,
        )

    # ------------------------------------------------------------------- DNS

    def get_dns_local(self, retry: bool = True) -> Dict[str, str]:
        """Return the modem's own DNS server config (OBJ_DNS_ID)."""
        rows = self._menudata(
            self.DNS_VIEW_URL, self.DNS_LOCAL_URL,
            "OBJ_DNS_ID", retry,
        )
        return rows[0] if rows else {}

    def get_dns_hostnames(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the DNS-bound hostnames known to the modem (ALLDNSHOST)."""
        return self._menudata(
            self.DNS_VIEW_URL, self.DNS_HOSTNAMES_URL,
            "ALLDNSHOST", retry,
        )

    # ------------------------------------------------------------- MAC table

    def get_mac_table(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the L2 forwarding table (OBJ_GETMACINST_ID) seen by the bridge."""
        return self._menudata(
            self.MAC_TABLE_VIEW_URL, self.MAC_TABLE_URL,
            "OBJ_GETMACINST_ID", retry,
        )

    # ------------------------------------------------------------- ARP table

    def get_arp_table(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the modem's L3->L2 ARP cache (OBJ_GETARPINST_ID)."""
        return self._menudata(
            self.ARP_VIEW_URL, self.ARP_URL,
            "OBJ_GETARPINST_ID", retry,
        )

    # ------------------------------------------------------------------- DDNS

    def get_ddns(self, retry: bool = True) -> Dict[str, str]:
        """Return the DDNS client state (OBJ_DDNSCLIENT_ID, single instance)."""
        rows = self._menudata(
            self.DDNS_VIEW_URL, self.DDNS_URL,
            "OBJ_DDNSCLIENT_ID", retry,
        )
        return rows[0] if rows else {}

    # -------------------------------------------------------- Ethernet ports

    def get_eth_lan_ports(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the 4 LAN ethernet ports (OBJ_ETH_ID under localNetStatus)."""
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.ETH_LAN_URL,
            "OBJ_ETH_ID", retry,
        )

    def get_eth_wan_port(self, retry: bool = True) -> Dict[str, str]:
        """Return the eth-WAN uplink port (OBJ_ETH_ID under ethWanStatus)."""
        rows = self._menudata(
            self.ETH_WAN_VIEW_URL, self.ETH_WAN_URL,
            "OBJ_ETH_ID", retry,
        )
        return rows[0] if rows else {}

    # --------------------------------------------------------- DHCPv4 server

    def get_dhcp_config(self, retry: bool = True) -> Dict[str, str]:
        """Return the LAN DHCPv4 server config (OBJ_Br0AndDhcpsHosCfg_ID)."""
        rows = self._menudata(
            self.DHCP_VIEW_URL, self.DHCP_CONFIG_URL,
            "OBJ_Br0AndDhcpsHosCfg_ID", retry,
        )
        return rows[0] if rows else {}

    def get_dhcp_bindings(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return DHCPv4 reservations / static bindings (OBJ_DHCPBIND_ID)."""
        return self._menudata(
            self.DHCP_VIEW_URL, self.DHCP_BINDINGS_URL,
            "OBJ_DHCPBIND_ID", retry,
        )

    # ----------------------------------------------------------- DHCPv6 + RA

    def get_dhcp6_server(self, retry: bool = True) -> Dict[str, str]:
        """Return the LAN DHCPv6 server config (OBJ_DHCP6S_ID, single)."""
        rows = self._menudata(
            self.DHCP6_VIEW_URL, self.DHCP6_SERVER_URL,
            "OBJ_DHCP6S_ID", retry,
        )
        return rows[0] if rows else {}

    def get_dhcp6_hosts(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return DHCPv6 client bindings (OBJ_DHCP6C_ID); empty when IPv6 is off."""
        return self._menudata(
            self.DHCP6_VIEW_URL, self.DHCP6_HOSTS_URL,
            "OBJ_DHCP6C_ID", retry,
        )

    def get_ra(self, retry: bool = True) -> Dict[str, str]:
        """Return the IPv6 Router Advertisement service config (OBJ_RAIS_ID)."""
        rows = self._menudata(
            self.DHCP6_VIEW_URL, self.RA_URL,
            "OBJ_RAIS_ID", retry,
        )
        return rows[0] if rows else {}

    # -------------------------------------------------------------------- VoIP

    def get_voip_status(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return VoIP status: virtual lines + SIP lines from voipstatus.

        Single request, two roots:
        - ``OBJ_VOIPVPLINE_ID``: virtual lines (VL1, VL2) with ``IsOnline``.
        - ``OBJ_VOIPSIPLINE_ID``: SIP user-agent lines with ``PhoneName``,
          ``AuthUserName`` (phone number) and ``IsOnline``.
        """
        return self._menudata_multi(
            self.VOIP_STATUS_VIEW_URL, self.VOIP_STATUS_URL,
            ["OBJ_VOIPVPLINE_ID", "OBJ_VOIPSIPLINE_ID"],
            retry,
        )

    def get_voip_bindings(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return VoIP physical<->virtual line bindings (flexibleBind page).

        Single request, two roots:
        - ``OBJ_VOIPHOMELINE_ID``: per-port home-line config (``TermID``,
          ``OutByWanId``).
        - ``OBJ_VOIPVPLINE_ID``: per virtual line the comma-separated
          ``PhyList`` of bound physical jacks (e.g. ``0,1``).
        """
        return self._menudata_multi(
            self.VOIP_FLEX_BIND_VIEW_URL, self.VOIP_FLEX_BIND_URL,
            ["OBJ_VOIPHOMELINE_ID", "OBJ_VOIPVPLINE_ID"],
            retry,
        )

    # -------------------------------------------------------------------- UPnP

    def get_upnp_config(self, retry: bool = True) -> Dict[str, str]:
        """Return UPnP IGD master switch (OBJ_UPNPCONFIG_ID, single)."""
        rows = self._menudata(
            self.UPNP_VIEW_URL, self.UPNP_CONFIG_URL,
            "OBJ_UPNPCONFIG_ID", retry,
        )
        return rows[0] if rows else {}

    def get_upnp_portmappings(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return live UPnP port mappings (OBJ_UPNPPORTMAP_ID)."""
        return self._menudata(
            self.UPNP_VIEW_URL, self.UPNP_PORTS_URL,
            "OBJ_UPNPPORTMAP_ID", retry,
        )

    # ---------------------------------------------------------- DLNA / DMS

    def get_dms(self, retry: bool = True) -> Dict[str, str]:
        """Return the DLNA / DMS media-server config (OBJ_DMS_ID, single)."""
        rows = self._menudata(
            self.DMS_VIEW_URL, self.DMS_URL,
            "OBJ_DMS_ID", retry,
        )
        return rows[0] if rows else {}

    # ------------------------------------------------------------ FTP server

    def get_ftp(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return FTP server state: config (OBJ_FMFTPSERVERCFG_ID) + users (OBJ_FMFTPUSER_ID)."""
        return self._menudata_multi(
            self.FTP_VIEW_URL, self.FTP_URL,
            ["OBJ_FMFTPSERVERCFG_ID", "OBJ_FMFTPUSER_ID"],
            retry,
        )

    # -------------------------------------------------- NanoCDN (TIM IPTV)

    def get_nanocdn(self, retry: bool = True) -> Dict[str, str]:
        """Return NanoCDN runtime stats (OBJ_NANOCDN_STATUS_ID, single).

        NanoCDN is the TIM/IPTV multicast-to-unicast offload running on
        the modem; the page exposes ``Status``, current/min/max session
        count and multicast bitrate counters.
        """
        rows = self._menudata(
            self.NANOCDN_VIEW_URL, self.NANOCDN_URL,
            "OBJ_NANOCDN_STATUS_ID", retry,
        )
        return rows[0] if rows else {}

    # ----------------------------------------------------- Wi-Fi advanced

    def get_wifi_advanced(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return advanced per-radio settings (OBJ_WLANSETTING_ID, 2 rows).

        Same root element as ``get_wifi_radios()``, but the advanced
        endpoint exposes the channel/bandwidth/power/standard config
        instead of just the on/off state.
        """
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL, self.WLAN_ADV_RADIOS_URL,
            "OBJ_WLANSETTING_ID", retry,
        )

    def get_wifi_mac_filter(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return per-AP MAC filter policy + the (possibly empty) rule list.

        - ``OBJ_WLANACL_ID``: one row per AP (DEV.WIFI.AP1..AP8) with
          ``ACLPolicy`` = ``Disabled`` / ``Allow`` / ``Deny``.
        - ``OBJ_ACLCFG_ID``: zero or more MAC entries (empty when no
          ACL is configured).
        """
        # The MAC filter rules endpoint needs the wlanAdvanced view to
        # populate; the policy endpoint works under the same view too.
        return self._menudata_multi(
            self.WLAN_ADVANCED_VIEW_URL,
            self.WLAN_MAC_FILTER_POLICY_URL,
            ["OBJ_WLANACL_ID"],
            retry,
        ) | self._menudata_multi(
            self.WLAN_ADVANCED_VIEW_URL,
            self.WLAN_MAC_FILTER_RULES_URL,
            ["OBJ_ACLCFG_ID"],
            retry,
        )

    def get_wifi_schedule(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return Wi-Fi scheduling rules (OBJ_WLAN_WIFISCHEDULE)."""
        return self._menudata(
            self.WLAN_SCHEDULE_VIEW_URL, self.WLAN_SCHEDULE_URL,
            "OBJ_WLAN_WIFISCHEDULE", retry,
        )

    def get_band_steering(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return EasyMesh + band steering master switches (single page).

        Same response carries two siblings:
        - ``OBJ_EASYMESHENABLE_ID`` (EasyMesh root toggle)
        - ``OBJ_BANDSTEERENABLE_ID`` (band steering toggle)
        """
        return self._menudata_multi(
            self.WLAN_BSS_STEERING_VIEW_URL, self.WLAN_BSS_STEERING_URL,
            ["OBJ_EASYMESHENABLE_ID", "OBJ_BANDSTEERENABLE_ID"],
            retry,
        )

    # ------------------------------------------------------------------ reboot

    def reboot(self) -> bool:
        try:
            self.session.get(
                f"{self.base_url}{self.REBOOT_VIEW_URL}",
                headers=self.NO_CACHE,
                timeout=8,
            )
            self.session.get(
                f"{self.base_url}{self.REBOOT_URL}",
                headers=self.NO_CACHE,
                timeout=8,
            )
            payload = {
                "IF_ACTION": "Restart",
                "Btn_restart": "",
                "_sessionTOKEN": self.session_token or "",
            }
            resp = self.session.post(
                f"{self.base_url}{self.REBOOT_URL}",
                data=payload,
                headers=self.NO_CACHE,
                timeout=8,
            )
            return resp.status_code == 200 and "ERR" not in resp.text.upper()[:200]
        except requests.RequestException:
            return False

    # ------------------------------------------------------------------ logout

    def logout(self):
        if not self.session_token:
            self.session.close()
            return
        try:
            self.session.post(
                f"{self.base_url}/?_type=loginData&_tag=logout_entry",
                data={
                    "IF_LogOff": "1",
                    "_sessionTOKEN": self.session_token,
                },
                timeout=8,
            )
        except requests.RequestException:
            pass
        finally:
            self.session.cookies.clear()
            self.session.close()
