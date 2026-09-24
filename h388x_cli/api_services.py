"""H388X services endpoint implementation mixin."""

from __future__ import annotations

import json as _json
from typing import Any, Dict, List


from .errors import ParseError


class ServicesMixin:
    def get_voip_status(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return VoIP status: virtual lines + SIP lines from voipstatus.

        Single request, two roots:
        - ``OBJ_VOIPVPLINE_ID``: virtual lines (VL1, VL2) with ``IsOnline``.
        - ``OBJ_VOIPSIPLINE_ID``: SIP user-agent lines with ``PhoneName``,
          ``AuthUserName`` (phone number) and ``IsOnline``.
        """
        return self._menudata_multi(
            self.VOIP_STATUS_VIEW_URL,
            self.VOIP_STATUS_URL,
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
            self.VOIP_FLEX_BIND_VIEW_URL,
            self.VOIP_FLEX_BIND_URL,
            ["OBJ_VOIPHOMELINE_ID", "OBJ_VOIPVPLINE_ID"],
            retry,
        )

    def get_upnp_config(self, retry: bool = True) -> Dict[str, str]:
        """Return UPnP IGD master switch (OBJ_UPNPCONFIG_ID, single)."""
        rows = self._menudata(
            self.UPNP_VIEW_URL,
            self.UPNP_CONFIG_URL,
            "OBJ_UPNPCONFIG_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_upnp_portmappings(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return live UPnP port mappings (OBJ_UPNPPORTMAP_ID)."""
        return self._menudata(
            self.UPNP_VIEW_URL,
            self.UPNP_PORTS_URL,
            "OBJ_UPNPPORTMAP_ID",
            retry,
        )

    def get_dms(self, retry: bool = True) -> Dict[str, str]:
        """Return the DLNA / DMS media-server config (OBJ_DMS_ID, single)."""
        rows = self._menudata(
            self.DMS_VIEW_URL,
            self.DMS_URL,
            "OBJ_DMS_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_ftp(self, retry: bool = True) -> Dict[str, List[Dict[str, str]]]:
        """Return FTP server state: config (OBJ_FMFTPSERVERCFG_ID) + users (OBJ_FMFTPUSER_ID)."""
        return self._menudata_multi(
            self.FTP_VIEW_URL,
            self.FTP_URL,
            ["OBJ_FMFTPSERVERCFG_ID", "OBJ_FMFTPUSER_ID"],
            retry,
        )

    def get_nanocdn(self, retry: bool = True) -> Dict[str, str]:
        """Return NanoCDN runtime stats (OBJ_NANOCDN_STATUS_ID, single).

        NanoCDN is the TIM/IPTV multicast-to-unicast offload running on
        the modem; the page exposes ``Status``, current/min/max session
        count and multicast bitrate counters.
        """
        rows = self._menudata(
            self.NANOCDN_VIEW_URL,
            self.NANOCDN_URL,
            "OBJ_NANOCDN_STATUS_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_topology(self, retry: bool = True) -> Dict[str, Any]:
        """Return the EasyMesh topology, raising ``ParseError`` on invalid JSON."""
        body = self._menudata_raw(self.TOPOLOGY_VIEW_URL, self.TOPOLOGY_URL, retry)
        try:
            return _json.loads(body)
        except _json.JSONDecodeError as exc:
            raise ParseError(f"invalid topology JSON: {exc}") from exc

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
        self,
        retry: bool = True,
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
            self.SIP_MEDIA_VIEW_URL,
            self.SIP_MEDIA_URL,
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
            self.VOIP_POS_VIEW_URL,
            self.VOIP_POS_URL,
            "OBJ_VOIPPOSENABLE_ID",
            retry,
        )
