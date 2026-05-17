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

    NO_CACHE = {"Cache-Control": "no-cache"}

    def __init__(self, ip: str = "192.168.1.1", username: str = "admin", password: str = ""):
        self.base_url = f"http://{ip}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
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
