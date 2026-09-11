"""H388X firewall endpoint implementation mixin."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError

from .validation import (
    IpFilterSpec,
    PortForwardSpec,
    UrlFilterSpec,
    validation_error_message,
)


class FirewallMixin:
    def get_firewall_level(self, retry: bool = True) -> Dict[str, str]:
        """Return the active firewall level (Low/Middle/High) from OBJ_FWLEVEL_ID."""
        rows = self._menudata(
            self.FIREWALL_VIEW_URL,
            self.FIREWALL_LEVEL_URL,
            "OBJ_FWLEVEL_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_firewall_dos(self, retry: bool = True) -> Dict[str, str]:
        """Return DoS protection state (Enable + Threshold) from OBJ_FWDOS_ID."""
        rows = self._menudata(
            self.FIREWALL_VIEW_URL,
            self.FIREWALL_DOS_URL,
            "OBJ_FWDOS_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_url_filter_global(self, retry: bool = True) -> Dict[str, str]:
        """Return URL-filter master switch + target action from OBJ_FWBASE_ID."""
        rows = self._menudata(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FIREWALL_FILTER_GLOBAL_URL,
            "OBJ_FWBASE_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_dmz(self, retry: bool = True) -> Dict[str, str]:
        """Return DMZ state (Enable + InternalClient) from OBJ_FWDMZ_ID."""
        rows = self._menudata(
            self.DMZ_VIEW_URL,
            self.FIREWALL_DMZ_URL,
            "OBJ_FWDMZ_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_port_forwarding_rules(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return all port-forwarding rules (OBJ_FWPM_ID) configured in NAT."""
        return self._menudata(
            self.PORT_FORWARDING_VIEW_URL,
            self.PORT_FORWARDING_URL,
            "OBJ_FWPM_ID",
            retry,
        )

    @staticmethod
    def _prefixed(prefix: str, fields: Dict[str, str]) -> Dict[str, str]:
        return {f"{prefix}.{k}": v for k, v in fields.items()}

    def _set_rule_enabled(
        self,
        view_url: str,
        data_url: str,
        prefix: str,
        inst_id: str,
        enable: bool,
    ) -> Tuple[bool, str]:
        """Flip an instance's ``Enable`` flag via the light ``InstSwitch``
        POST the WebUI uses for the on/off toggle in list views.

        Unlike a full edit this only submits ``Enable`` + the real
        ``_OBJ_InstID`` (still ``IF_ACTION=Apply``); the modem preserves
        every other field of the row. Verified live on port-forwarding.
        """
        fields = self._prefixed(
            prefix,
            {
                "Enable": "1" if enable else "0",
                "_OBJ_InstID": inst_id,
            },
        )
        return self._post_action(
            view_url,
            data_url,
            action="Apply",
            fields=fields,
        )

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
        """Create a new port-forwarding rule after local validation."""
        ext_end = external_port_end if external_port_end is not None else external_port
        int_port = internal_port if internal_port is not None else external_port
        try:
            spec = PortForwardSpec(
                description=description,
                protocol=protocol,
                external_port=external_port,
                external_port_end=ext_end,
                internal_client=internal_client,
                internal_port=int_port,
                remote_host=remote_host,
                remote_host_end=remote_host_end,
            )
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"

        fields = self._prefixed(
            self._PFWD_PREFIX,
            {
                "_OBJ_InstID": "-1",
                "Enable": "1" if enable else "0",
                "Description": spec.description,
                "Protocol": spec.protocol,
                "ExternalPort": str(spec.external_port),
                "ExternalPortEndRange": str(spec.external_port_end),
                "InternalClient": spec.internal_client,
                "InternalPort": str(spec.internal_port),
                "RemoteHost": spec.remote_host,
                "RemoteHostEndRange": spec.remote_host_end,
            },
        )
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

    def set_port_forwarding_enabled(
        self,
        inst_id: str,
        enable: bool,
    ) -> Tuple[bool, str]:
        """Enable/disable a port-forwarding rule without editing its
        other fields (light ``InstSwitch`` toggle)."""
        return self._set_rule_enabled(
            self.PORT_FORWARDING_VIEW_URL,
            self.PORT_FORWARDING_URL,
            self._PFWD_PREFIX,
            inst_id,
            enable,
        )

    def edit_port_forwarding_rule(
        self,
        inst_id: str,
        *,
        description: Optional[str] = None,
        protocol: Optional[str] = None,
        external_port: Optional[int] = None,
        internal_client: Optional[str] = None,
        internal_port: Optional[int] = None,
        external_port_end: Optional[int] = None,
        remote_host: Optional[str] = None,
        remote_host_end: Optional[str] = None,
        enable: Optional[bool] = None,
    ) -> Tuple[bool, str]:
        """Edit a port-forwarding rule after validating the final payload."""
        current = next(
            (
                r
                for r in self.get_port_forwarding_rules()
                if r.get("_OBJ_InstID") == inst_id
            ),
            None,
        )
        if current is None:
            return False, f"rule {inst_id!r} not found"

        def pick(new: object, key: str) -> str:
            return str(new) if new is not None else current.get(key, "")

        current_external_port = current.get("ExternalPort", "")
        current_external_end = current.get("ExternalPortEndRange", "")
        if external_port_end is not None:
            target_external_end = external_port_end
        elif (
            external_port is not None and current_external_end == current_external_port
        ):
            target_external_end = external_port
        else:
            target_external_end = current_external_end

        try:
            spec = PortForwardSpec(
                description=pick(description, "Description"),
                protocol=pick(protocol, "Protocol"),
                external_port=pick(external_port, "ExternalPort"),
                external_port_end=target_external_end,
                internal_client=pick(internal_client, "InternalClient"),
                internal_port=pick(internal_port, "InternalPort"),
                remote_host=pick(remote_host, "RemoteHost"),
                remote_host_end=pick(remote_host_end, "RemoteHostEndRange"),
            )
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"

        enable_val = (
            current.get("Enable", "1") if enable is None else ("1" if enable else "0")
        )
        fields = self._prefixed(
            self._PFWD_PREFIX,
            {
                "_OBJ_InstID": inst_id,
                "Enable": enable_val,
                "Description": spec.description,
                "Protocol": spec.protocol,
                "ExternalPort": str(spec.external_port),
                "ExternalPortEndRange": str(spec.external_port_end),
                "InternalClient": spec.internal_client,
                "InternalPort": str(spec.internal_port),
                "RemoteHost": spec.remote_host,
                "RemoteHostEndRange": spec.remote_host_end,
            },
        )
        return self._post_action(
            self.PORT_FORWARDING_VIEW_URL,
            self.PORT_FORWARDING_URL,
            action="Apply",
            fields=fields,
        )

    def get_firewall_ipfilter(
        self,
        retry: bool = True,
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
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_IPFILTER_URL,
            "OBJ_FWIP_ID",
            retry,
        )
        priority = self._menudata(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_IPFILTER_PRIORITY_URL,
            "OBJ_FWIP_PRIORITY_ID",
            retry,
        )
        return {"rules": rules, "priority": priority}

    def get_firewall_urlfilter(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return URL-filter rules (OBJ_FWURL_ID).

        The master enable/target switch is already in ``get_firewall_*``
        (URL filter global). This endpoint exposes the per-URL rule
        list, empty on a stock TIM Hub+.
        """
        return self._menudata(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_URLFILTER_URL,
            "OBJ_FWURL_ID",
            retry,
        )

    def add_url_filter_rule(self, name: str, url: str) -> Tuple[bool, str]:
        """Create a URL-filter rule after observed WebUI validation."""
        try:
            spec = UrlFilterSpec(name=name, url=url)
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"
        fields = self._prefixed(
            self._FWURL_PREFIX,
            {
                "_OBJ_InstID": "-1",
                "Name": spec.name,
                "Url": spec.url,
            },
        )
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_URLFILTER_URL,
            action="Apply",
            fields=fields,
        )

    def del_url_filter_rule(self, inst_id: str) -> Tuple[bool, str]:
        """Delete a URL-filter rule by its ``_OBJ_InstID``."""
        fields = self._prefixed(self._FWURL_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_URLFILTER_URL,
            action="Delete",
            fields=fields,
        )

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
        """Create an IP-filter rule after known WebUI validation."""
        try:
            spec = IpFilterSpec(
                name=name,
                protocol=protocol,
                target=target,
                filter_index=filter_index,
                ip_version=ip_version,
                source_ip=source_ip,
                dest_ip=dest_ip,
                min_src_port=min_src_port,
                max_src_port=max_src_port,
                min_dst_port=min_dst_port,
                max_dst_port=max_dst_port,
                dscp=dscp,
            )
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"

        proto_num = self._IP_PROTO_MAP.get(spec.protocol, spec.protocol)
        target_num = "1" if spec.target == "allow" else "0"
        fields = self._prefixed(
            self._FWIP_PREFIX,
            {
                "_OBJ_InstID": "-1",
                "Enable": "1" if enable else "0",
                "Name": spec.name,
                "FilterTarget": target_num,
                "FilterIndex": str(spec.filter_index),
                "IPVersion": spec.ip_version,
                "SourceIP": spec.source_ip,
                "SourceIPMask": source_mask,
                "DestIP": spec.dest_ip,
                "DestIPMask": dest_mask,
                "S_Protocol": proto_num,
                "Protocol": proto_num,
                "MinSrcPort": spec.min_src_port,
                "MaxSrcPort": spec.max_src_port,
                "MinDstPort": spec.min_dst_port,
                "MaxDstPort": spec.max_dst_port,
                "INCViewName": in_iface,
                "OUTCViewName": out_iface,
                "DSCP": spec.dscp,
            },
        )
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_IPFILTER_URL,
            action="Apply",
            fields=fields,
        )

    def del_ip_filter_rule(self, inst_id: str) -> Tuple[bool, str]:
        """Delete an IP-filter rule by its ``_OBJ_InstID``
        (e.g. ``DEV.FW.CHAIN1.IPF1``)."""
        fields = self._prefixed(self._FWIP_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_IPFILTER_URL,
            action="Delete",
            fields=fields,
        )

    def set_ip_filter_enabled(
        self,
        inst_id: str,
        enable: bool,
    ) -> Tuple[bool, str]:
        """Enable/disable an IP-filter rule without editing its other
        fields (light ``InstSwitch`` toggle)."""
        return self._set_rule_enabled(
            self.FILTER_CRITERIA_VIEW_URL,
            self.FW_IPFILTER_URL,
            self._FWIP_PREFIX,
            inst_id,
            enable,
        )

    def get_parental_control(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return parental-control entries (OBJ_PARENT_CONTROL_ID).

        Empty by default. The web UI lets you bind MACs to time
        schedules; until that's done the modem returns the empty
        wrapper element.
        """
        return self._menudata(
            self.PARENT_CTRL_VIEW_URL,
            self.PARENT_CTRL_URL,
            "OBJ_PARENT_CONTROL_ID",
            retry,
        )
