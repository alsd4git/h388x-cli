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
