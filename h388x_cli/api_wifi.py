"""H388X wifi endpoint implementation mixin."""

from __future__ import annotations

from typing import Dict, List


from .errors import SessionExpiredError


class WifiMixin:
    def get_wifi_clients(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return Wi-Fi clients after reproducing the WebUI arming sequence."""
        self._get_response(f"{self.base_url}{self.LOCALNET_VIEW_URL}")
        wlan = self._get_response(f"{self.base_url}{self.WLAN_APS_URL}")
        if self._is_session_expired(wlan.text):
            if retry and self.login():
                return self.get_wifi_clients(retry=False)
            raise SessionExpiredError("session expired while arming Wi-Fi client view")
        clients = self._get_response(f"{self.base_url}{self.WIFI_CLIENTS_URL}")
        if self._is_session_expired(clients.text):
            if retry and self.login():
                return self.get_wifi_clients(retry=False)
            raise SessionExpiredError("session expired while reading Wi-Fi clients")
        return self._parse_instances(clients.text, "OBJ_ACCESSDEV_ID")

    def get_wifi_radios(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the two WLAN radios (2.4 GHz / 5 GHz) and their on/off state."""
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL,
            self.WLAN_RADIOS_URL,
            "OBJ_WLANSETTING_ID",
            retry,
        )

    def get_wifi_aps(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return all WLAN access points (SSIDs) with ESSID, auth and encryption."""
        return self._menudata(
            self.LOCALNET_VIEW_URL,
            self.WLAN_APS_URL,
            "OBJ_WLANAP_ID",
            retry,
        )

    def get_wifi_advanced(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return advanced per-radio settings (OBJ_WLANSETTING_ID, 2 rows).

        Same root element as ``get_wifi_radios()``, but the advanced
        endpoint exposes the channel/bandwidth/power/standard config
        instead of just the on/off state.
        """
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL,
            self.WLAN_ADV_RADIOS_URL,
            "OBJ_WLANSETTING_ID",
            retry,
        )

    def get_wifi_mac_filter(
        self, retry: bool = True
    ) -> Dict[str, List[Dict[str, str]]]:
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
            self.WLAN_SCHEDULE_VIEW_URL,
            self.WLAN_SCHEDULE_URL,
            "OBJ_WLAN_WIFISCHEDULE",
            retry,
        )

    def get_band_steering(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return EasyMesh + band steering master switches (single page).

        Same response carries two siblings:
        - ``OBJ_EASYMESHENABLE_ID`` (EasyMesh root toggle)
        - ``OBJ_BANDSTEERENABLE_ID`` (band steering toggle)
        """
        return self._menudata_multi(
            self.WLAN_BSS_STEERING_VIEW_URL,
            self.WLAN_BSS_STEERING_URL,
            ["OBJ_EASYMESHENABLE_ID", "OBJ_BANDSTEERENABLE_ID"],
            retry,
        )

    def get_wifi_ssid_config(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the full SSID config rows (OBJ_WLANAP_ID, ``wlan_sssidconf``).

        Same root as ``get_wifi_aps()`` (status view) but parsed from
        the ``wlanBasic`` parent so the response includes
        ``ESSIDHideEnable`` (hidden SSID toggle) and ``MaxUserNum``
        (per-SSID client cap) on top of the usual security fields.
        """
        return self._menudata(
            self.WLAN_BASIC_VIEW_URL,
            self.WLAN_SSID_CONF_URL,
            "OBJ_WLANAP_ID",
            retry,
        )
