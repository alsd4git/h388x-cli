# WebUI coverage matrix

Inventory of the TIM HUB+ **AGZHM_1.4.4** firmware built from the endpoints
implemented in `h388x_cli/api.py`, the local discovery report, and the commands
documented in `README.md`.

The matrix is intentionally conservative. "covered" means the CLI path is
implemented and has an offline-tested read path. For writes, the POST must
also be verified in the code or API. A function is marked "not available on
TIM firmware" only after a live check or an observed missing WebUI entry.

## Legend

| Status | Meaning |
| --- | --- |
| covered | Endpoint and CLI function are available; offline fixtures/tests are present where applicable. |
| partially covered | Reading is available, but one or more page actions are not implemented yet. |
| HAR required | A reliable POST mapping is missing or the function is not exposed by the CLI. Record one isolated change before implementing it. |
| not available on TIM firmware | The function was verified as absent on the target firmware. No row uses this status without evidence. |

`R` = read, `W` = write/action, `R/W` = both.

## Live verification (Chrome, 2026-08-08)

The authenticated Chrome session on the active modem was used only to open
pages and read the DOM. No `Apply`, `Diagnostics`, `Reboot`, `Backup`,
`Logout`, or other state-changing controls were pressed. The visible menus
`Internet`, `Local network`, `VoIP`, `Management & diagnostics`, and
`Topology` were confirmed.

The live check also confirmed forms for firewall/DMZ, parental controls,
DDNS, WLAN radio, ACL, band steering/Easy Mesh, scheduling, VoIP codecs and
mapping, FTP, UPnP, DMS, IPv6, EDNS0, timeout, accounts, backups, and
diagnostics. Device values and identifiers are omitted so active-network data
does not become a fixture or log.

The current discovery exposes `wan_internet_lua.lua` for connection reads
(`ID_WAN_COMFIG`), but no PPPoE or DHCP reconnect/renew endpoint. We therefore
do not add a misleading `renew-ip` command. Reboot is the only known action,
and it intentionally disrupts connectivity.

## Page → endpoint → command matrix

| WebUI page (`menuView`) | Endpoint (`menuData`/`hiddenData`) | Operation | CLI command | Status | Notes |
| --- | --- | :---: | --- | --- | --- |
| `statusMgr` | `devmgr_statusmgr_lua.lua` | R | `info` | covered | Modem identity, serial number, and firmware. |
| `dslWanStatus` | `dsl_interface_status_lua.lua` | R | `stats`, `dsl-interface` | covered | Summary and PHY data share the payload. |
| `dslWanStatus` | `wan_internet_lua.lua` | R | `wan` | covered | Includes inactive connections with `wan --all`. |
| `localNetStatus` | `accessdev_landevs_lua.lua` | R | `clients` | covered | LAN clients. |
| `localNetStatus` | `accessdev_ssiddev_lua.lua` | R | `clients` | covered | Wi-Fi clients. The `localNetStatus → wlan_status_lua.lua → accessdev_ssiddev_lua.lua` flow is validated in code. |
| `localNetStatus` | `eth_lanstatus_lua.lua` | R | `eth` | covered | LAN ports. |
| `localNetStatus` | `publiclan_status_lua.lua` | R | `public-lan` | covered | Public/guest LAN slots. |
| `localNetStatus` | `usb_usbdevs_lua.lua` | R | `usb-devs` | covered | Empty when no USB device is connected. |
| `wlanBasic` | `wlan_basiconoff_lua.lua` | R | `wifi` | covered | 2.4/5 GHz radio state. |
| `wlanBasic` | `wlan_status_lua.lua` | R | `wifi` | covered | SSID, security, and AP state. |
| `wlanBasic` | `wlan_basicadconf_lua.lua` | R | `wifi-advanced` | covered | Channel, band, power, and country. |
| `wlanBasic` | `wlan_sssidconf_lua.lua` | R | `wifi-ssid-config` | covered | Includes SSID visibility and `MaxUserNum`. |
| `wlanBasic` | `wlan_basiconoff_lua.lua` | W | — | HAR required | Wi-Fi radio toggle. |
| `wlanBasic` | `wlan_sssidconf_lua.lua` | W | — | HAR required | SSID, password, visibility, and client limit. |
| `wlanBasic` | `wlan_basicadconf_lua.lua` | W | — | HAR required | Advanced radio configuration. |
| `filterCriteria` | `firewall_filterglobal_m.lua` | R | `firewall` | covered | Global URL-filter and target toggle. |
| `filterCriteria` | `firewall_filterglobal_m.lua` | W | — | HAR required | Firewall/URL-filter toggle. |
| `filterCriteria` | `firewall_ipfilter_m.lua` | R/W | `firewall-ipfilter`, `firewall-ipfilter-add`, `firewall-ipfilter-del`, `firewall-ipfilter-toggle` | covered | IP rules and enable toggle. |
| `filterCriteria` | `firewall_ipfilter_priority_lua.lua` | R | `firewall-ipfilter` | covered | Rule priority. |
| `filterCriteria` | `firewall_urlfilter_m.lua` | R/W | `firewall-urlfilter`, `firewall-urlfilter-add`, `firewall-urlfilter-del` | covered | URL rules. The master switch remains in the global row. |
| `firewall` | `firewall_config_lua.lua` | R | `firewall` | covered | Firewall level. |
| `firewall` | `firewall_dos_lua.lua` | R | `firewall` | covered | Anti-DoS settings and thresholds. |
| `firewall` | `firewall_config_lua.lua`, `firewall_dos_lua.lua` | W | — | HAR required | Firewall level and anti-DoS options. |
| `dmzMenu` | `firewall_dmz_m.lua` | R | `firewall` | covered | DMZ state and internal client. |
| `dmzMenu` | `firewall_dmz_m.lua` | W | — | HAR required | DMZ management. |
| `portForwardingMenu` | `firewall_portforwarding_m.lua` | R/W | `port-forward`, `port-forward-add`, `port-forward-del`, `port-forward-toggle`, `port-forward-edit` | covered | Add/delete/toggle/edit verified through the API. |
| `dns` | `dns_localdns_lua.lua` | R | `dns` | covered | Local DNS configuration. |
| `dns` | `dns_hostname_lua.lua` | R | `dns` | covered | Associated hostnames. |
| `dns` / `lanMgrIpv4` | `dhcp4s_dhcpbasiccfg_lua.lua` | R/W | `dhcp`, `dns-set` | covered | `dns-set` changes DNS servers handed out by DHCP, not the local resolver. |
| `dns` | `dns_hostname_lua.lua` | W | — | HAR required | Edit/add static hostnames. |
| `macTable` | `macinfo_mactable_lua.lua` | R | `mac-table` | covered | Bridge FDB. |
| `arpTable` | `arp_arptable_lua.lua` | R | `arp` | covered | IPv4 ARP cache. |
| `ddns` | `ddns_lua.lua` | R | `ddns` | covered | DDNS client state. |
| `ddns` | `ddns_lua.lua` | W | — | HAR required | Provider and credential configuration. |
| `ethWanStatus` | `eth_interface_status_lua.lua` | R | `eth` | covered | Ethernet WAN uplink. |
| `lanMgrIpv4` | `dhcp4s_dhcpbasiccfg_lua.lua` | R | `dhcp` | covered | DHCPv4 server. |
| `lanMgrIpv4` | `dhcp4s_dhcpbinding_m.lua` | R/W | `dhcp`, `devices set`, `devices clear`, `devices import`, `devices edit`, `dhcp-reserve-add`, `dhcp-reserve-del` | covered | DHCP reservations, including read-modify-write edit. |
| `lanMgrIpv4` | `dhcp4s_dhcpbinding_m.lua` | W | — | partially covered | There is no dedicated `dhcp-reserve-edit` command yet. Edit is available through `devices` actions. |
| `lanMgrIpv6` | `dhcp6s_dhcpserver_lua.lua`, `dhcp6s_hostinfo_lua.lua`, `ra_raservice_lua.lua` | R | `dhcp6` | covered | DHCPv6 and Router Advertisement. |
| `lanMgrIpv6` | `prefix_prefixpool_lua.lua`, `prefix_staticprefix_lua.lua` | R | `ipv6-prefix` | covered | Prefix delegation and static prefixes. |
| `lanMgrIpv6` | `dhcp6s_dhcpserver_lua.lua`, `ra_raservice_lua.lua`, `prefix_staticprefix_lua.lua` | W | — | HAR required | IPv6 and RA toggle/configuration. |
| `smEdns0` | `edns0_lua.lua` | R | `edns0` | covered | EDNS0 state. |
| `smEdns0` | `edns0_lua.lua` | W | — | HAR required | EDNS0 toggle. |
| `voipStatus` | `voip_voipstatus_m.lua` | R | `voip` | covered | SIP line registration. |
| `flexibleBind` | `voip_flexiblebinding_lua.lua` | R | `voip` | covered | TEL physical binding. |
| `sipMedia` | `voip_sipmedia_lua.lua` | R | `voip-media` | covered | Codecs and per-line priority. |
| `posOnoff` | `voip_posonoff_lua.lua` | R | `voip-pos` | covered | POS toggle per slot. |
| `voipStatus` / `sipMedia` | corresponding SIP endpoints | W | — | HAR required | SIP/VoIP credentials, codecs, and configuration. Sensitive action. |
| `upnp` | `upnp_upnp_m.lua`, `upnp_portmapping_lua.lua` | R | `upnp` | covered | State and dynamic port mappings. |
| `upnp` | same endpoints | W | — | HAR required | UPnP toggle and persistent mapping management. |
| `dms` | `dms_dms_lua.lua` | R | `dms` | covered | DLNA/media server. |
| `dms` | `dms_dms_lua.lua` | W | — | HAR required | DLNA configuration. |
| `ftp` | `ftp_ftpserver_m.lua` | R | `ftp` | covered | FTP server and users. |
| `ftp` | `ftp_ftpserver_m.lua` | W | — | HAR required | FTP toggle and user management. |
| `mabrNanoCDN` | `nanocdn_lua.lua` | R | `nanocdn` | covered | TIM IPTV runtime statistics. |
| `mmTopology` | `topo_lua.lua` | R | `topology`, `health` | covered | EasyMesh JSON payload. |
| `wlanBssSteeringOnoff` | `wlan_BssSteeringOnoff_lua.lua` | R | `band-steering` | covered | EasyMesh and band-steering master switch. |
| `wlanBssSteeringOnoff` | `wlan_BssSteeringOnoff_lua.lua` | W | — | HAR required | EasyMesh/band-steering toggle. |
| `WlanWiFiSchedule` | `wlan_wifi_schedule_lua.lua` | R | `wifi-schedule` | covered | Recurring schedules. |
| `WlanWiFiSchedule` | `wlan_wifi_schedule_lua.lua` | W | — | HAR required | Create, edit, or disable schedules. |
| `wlanAdvanced` | `wlan_macfilteraclpolicy_lua.lua`, `wlan_macfilterrule_m.lua` | R | `wifi-acl` | covered | Wi-Fi ACL policy and rules. |
| `wlanAdvanced` | `wlan_macfilteraclpolicy_lua.lua`, `wlan_macfilterrule_m.lua` | W | — | HAR required | Wi-Fi ACL management. |
| `parentCtrl` | `firewall_parentctrl_lua.lua` | R | `parental-control` | covered | MAC/schedule bindings. |
| `parentCtrl` | `firewall_parentctrl_lua.lua` | W | — | HAR required | Full parental controls. |
| `accountMgr` | `devauth_accountmgr_lua.lua` | R | `admin-users` | covered | Accounts and privileges. Passwords are not returned. |
| `accountMgr` | `devauth_accountmgr_lua.lua` | W | — | HAR required | Administrator password change. Sensitive action. |
| `loginTimeoutMgr` | `web_login_timeout_lua.lua` | R/W | `web-timeout`, `web-timeout --set MINUTES` | covered | 1–60 minute timeout. |
| `wan3gStatus` | `wwan_mobile_status_lua.lua` | R | `mobile-wan` | covered | Mobile dongle and network state. |
| `usrCfgMgr` | `do_download_usercfg.lua` | R | `config backup` | covered | Binary backup. Local output uses restrictive permissions. |
| `usrCfgMgr` | configuration restore endpoint | W | — | HAR required | Restore. Requires a preventive backup and explicit confirmation. |
| `rebootAndReset` | `devmgr_restartmgr_lua.lua` | W | `reboot` | covered | POST verified. Confirmation required unless `-y` is supplied. |
| `rebootAndReset` | reset/factory endpoint | W | — | HAR required | Factory reset. Sensitive action. |
| `networkDiag` | `networkdiag_ping_lua.lua` | R/W | `ping` | covered | Asynchronous modem-side diagnostic. Does not change configuration. |
| `networkDiag` | `networkdiag_traceroute_lua.lua` | R/W | `traceroute` | covered | Asynchronous modem-side diagnostic. Does not change configuration. |
| `networkDiag` | DSL diagnostics (F4/F5, VPI/VCI) | R/W | — | HAR required | Form observed live but not mapped in `ZTEH388XAPI`. No test was started. |
| `sntp` (`hiddenData`) | `sntp_data` | R | `sntp` | covered | hiddenData endpoint, no view arming. |
| `sntp` (`hiddenData`) | `sntp_data` | W | — | HAR required | NTP servers, timezone, and DST. |
| `loginData` | `login_entry`, `logout_entry` | R/W | automatic login, `logout` | covered | Session and local cache. No credentials in the report. |
| `Certificates` | endpoint not found in the current mapping | R/W | — | HAR required | Page is present live but exposes no data in the initial view. Capture it before classifying read/write support. |
| `upgrade` / firmware | firmware upload endpoint | W | — | HAR required | Not implemented. Requires fixtures, backup, `--dry-run`/`--yes`, and separate live validation. |

## Resulting priority gaps

1. **Wi-Fi writes**: radio, SSID/password, visibility, client limit, ACL, and
   scheduling. Reads are covered. Record one HAR for each isolated action.
2. **Firewall/LAN writes**: firewall/DoS toggle, DMZ, DNS hostnames, and a
   dedicated CLI convention for DHCP edit.
3. **Services and sensitive functions**: parental controls, UPnP/DLNA/FTP,
   SNTP, IPv6/EDNS0, EasyMesh, DDNS, and configurable WAN.
4. **High-risk actions**: administrator password, restore, factory reset,
   VoIP/SIP, and firmware upgrade. They require a preventive backup, `--yes`,
   and `--dry-run` where the firmware supports it.

## Source and maintenance

- Endpoints and parent views: `ZTEH388XAPI` constants and `ROADMAP.md`.
- Commands: `README.md` and Typer registration in `h388x_cli/cli.py`.
- Machine-readable catalog: `h388x_cli/coverage.py`, exposed by
  `h388x capabilities` with `schema_version=1`.
- Live state: update after each `h388x discover`. `endpoints.json` stays
  local and gitignored because it may contain serial numbers and authenticated
  samples.
- Comparison: `h388x discover --previous FILE` adds a `comparison` section to
  the report with added, removed, or changed endpoints. Samples and byte
  counts are not treated as differences.
- A row marked "HAR required" becomes "covered" only after a minimal offline
  fixture, read-before-write, dry-run/confirmation for risky actions, and a
  live check that restores the initial state.
