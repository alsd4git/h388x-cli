import hashlib
import json as _json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests


def _default_cache_dir() -> Path:
    """Return the per-user cache directory for h388x-cli.

    Respects ``XDG_CACHE_HOME`` on Linux/macOS, falls back to
    ``~/.cache/h388x-cli``. The directory is created lazily by the
    caller on first write.
    """
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "h388x-cli"


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
    FW_IPFILTER_PRIORITY_URL = "/?_type=menuData&_tag=firewall_ipfilter_priority_lua.lua"
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
    WLAN_BSS_STEERING_VIEW_URL = "/?_type=menuView&_tag=wlanBssSteeringOnoff&Menu3Location=0"
    WLAN_BSS_STEERING_URL = "/?_type=menuData&_tag=wlan_BssSteeringOnoff_lua.lua"

    NO_CACHE = {"Cache-Control": "no-cache"}

    def __init__(
        self,
        host: str = "192.168.1.1",
        username: str = "admin",
        password: str = "",
        verify_tls: bool = True,
        cache_enabled: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        ``host`` can be a bare IP/hostname (``192.168.1.1``,
        ``modem.example.com``) or a full URL with explicit scheme
        (``http://192.168.1.1``, ``https://modem.example.com:8443``).
        When the scheme is omitted, ``http://`` is assumed; any trailing
        slash is stripped so ``base_url`` is safe to concatenate with
        absolute paths.

        When ``cache_enabled`` is true (default) a previously persisted
        SID cookie + session token for this ``(host, username)`` pair is
        loaded so subsequent CLI invocations skip the login handshake.
        Pass a custom ``cache_dir`` to override the default
        ``~/.cache/h388x-cli`` location (mostly useful for tests).
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

        self.cache_enabled = cache_enabled
        self._cache_dir = cache_dir or _default_cache_dir()
        if cache_enabled:
            self._load_cache()

    # ------------------------------------------------------------- cache I/O

    def _cache_path(self) -> Path:
        """Per-(host, user) cache file path under the cache directory."""
        key = hashlib.sha256(
            f"{self.base_url}|{self.username}".encode()
        ).hexdigest()[:16]
        return self._cache_dir / f"session-{key}.json"

    def _load_cache(self) -> bool:
        """Hydrate the requests session from a previously saved cache.

        Returns True when a usable cache was found and applied. Any
        IO/JSON error is swallowed — a missing or corrupted cache just
        forces a fresh login on next request.
        """
        path = self._cache_path()
        try:
            with path.open("r") as f:
                data = _json.load(f)
        except (OSError, ValueError):
            return False
        token = data.get("session_token")
        cookies = data.get("cookies") or {}
        if not token or not cookies:
            return False
        self.session_token = token
        # Set the restored cookies pinned to the modem host. Without an
        # explicit domain, requests defaults to ``domain=""`` and any
        # ``Set-Cookie`` reply from the server (which carries the request
        # host as its domain) would coexist as a duplicate — causing
        # ``CookieConflictError`` on ``cookies.get("SID")``.
        from urllib.parse import urlparse
        host = urlparse(self.base_url).hostname or ""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=host, path="/")
        return True

    def _save_cache(self) -> None:
        """Persist the live SID cookie + session token to disk (0600)."""
        if not self.cache_enabled or not self.session_token:
            return
        cookies = {c.name: c.value for c in self.session.cookies}
        if "SID" not in cookies:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        path = self._cache_path()
        payload = {
            "host": self.base_url,
            "user": self.username,
            "session_token": self.session_token,
            "cookies": cookies,
        }
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w") as f:
                _json.dump(payload, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _clear_cache(self) -> None:
        """Remove the on-disk cache for this (host, user) pair, if any."""
        try:
            self._cache_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _has_sid_cookie(self) -> bool:
        """True iff the session jar carries at least one ``SID`` cookie.

        Avoids ``CookieConflictError`` from ``RequestsCookieJar.get`` when
        more than one ``SID`` is present (different domain/path scopes).
        """
        return any(c.name == "SID" for c in self.session.cookies)

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

            ok = self._has_sid_cookie()
            if ok:
                self._save_cache()
            return ok
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

    def _refresh_session_token(self, body: str) -> None:
        """Update ``self.session_token`` from a POST response, if present.

        The modem rotates ``_sessionTOKEN`` on every successful write and
        embeds the new value in the response (either as the JSON field
        ``sess_token`` for ``loginData`` flows, or inside ``<sess_token>``
        in the standard XML response envelope). Silently no-op on any
        parse error — the next request will just trigger a SessionTimeout
        + re-login.
        """
        try:
            tok = _json.loads(body).get("sess_token")
            if tok:
                self.session_token = tok
                return
        except (ValueError, TypeError):
            pass
        m = re.search(r"<sess_token>([^<]+)</sess_token>", body)
        if m:
            self.session_token = m.group(1).strip()

    def _fetch_fresh_session_token(self) -> bool:
        """Pull the current ``_sessionTOKEN`` for our SID cookie.

        The modem rotates the CSRF token at every authenticated request,
        and ``login_entry`` (the same endpoint used during login) returns
        the live value as JSON ``{"sess_token": "..."}``. Called right
        before a write so we don't fight a stale token loaded from the
        session cache. Returns True on success.
        """
        try:
            r = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_entry",
                headers=self.NO_CACHE,
                timeout=8,
            )
            tok = r.json().get("sess_token")
            if tok:
                self.session_token = tok
                return True
        except (requests.RequestException, ValueError):
            pass
        return False

    def _post_action(
        self,
        view_url: str,
        data_url: str,
        action: str,
        fields: Dict[str, str],
        retry: bool = True,
    ) -> Tuple[bool, str]:
        """POST a write action against a menuData endpoint.

        Mirrors the WebUI's ``dataPost`` flow: arm the parent view,
        refresh the ``_sessionTOKEN`` from ``login_entry`` (the token
        rotates server-side at every request, so a value loaded from
        the session cache is almost always stale → ``IF_ERRORID=-1452
        "page expired"``), then POST ``IF_ACTION=<action>`` + the
        caller's ``fields`` + the rotating token. On ``SessionTimeout``
        re-logs in and replays the call once. Returns ``(ok, raw_body)``
        where ``ok`` means ``IF_ERRORSTR=SUCC``.
        """
        try:
            self.session.get(
                f"{self.base_url}{view_url}", headers=self.NO_CACHE, timeout=8
            )
            self._fetch_fresh_session_token()
            payload = {
                "IF_ACTION": action,
                **{k: ("" if v is None else str(v)) for k, v in fields.items()},
                "_sessionTOKEN": self.session_token or "",
            }
            resp = self.session.post(
                f"{self.base_url}{data_url}",
                data=payload,
                headers=self.NO_CACHE,
                timeout=10,
            )
            body = resp.text
            if self._is_session_expired(body):
                if retry and self.login():
                    return self._post_action(
                        view_url, data_url, action, fields, retry=False
                    )
                return False, body
            self._refresh_session_token(body)
            ok = (
                resp.status_code == 200
                and "<IF_ERRORSTR>SUCC</IF_ERRORSTR>" in body
            )
            return ok, body
        except requests.RequestException as e:
            return False, f"requests error: {e}"

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

    # OBJ_FWPM_ID exposes its ParaNames prefixed with the root in the GET
    # response (e.g. ``OBJ_FWPM_ID.Enable``). The WebUI's ``dataPost``
    # mirrors that on the POST side: every form input id keeps the prefix,
    # so we have to do the same here or the modem silently drops the row.
    _PFWD_PREFIX = "OBJ_FWPM_ID"

    @staticmethod
    def _prefixed(prefix: str, fields: Dict[str, str]) -> Dict[str, str]:
        return {f"{prefix}.{k}": v for k, v in fields.items()}

    def add_port_forwarding_rule(
        self,
        description: str,
        protocol: str,
        external_port: int,
        internal_client: str,
        internal_port: Optional[int] = None,
        external_port_end: Optional[int] = None,
        remote_host: str = "0.0.0.0",
        remote_host_end: str = "0.0.0.0",
        enable: bool = True,
    ) -> Tuple[bool, str]:
        """Create a new port-forwarding rule.

        Despite the name, the WebUI submits new instances with the same
        ``IF_ACTION=Apply`` that edits existing ones, distinguished only
        by ``_OBJ_InstID=-1`` (the magic "new" marker rendered as
        ``<input id='OBJ_FWPM_ID._OBJ_InstID' value='-1'>`` in the
        ``portForwardingMenu`` view). The server then assigns the real
        ``DEV.NAT.PtMapping<N>`` id.

        ``protocol`` must be one of ``TCP``, ``UDP``, ``BOTH``.
        ``internal_port`` defaults to ``external_port`` (single-port
        mapping) and ``external_port_end`` defaults to ``external_port``
        as well. ``remote_host`` ``0.0.0.0`` means "any source".
        """
        proto = protocol.upper()
        if proto not in {"TCP", "UDP", "BOTH"}:
            return False, f"protocol must be TCP/UDP/BOTH (got {protocol!r})"
        ext_end = external_port_end if external_port_end is not None else external_port
        int_port = internal_port if internal_port is not None else external_port
        fields = self._prefixed(self._PFWD_PREFIX, {
            "_OBJ_InstID": "-1",
            "Enable": "1" if enable else "0",
            "Description": description,
            "Protocol": proto,
            "ExternalPort": str(external_port),
            "ExternalPortEndRange": str(ext_end),
            "InternalClient": internal_client,
            "InternalPort": str(int_port),
            "RemoteHost": remote_host,
            "RemoteHostEndRange": remote_host_end,
        })
        return self._post_action(
            self.PORT_FORWARDING_VIEW_URL,
            self.PORT_FORWARDING_URL,
            action="Apply",
            fields=fields,
        )

    def del_port_forwarding_rule(self, inst_id: str) -> Tuple[bool, str]:
        """Delete a port-forwarding rule by its ``_OBJ_InstID``
        (e.g. ``DEV.NAT.PtMapping7``).

        Uses ``IF_ACTION=Delete`` to mirror the WebUI's ``Btn_delete``
        handler (``initial_button(buttonType="Delete", ...)`` in the
        modem's inline JS — NOT the shorter ``"Del"``).
        """
        fields = self._prefixed(self._PFWD_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.PORT_FORWARDING_VIEW_URL,
            self.PORT_FORWARDING_URL,
            action="Delete",
            fields=fields,
        )

    # --- DHCPv4 static reservations write actions ---
    # Same prefixed-ParaName convention as port-forwarding (the form
    # template renders <input id="OBJ_DHCPBIND_ID.Name:DHCPStaticRule">
    # and the colonStripping rule strips the suffix on submit).
    _DHCP_BIND_PREFIX = "OBJ_DHCPBIND_ID"

    def add_dhcp_reservation(
        self, mac: str, ip_address: str, name: str
    ) -> Tuple[bool, str]:
        """Create a static DHCPv4 lease (POST ``IF_ACTION=Apply`` +
        ``_OBJ_InstID=-1``).

        Active leases on other MACs are not disrupted; the modem only
        enforces the binding at the next renewal of the target client.
        """
        fields = self._prefixed(self._DHCP_BIND_PREFIX, {
            "_OBJ_InstID": "-1",
            "Name": name,
            "IPAddr": ip_address,
            "MACAddr": mac,
        })
        return self._post_action(
            self.DHCP_VIEW_URL, self.DHCP_BINDINGS_URL,
            action="Apply", fields=fields,
        )

    def del_dhcp_reservation(self, inst_id: str) -> Tuple[bool, str]:
        """Delete a DHCPv4 reservation by its ``_OBJ_InstID``
        (e.g. ``DEV.V4DP.Sr.Pl1.Bd1``)."""
        fields = self._prefixed(self._DHCP_BIND_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.DHCP_VIEW_URL, self.DHCP_BINDINGS_URL,
            action="Delete", fields=fields,
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

    # --------------------------------------------------------- Mesh topology

    def _menudata_raw(
        self,
        view_url: str,
        data_url: str,
        retry: bool = True,
    ) -> str:
        """Like ``_menudata`` but returns the raw response body. Used for
        the few endpoints that emit JSON (e.g. ``topo_lua.lua``) instead
        of the standard ZTE XML ``Instance/ParaName/ParaValue`` shape."""
        try:
            self.session.get(
                f"{self.base_url}{view_url}", headers=self.NO_CACHE, timeout=8
            )
            resp = self.session.get(
                f"{self.base_url}{data_url}", headers=self.NO_CACHE, timeout=8
            )
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata_raw(view_url, data_url, retry=False)
                return ""
            return resp.text
        except requests.RequestException:
            return ""

    def get_topology(self, retry: bool = True) -> Dict[str, Any]:
        """Return the EasyMesh topology view as a plain dict.

        The endpoint replies with JSON (rare for AGZHM): one
        ``controllerData`` describing the controller (the modem itself)
        plus ``agentlay1`` / ``agentlay2`` for the two extender layers,
        each carrying ``MGET_INST_NUM`` and an optional ``Instance``
        list when satellites are present.
        """
        import json as _json

        body = self._menudata_raw(self.TOPOLOGY_VIEW_URL, self.TOPOLOGY_URL, retry)
        if not body:
            return {}
        try:
            return _json.loads(body)
        except _json.JSONDecodeError:
            return {}

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

    # --------------------------------------------------- System / admin (F)

    def get_admin_users(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return web admin accounts (OBJ_USERINFO_ID, ``devauth_accountmgr``).

        Each instance exposes ``Username`` and ``Right`` (privilege
        level). The modem's ``encode`` hint marks ``Password`` /
        ``NewPassword`` as write-only, so they never appear here.
        """
        return self._menudata(
            self.ADMIN_USERS_VIEW_URL, self.ADMIN_USERS_URL,
            "OBJ_USERINFO_ID", retry,
        )

    def get_web_login_timeout(self, retry: bool = True) -> Dict[str, str]:
        """Return web UI session timeout (OBJ_USERIF_ID, single row).

        ``Timeout`` is expressed in minutes; controls how long an idle
        admin session stays valid before requiring a fresh login.
        """
        rows = self._menudata(
            self.WEB_TIMEOUT_VIEW_URL, self.WEB_TIMEOUT_URL,
            "OBJ_USERIF_ID", retry,
        )
        return rows[0] if rows else {}

    def set_web_login_timeout(
        self, minutes: int, inst_id: str = "IGD"
    ) -> Tuple[bool, str]:
        """Set the web UI idle session timeout (minutes).

        Posts ``IF_ACTION=Apply`` with ``Timeout`` and ``_InstID`` to
        ``web_login_timeout_lua.lua``. Returns ``(ok, raw_body)``.
        See ``firmware/notes/2026-05-29-write-actions-protocol.md`` for
        the convention.
        """
        return self._post_action(
            self.WEB_TIMEOUT_VIEW_URL,
            self.WEB_TIMEOUT_URL,
            action="Apply",
            fields={"_InstID": inst_id, "Timeout": str(int(minutes))},
        )

    def get_mobile_wan(self, retry: bool = True) -> Dict[str, Any]:
        """Return USB-dongle mobile backup status.

        The payload mixes two pieces:
        - top-level scalars ``DongleStatus``, ``DevType``, ``DongleType``
          describing whether a 3G/4G dongle is plugged in;
        - an ``OBJ_WWANMOBILEINFO_ID`` instance with operator name,
          signal strength, IMEI, network mode and a numeric alarm flag.
        Returned shape: ``{"dongle": {...scalars...}, "info": {...row...}}``.
        """
        body = self._menudata_raw(
            self.MOBILE_WAN_VIEW_URL, self.MOBILE_WAN_URL, retry,
        )
        if not body:
            return {"dongle": {}, "info": {}}
        info_rows = self._parse_instances(body, "OBJ_WWANMOBILEINFO_ID")
        dongle: Dict[str, str] = {}
        try:
            tree = ET.fromstring(body)
            for tag in ("DongleStatus", "DevType", "DongleType"):
                el = tree.find(tag)
                if el is not None and el.text is not None:
                    dongle[tag] = el.text
        except ET.ParseError:
            pass
        return {"dongle": dongle, "info": info_rows[0] if info_rows else {}}

    def get_firewall_ipfilter(
        self, retry: bool = True,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return IP-filter rules + the priority slot.

        Same parent view (``filterCriteria``) serves two endpoints:
        - ``OBJ_FWIP_ID`` — the user-defined IP-filter rules (empty
          on a stock install);
        - ``OBJ_FWIP_PRIORITY_ID`` — a single ``FilterIndex`` that
          selects which rule wins on conflict.
        Returned shape: ``{"rules": [...], "priority": [...]}``.
        """
        rules = self._menudata(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_IPFILTER_URL,
            "OBJ_FWIP_ID", retry,
        )
        priority = self._menudata(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_IPFILTER_PRIORITY_URL,
            "OBJ_FWIP_PRIORITY_ID", retry,
        )
        return {"rules": rules, "priority": priority}

    def get_firewall_urlfilter(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return URL-filter rules (OBJ_FWURL_ID).

        The master enable/target switch is already in ``get_firewall_*``
        (URL filter global). This endpoint exposes the per-URL rule
        list, empty on a stock TIM Hub+.
        """
        return self._menudata(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_URLFILTER_URL,
            "OBJ_FWURL_ID", retry,
        )

    # --- Firewall URL-filter write actions ---
    # Same prefixed-ParaName + Apply/-1 convention. The filterCriteria
    # view renders <input id="OBJ_FWURL_ID.Name:URLFilter"> /
    # ".Url:URLFilter"; colonStripping() drops the suffix on submit.
    # Client-side validation: Name 1..32 ASCII, Url 1..128 (url format).
    _FWURL_PREFIX = "OBJ_FWURL_ID"

    def add_url_filter_rule(self, name: str, url: str) -> Tuple[bool, str]:
        """Create a URL-filter rule (POST ``IF_ACTION=Apply`` +
        ``_OBJ_InstID=-1``).

        Only blocks the given URL; existing routes are untouched. The
        master URL-filter toggle lives in the ``firewall`` view and must
        be on for the rule to take effect.
        """
        fields = self._prefixed(self._FWURL_PREFIX, {
            "_OBJ_InstID": "-1",
            "Name": name,
            "Url": url,
        })
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_URLFILTER_URL,
            action="Apply", fields=fields,
        )

    def del_url_filter_rule(self, inst_id: str) -> Tuple[bool, str]:
        """Delete a URL-filter rule by its ``_OBJ_InstID``."""
        fields = self._prefixed(self._FWURL_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_URLFILTER_URL,
            action="Delete", fields=fields,
        )

    # --- Firewall IP-filter write actions ---
    # filterCriteria view renders many <input id="OBJ_FWIP_ID.X:IPFilter">.
    # Server-side required: Name (1..32 ASCII), FilterIndex (1..20),
    # Protocol (1..255). ``S_Protocol`` is a UI-only helper (not stored;
    # comes back empty on read), but the WebUI still submits it so we
    # mirror that. ``FilterTarget`` default is 1=allow in the form, which
    # is the safe default (an allow rule never blocks existing traffic).
    _FWIP_PREFIX = "OBJ_FWIP_ID"
    _IP_PROTO_MAP = {"ICMP": "1", "TCP": "6", "UDP": "17"}

    def add_ip_filter_rule(
        self,
        name: str,
        protocol: str,
        *,
        target: str = "allow",
        filter_index: int = 1,
        enable: bool = True,
        ip_version: str = "4",
        source_ip: str = "",
        source_mask: str = "",
        dest_ip: str = "",
        dest_mask: str = "",
        min_src_port: str = "",
        max_src_port: str = "",
        min_dst_port: str = "",
        max_dst_port: str = "",
        in_iface: str = "",
        out_iface: str = "",
        dscp: str = "",
    ) -> Tuple[bool, str]:
        """Create an IP-filter rule (POST ``IF_ACTION=Apply`` +
        ``_OBJ_InstID=-1``).

        ``protocol`` is ``ICMP``/``TCP``/``UDP`` (case-insensitive) or a
        raw 1..255 number. ``target`` is ``allow`` (default, safe) or
        ``deny``. The modem normalises ``filter_index`` (1..20) to the
        next free slot. Empty IP/port/interface fields mean "any".
        """
        proto = protocol.upper()
        proto_num = self._IP_PROTO_MAP.get(proto)
        if proto_num is None:
            if proto.isdigit() and 1 <= int(proto) <= 255:
                proto_num = proto
            else:
                return False, (
                    f"protocol must be ICMP/TCP/UDP or 1-255 (got {protocol!r})"
                )
        tgt = {"allow": "1", "permit": "1", "deny": "0", "drop": "0"}.get(
            target.lower()
        )
        if tgt is None:
            return False, f"target must be allow/deny (got {target!r})"
        fields = self._prefixed(self._FWIP_PREFIX, {
            "_OBJ_InstID": "-1",
            "Enable": "1" if enable else "0",
            "Name": name,
            "FilterTarget": tgt,
            "FilterIndex": str(filter_index),
            "IPVersion": ip_version,
            "SourceIP": source_ip,
            "SourceIPMask": source_mask,
            "DestIP": dest_ip,
            "DestIPMask": dest_mask,
            "S_Protocol": proto_num,
            "Protocol": proto_num,
            "MinSrcPort": min_src_port,
            "MaxSrcPort": max_src_port,
            "MinDstPort": min_dst_port,
            "MaxDstPort": max_dst_port,
            "INCViewName": in_iface,
            "OUTCViewName": out_iface,
            "DSCP": dscp,
        })
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_IPFILTER_URL,
            action="Apply", fields=fields,
        )

    def del_ip_filter_rule(self, inst_id: str) -> Tuple[bool, str]:
        """Delete an IP-filter rule by its ``_OBJ_InstID``
        (e.g. ``DEV.FW.CHAIN1.IPF1``)."""
        fields = self._prefixed(self._FWIP_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL, self.FW_IPFILTER_URL,
            action="Delete", fields=fields,
        )

    def get_parental_control(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return parental-control entries (OBJ_PARENT_CONTROL_ID).

        Empty by default. The web UI lets you bind MACs to time
        schedules; until that's done the modem returns the empty
        wrapper element.
        """
        return self._menudata(
            self.PARENT_CTRL_VIEW_URL, self.PARENT_CTRL_URL,
            "OBJ_PARENT_CONTROL_ID", retry,
        )

    def _hiddendata(
        self, data_url: str, root_element: str, retry: bool = True,
    ) -> List[Dict[str, str]]:
        """Fetch a ``_type=hiddenData`` endpoint (no view-arming).

        These endpoints sit outside the menuView/menuData dance and
        respond to a plain authenticated GET. Session timeout
        handling is the same — re-login once then retry.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}{data_url}", headers=self.NO_CACHE, timeout=8
            )
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._hiddendata(data_url, root_element, retry=False)
                return []
            return self._parse_instances(resp.text, root_element)
        except requests.RequestException:
            return []

    def get_sntp(self, retry: bool = True) -> Dict[str, str]:
        """Return SNTP/time config (OBJ_SNTP_ID, single row).

        Hidden endpoint, no view arming. Fields include up to 5 NTP
        servers, the modem's current local time, poll interval
        (seconds), a numeric ``ZoneIndex`` (14 = Europe/Rome on
        TIM Hub+), ``AutoSetTzname`` and ``DaylightSavingsUsed``
        flags, plus a DSCP marking.
        """
        rows = self._hiddendata(self.SNTP_URL, "OBJ_SNTP_ID", retry)
        return rows[0] if rows else {}

    def get_voip_media(
        self, retry: bool = True,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return SIP media codec preferences per line.

        The payload carries two roots: ``OBJ_VOIPVPLINE_ID`` (line
        stubs) and ``OBJ_VOIPLINEVMEDAI_ID`` (3 codec rows per line —
        per-line priority list). The codec row ``_InstID`` encodes
        the parent line, e.g. ``IGD.SV.VS1.VP1.VL1.LC.CL1``. Use
        ``MediaVPV`` for the RTP payload type (8=PCMA, 9=G.722,
        18=G.729) and ``MediaVPri`` for the negotiation priority.
        """
        return self._menudata_multi(
            self.SIP_MEDIA_VIEW_URL, self.SIP_MEDIA_URL,
            ["OBJ_VOIPVPLINE_ID", "OBJ_VOIPLINEVMEDAI_ID"],
            retry,
        )

    def get_voip_pos(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return VoIP POS (port-on-off) toggles per VoIP slot.

        Two instances (one per VoIP line slot). ``VoipPosEnable=0``
        means the POS feature is off — typical state on a stock
        TIM Hub+.
        """
        return self._menudata(
            self.VOIP_POS_VIEW_URL, self.VOIP_POS_URL,
            "OBJ_VOIPPOSENABLE_ID", retry,
        )

    def get_usb_devs(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return attached USB storage devices (OBJ_USBSTORAGE_ID).

        Empty when no USB stick is plugged in. The parent view is
        ``localNetStatus`` (shared with LAN clients and public LAN).
        """
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.USB_DEVS_URL,
            "OBJ_USBSTORAGE_ID", retry,
        )

    def get_wifi_ssid_config(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the full SSID config rows (OBJ_WLANAP_ID, ``wlan_sssidconf``).

        Same root as ``get_wifi_aps()`` (status view) but parsed from
        the ``wlanBasic`` parent so the response includes
        ``ESSIDHideEnable`` (hidden SSID toggle) and ``MaxUserNum``
        (per-SSID client cap) on top of the usual security fields.
        """
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL, self.WLAN_SSID_CONF_URL,
            "OBJ_WLANAP_ID", retry,
        )

    def get_edns0(self, retry: bool = True) -> Dict[str, str]:
        """Return EDNS0 toggle state (OBJ_EDNS0_ID, single row).

        EDNS0 = DNS client subnet extension. The instance carries a
        single boolean ``EDNS0Enable`` (default ``0``).
        """
        rows = self._menudata(
            self.EDNS0_VIEW_URL, self.EDNS0_URL,
            "OBJ_EDNS0_ID", retry,
        )
        return rows[0] if rows else {}

    def get_ipv6_prefix(
        self, retry: bool = True,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return IPv6 prefix delegation + static prefix entries.

        Both come from the same ``lanMgrIpv6`` parent view:
        - ``OBJ_PREFIXPOOL_ID`` — DHCPv6-PD prefixes received from the
          ISP (empty on stock TIM Hub+ until WAN6 negotiates a PD);
        - ``OBJ_STATIC_PREFIX_ID`` — manually configured static prefixes.
        Returned shape: ``{"pool": [...], "static": [...]}``.
        """
        pool = self._menudata(
            self.IPV6_PREFIX_VIEW_URL, self.IPV6_PREFIX_POOL_URL,
            "OBJ_PREFIXPOOL_ID", retry,
        )
        static = self._menudata(
            self.IPV6_PREFIX_VIEW_URL, self.IPV6_STATIC_PREFIX_URL,
            "OBJ_STATIC_PREFIX_ID", retry,
        )
        return {"pool": pool, "static": static}

    def get_dsl_interface(self, retry: bool = True) -> Dict[str, str]:
        """Return raw DSL physical line stats (OBJ_DSLINTERFACE_ID, single).

        Different from ``get_dsl_stats()`` (which is the home-page
        summary): this is the full PHY view used by the DSL status
        page — current/max rates, SNR margin, attenuation, TX/RX
        power, FEC/CRC errors, profile, INP and interleave depth,
        plus link encapsulation and Showtime start time.
        """
        rows = self._menudata(
            self.DSL_IF_VIEW_URL, self.DSL_IF_URL,
            "OBJ_DSLINTERFACE_ID", retry,
        )
        return rows[0] if rows else {}

    def get_public_lan(self, retry: bool = True) -> Dict[str, str]:
        """Return the secondary 'public LAN' interface (OBJ_PUBLICLAN_ID).

        On TIM Hub+ this is the optional hotspot/guest public-IP slot;
        when unused the row reports ``Enable=Disabled`` and zeroed
        IP/mask. Only one instance is exposed.
        """
        rows = self._menudata(
            self.PUBLIC_LAN_VIEW_URL, self.PUBLIC_LAN_URL,
            "OBJ_PUBLICLAN_ID", retry,
        )
        return rows[0] if rows else {}

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

    # --------------------------------------------------------- close / logout

    def close(self) -> None:
        """Tear down the local requests session, keeping the modem session
        alive on the server so subsequent CLI invocations can resume from
        the on-disk cache. Called by the normal per-command teardown.
        """
        # Re-save the cookies even after read-only operations: the modem
        # bumps the SID's lifetime on every authenticated request, and we
        # might also have refreshed ``session_token`` mid-flow.
        self._save_cache()
        try:
            self.session.close()
        except Exception:
            pass

    def logout(self) -> None:
        """Explicitly log out of the modem session and wipe the cache.

        Use this when you want the next ``login()`` to start from a
        clean slate (e.g. switching admin user, or freeing the single
        admin slot the modem allows). The CLI exposes it as
        ``h388x logout``.
        """
        if self.session_token:
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
        self._clear_cache()
        self.session.cookies.clear()
        self.session.close()
