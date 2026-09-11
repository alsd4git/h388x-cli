"""H388X wan endpoint implementation mixin."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List


class WanDslMixin:
    def get_dsl_stats(self, retry: bool = True) -> Dict[str, str]:
        instances = self._menudata(
            self.DSL_INIT_URL, self.DSL_STATS_URL, "OBJ_DSLINTERFACE_ID", retry
        )
        return instances[0] if instances else {}

    def get_wan_connections(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return ALL WAN connections (INTERNET_VD/AD, IPTV_VD/AD, ...)."""
        return self._menudata(
            self.DSL_INIT_URL,
            "/?_type=menuData&_tag=wan_internet_lua.lua&TypeUplink=1&pageType=1",
            "ID_WAN_COMFIG",
            retry,
        )

    def get_ddns(self, retry: bool = True) -> Dict[str, str]:
        """Return the DDNS client state (OBJ_DDNSCLIENT_ID, single instance)."""
        rows = self._menudata(
            self.DDNS_VIEW_URL,
            self.DDNS_URL,
            "OBJ_DDNSCLIENT_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_eth_wan_port(self, retry: bool = True) -> Dict[str, str]:
        """Return the eth-WAN uplink port (OBJ_ETH_ID under ethWanStatus)."""
        rows = self._menudata(
            self.ETH_WAN_VIEW_URL,
            self.ETH_WAN_URL,
            "OBJ_ETH_ID",
            retry,
        )
        return rows[0] if rows else {}

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
            self.MOBILE_WAN_VIEW_URL,
            self.MOBILE_WAN_URL,
            retry,
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

    def get_dsl_interface(self, retry: bool = True) -> Dict[str, str]:
        """Return raw DSL physical line stats (OBJ_DSLINTERFACE_ID, single).

        Different from ``get_dsl_stats()`` (which is the home-page
        summary): this is the full PHY view used by the DSL status
        page — current/max rates, SNR margin, attenuation, TX/RX
        power, FEC/CRC errors, profile, INP and interleave depth,
        plus link encapsulation and Showtime start time.
        """
        rows = self._menudata(
            self.DSL_IF_VIEW_URL,
            self.DSL_IF_URL,
            "OBJ_DSLINTERFACE_ID",
            retry,
        )
        return rows[0] if rows else {}
