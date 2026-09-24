"""H388X lan endpoint implementation mixin."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from pydantic import ValidationError

from .validation import (
    DhcpReservationSpec,
    validation_error_message,
)


class LanMixin:
    def get_dhcp_leases(self, retry: bool = True) -> List[Dict[str, str]]:
        return self._menudata(
            self.DHCP_VIEW_URL, self.DHCP_LEASES_URL, "OBJ_DHCPHOSTINFO_ID", retry
        )

    def get_lan_clients(self, retry: bool = True) -> List[Dict[str, str]]:
        return self._menudata(
            self.LOCALNET_VIEW_URL, self.LAN_CLIENTS_URL, "OBJ_ACCESSDEV_ID", retry
        )

    def add_dhcp_reservation(
        self, mac: str, ip_address: str, name: str
    ) -> Tuple[bool, str]:
        """Create a static DHCPv4 reservation after local validation."""
        try:
            spec = DhcpReservationSpec(mac=mac, ip_address=ip_address, name=name)
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"
        fields = self._prefixed(
            self._DHCP_BIND_PREFIX,
            {
                "_OBJ_InstID": "-1",
                "Name": spec.name,
                "IPAddr": spec.ip_address,
                "MACAddr": spec.mac,
            },
        )
        return self._post_action(
            self.DHCP_VIEW_URL,
            self.DHCP_BINDINGS_URL,
            action="Apply",
            fields=fields,
        )

    def del_dhcp_reservation(self, inst_id: str) -> Tuple[bool, str]:
        """Delete a DHCPv4 reservation by its ``_OBJ_InstID``
        (e.g. ``DEV.V4DP.Sr.Pl1.Bd1``)."""
        fields = self._prefixed(self._DHCP_BIND_PREFIX, {"_OBJ_InstID": inst_id})
        return self._post_action(
            self.DHCP_VIEW_URL,
            self.DHCP_BINDINGS_URL,
            action="Delete",
            fields=fields,
        )

    def edit_dhcp_reservation(
        self,
        inst_id: str,
        *,
        name: Optional[str] = None,
        ip_address: Optional[str] = None,
        mac: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Edit a DHCPv4 reservation after validating its final payload."""
        current = next(
            (r for r in self.get_dhcp_bindings() if r.get("_OBJ_InstID") == inst_id),
            None,
        )
        if current is None:
            return False, f"binding {inst_id!r} not found"

        def pick(new: object, key: str) -> str:
            return str(new) if new is not None else current.get(key, "")

        try:
            spec = DhcpReservationSpec(
                name=pick(name, "Name"),
                ip_address=pick(ip_address, "IPAddr"),
                mac=pick(mac, "MACAddr"),
            )
        except ValidationError as exc:
            return False, f"validation error: {validation_error_message(exc)}"
        fields = self._prefixed(
            self._DHCP_BIND_PREFIX,
            {
                "_OBJ_InstID": inst_id,
                "Name": spec.name,
                "IPAddr": spec.ip_address,
                "MACAddr": spec.mac,
            },
        )
        return self._post_action(
            self.DHCP_VIEW_URL,
            self.DHCP_BINDINGS_URL,
            action="Apply",
            fields=fields,
        )

    def get_dns_local(self, retry: bool = True) -> Dict[str, str]:
        """Return the modem's own DNS server config (OBJ_DNS_ID)."""
        rows = self._menudata(
            self.DNS_VIEW_URL,
            self.DNS_LOCAL_URL,
            "OBJ_DNS_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_dns_hostnames(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the DNS-bound hostnames known to the modem (ALLDNSHOST)."""
        return self._menudata(
            self.DNS_VIEW_URL,
            self.DNS_HOSTNAMES_URL,
            "ALLDNSHOST",
            retry,
        )

    def get_mac_table(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the L2 forwarding table (OBJ_GETMACINST_ID) seen by the bridge."""
        return self._menudata(
            self.MAC_TABLE_VIEW_URL,
            self.MAC_TABLE_URL,
            "OBJ_GETMACINST_ID",
            retry,
        )

    def get_arp_table(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the modem's L3->L2 ARP cache (OBJ_GETARPINST_ID)."""
        return self._menudata(
            self.ARP_VIEW_URL,
            self.ARP_URL,
            "OBJ_GETARPINST_ID",
            retry,
        )

    def get_eth_lan_ports(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return the 4 LAN ethernet ports (OBJ_ETH_ID under localNetStatus)."""
        return self._menudata(
            self.LOCALNET_VIEW_URL,
            self.ETH_LAN_URL,
            "OBJ_ETH_ID",
            retry,
        )

    def get_dhcp_config(self, retry: bool = True) -> Dict[str, str]:
        """Return the LAN DHCPv4 server config (OBJ_Br0AndDhcpsHosCfg_ID)."""
        rows = self._menudata(
            self.DHCP_VIEW_URL,
            self.DHCP_CONFIG_URL,
            "OBJ_Br0AndDhcpsHosCfg_ID",
            retry,
        )
        return rows[0] if rows else {}

    def set_dhcp_dns(
        self,
        dns1: Optional[str] = None,
        dns2: Optional[str] = None,
        from_wan: Optional[bool] = None,
    ) -> Tuple[bool, str]:
        """Set the DNS servers handed to LAN clients via DHCP.

        This is the resolver the LAN actually uses (the modem's own
        ``dns_local`` SerIPAddress is not editable in the WebUI). It's a
        single-instance scalar config: we read the full current row and
        re-POST ``IF_ACTION=Apply`` with only the DNS fields changed, so
        IP/pool/lease/mask are preserved verbatim.

        ``from_wan=True`` flips ``DnsServerSource`` to 1 (use the ISP
        DNS, ignoring dns1/dns2). Otherwise the source is forced to 0
        (manual) and dns1/dns2 are applied. Existing leases keep their
        old DNS until renewal, so this never drops the live connection.
        """
        cur = self.get_dhcp_config()
        if not cur:
            return False, "could not read current DHCP config"
        fields = dict(cur)
        if from_wan:
            fields["DnsServerSource"] = "1"
        else:
            fields["DnsServerSource"] = "0"
            if dns1 is not None:
                fields["DNSServer1"] = dns1
            if dns2 is not None:
                fields["DNSServer2"] = dns2
        return self._post_action(
            self.DHCP_VIEW_URL,
            self.DHCP_CONFIG_URL,
            action="Apply",
            fields=fields,
        )

    def get_dhcp_bindings(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return DHCPv4 reservations / static bindings (OBJ_DHCPBIND_ID)."""
        return self._menudata(
            self.DHCP_VIEW_URL,
            self.DHCP_BINDINGS_URL,
            "OBJ_DHCPBIND_ID",
            retry,
        )

    def get_dhcp6_server(self, retry: bool = True) -> Dict[str, str]:
        """Return the LAN DHCPv6 server config (OBJ_DHCP6S_ID, single)."""
        rows = self._menudata(
            self.DHCP6_VIEW_URL,
            self.DHCP6_SERVER_URL,
            "OBJ_DHCP6S_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_dhcp6_hosts(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return DHCPv6 client bindings (OBJ_DHCP6C_ID); empty when IPv6 is off."""
        return self._menudata(
            self.DHCP6_VIEW_URL,
            self.DHCP6_HOSTS_URL,
            "OBJ_DHCP6C_ID",
            retry,
        )

    def get_usb_devs(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return attached USB storage devices (OBJ_USBSTORAGE_ID).

        Empty when no USB stick is plugged in. The parent view is
        ``localNetStatus`` (shared with LAN clients and public LAN).
        """
        return self._menudata(
            self.LOCALNET_VIEW_URL,
            self.USB_DEVS_URL,
            "OBJ_USBSTORAGE_ID",
            retry,
        )

    def get_edns0(self, retry: bool = True) -> Dict[str, str]:
        """Return EDNS0 toggle state (OBJ_EDNS0_ID, single row).

        EDNS0 = DNS client subnet extension. The instance carries a
        single boolean ``EDNS0Enable`` (default ``0``).
        """
        rows = self._menudata(
            self.EDNS0_VIEW_URL,
            self.EDNS0_URL,
            "OBJ_EDNS0_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_ipv6_prefix(
        self,
        retry: bool = True,
    ) -> Dict[str, List[Dict[str, str]]]:
        """Return IPv6 prefix delegation + static prefix entries.

        Both come from the same ``lanMgrIpv6`` parent view:
        - ``OBJ_PREFIXPOOL_ID`` — DHCPv6-PD prefixes received from the
          ISP (empty on stock TIM Hub+ until WAN6 negotiates a PD);
        - ``OBJ_STATIC_PREFIX_ID`` — manually configured static prefixes.
        Returned shape: ``{"pool": [...], "static": [...]}``.
        """
        pool = self._menudata(
            self.IPV6_PREFIX_VIEW_URL,
            self.IPV6_PREFIX_POOL_URL,
            "OBJ_PREFIXPOOL_ID",
            retry,
        )
        static = self._menudata(
            self.IPV6_PREFIX_VIEW_URL,
            self.IPV6_STATIC_PREFIX_URL,
            "OBJ_STATIC_PREFIX_ID",
            retry,
        )
        return {"pool": pool, "static": static}

    def get_public_lan(self, retry: bool = True) -> Dict[str, str]:
        """Return the secondary 'public LAN' interface (OBJ_PUBLICLAN_ID).

        On TIM Hub+ this is the optional hotspot/guest public-IP slot;
        when unused the row reports ``Enable=Disabled`` and zeroed
        IP/mask. Only one instance is exposed.
        """
        rows = self._menudata(
            self.PUBLIC_LAN_VIEW_URL,
            self.PUBLIC_LAN_URL,
            "OBJ_PUBLICLAN_ID",
            retry,
        )
        return rows[0] if rows else {}
