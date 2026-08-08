# Matrice di copertura WebUI

Inventario del firmware TIM HUB+ **AGZHM_1.4.4** costruito a partire dagli
endpoint presenti in `h388x_cli/api.py`, dal report di discovery locale e dai
comandi documentati in `README.md`.

La matrice è intenzionalmente conservativa: “coperta” significa che il
percorso è implementato nel CLI e ha una lettura offline testata; per le
scritture significa anche che il POST è stato verificato dal codice/API. Una
funzione non viene marcata come “non disponibile sul firmware TIM” senza una
prova live o una voce WebUI osservata come assente.

## Legenda

| Stato | Significato |
| --- | --- |
| coperta | Endpoint e funzione CLI disponibili; fixture/test offline presenti quando applicabile. |
| parzialmente coperta | La lettura è disponibile, ma una o più azioni della pagina non lo sono ancora. |
| da acquisire tramite HAR | Manca un mapping POST affidabile o una funzione non è ancora esposta dal CLI; prima di implementarla serve una registrazione di una sola modifica. |
| non disponibile sul firmware TIM | La funzione è stata verificata come assente sul firmware target. Nessuna riga usa questo stato senza evidenza. |

`R` = lettura, `W` = scrittura/azione, `R/W` = entrambe.

## Matrice pagina → endpoint → comando

| Pagina WebUI (`menuView`) | Endpoint (`menuData`/`hiddenData`) | Operazione | Comando CLI | Stato | Note |
| --- | --- | :---: | --- | --- | --- |
| `statusMgr` | `devmgr_statusmgr_lua.lua` | R | `info` | coperta | Identità modem, seriale e firmware. |
| `dslWanStatus` | `dsl_interface_status_lua.lua` | R | `stats`, `dsl-interface` | coperta | Summary e PHY condividono il payload. |
| `dslWanStatus` | `wan_internet_lua.lua` | R | `wan` | coperta | Include le connessioni non attive con `wan --all`. |
| `localNetStatus` | `accessdev_landevs_lua.lua` | R | `clients` | coperta | Client LAN. |
| `localNetStatus` | `accessdev_ssiddev_lua.lua` | R | `clients` | coperta | Client Wi-Fi; flusso `localNetStatus → wlan_status_lua.lua → accessdev_ssiddev_lua.lua` validato nel codice. |
| `localNetStatus` | `eth_lanstatus_lua.lua` | R | `eth` | coperta | Porte LAN. |
| `localNetStatus` | `publiclan_status_lua.lua` | R | `public-lan` | coperta | Slot public/guest LAN. |
| `localNetStatus` | `usb_usbdevs_lua.lua` | R | `usb-devs` | coperta | Vuoto quando non c’è un dispositivo USB. |
| `wlanBasic` | `wlan_basiconoff_lua.lua` | R | `wifi` | coperta | Stato radio 2.4/5 GHz. |
| `wlanBasic` | `wlan_status_lua.lua` | R | `wifi` | coperta | SSID, sicurezza e stato AP. |
| `wlanBasic` | `wlan_basicadconf_lua.lua` | R | `wifi-advanced` | coperta | Canale, banda, potenza e paese. |
| `wlanBasic` | `wlan_sssidconf_lua.lua` | R | `wifi-ssid-config` | coperta | Include visibilità SSID e `MaxUserNum`. |
| `wlanBasic` | `wlan_basiconoff_lua.lua` | W | — | da acquisire tramite HAR | Toggle radio Wi-Fi. |
| `wlanBasic` | `wlan_sssidconf_lua.lua` | W | — | da acquisire tramite HAR | SSID, password, visibilità e massimo client. |
| `wlanAdvanced` | `wlan_basicadconf_lua.lua` | W | — | da acquisire tramite HAR | Modifica configurazione avanzata radio. |
| `filterCriteria` | `firewall_filterglobal_m.lua` | R | `firewall` | coperta | Toggle globale URL filtering e target. |
| `filterCriteria` | `firewall_filterglobal_m.lua` | W | — | da acquisire tramite HAR | Toggle firewall/URL filtering. |
| `filterCriteria` | `firewall_ipfilter_m.lua` | R/W | `firewall-ipfilter`, `firewall-ipfilter-add`, `firewall-ipfilter-del`, `firewall-ipfilter-toggle` | coperta | Regole IP e toggle enable. |
| `filterCriteria` | `firewall_ipfilter_priority_lua.lua` | R | `firewall-ipfilter` | coperta | Priorità regole. |
| `filterCriteria` | `firewall_urlfilter_m.lua` | R/W | `firewall-urlfilter`, `firewall-urlfilter-add`, `firewall-urlfilter-del` | coperta | Regole URL; il master switch resta nella riga globale. |
| `firewall` | `firewall_config_lua.lua` | R | `firewall` | coperta | Livello firewall. |
| `firewall` | `firewall_dos_lua.lua` | R | `firewall` | coperta | Anti-DoS e soglie. |
| `firewall` | `firewall_config_lua.lua`, `firewall_dos_lua.lua` | W | — | da acquisire tramite HAR | Cambio livello e opzioni anti-DoS. |
| `dmzMenu` | `firewall_dmz_m.lua` | R | `firewall` | coperta | Stato DMZ e client interno. |
| `dmzMenu` | `firewall_dmz_m.lua` | W | — | da acquisire tramite HAR | Gestione DMZ. |
| `portForwardingMenu` | `firewall_portforwarding_m.lua` | R/W | `port-forward`, `port-forward-add`, `port-forward-del`, `port-forward-toggle`, `port-forward-edit` | coperta | Add/delete/toggle/edit verificati tramite API. |
| `dns` | `dns_localdns_lua.lua` | R | `dns` | coperta | Configurazione DNS locale. |
| `dns` | `dns_hostname_lua.lua` | R | `dns` | coperta | Hostname associati. |
| `dns` / `lanMgrIpv4` | `dhcp4s_dhcpbasiccfg_lua.lua` | R/W | `dhcp`, `dns-set` | coperta | `dns-set` modifica i DNS consegnati via DHCP, non il resolver locale. |
| `dns` | `dns_hostname_lua.lua` | W | — | da acquisire tramite HAR | Edit/add degli hostname statici. |
| `macTable` | `macinfo_mactable_lua.lua` | R | `mac-table` | coperta | Bridge FDB. |
| `arpTable` | `arp_arptable_lua.lua` | R | `arp` | coperta | Cache ARP IPv4. |
| `ddns` | `ddns_lua.lua` | R | `ddns` | coperta | Stato client DDNS. |
| `ddns` | `ddns_lua.lua` | W | — | da acquisire tramite HAR | Configurazione provider/credenziali. |
| `ethWanStatus` | `eth_interface_status_lua.lua` | R | `eth` | coperta | Uplink WAN Ethernet. |
| `lanMgrIpv4` | `dhcp4s_dhcpbasiccfg_lua.lua` | R | `dhcp` | coperta | Server DHCPv4. |
| `lanMgrIpv4` | `dhcp4s_dhcpbinding_m.lua` | R/W | `dhcp`, `devices set`, `devices clear`, `devices import`, `devices edit`, `dhcp-reserve-add`, `dhcp-reserve-del` | coperta | Prenotazioni DHCP, incluso edit read-modify-write. |
| `lanMgrIpv4` | `dhcp4s_dhcpbinding_m.lua` | W | — | parzialmente coperta | Il CLI non ha ancora un comando dedicato `dhcp-reserve-edit`; l’edit è raggiungibile dalle azioni `devices`. |
| `lanMgrIpv6` | `dhcp6s_dhcpserver_lua.lua`, `dhcp6s_hostinfo_lua.lua`, `ra_raservice_lua.lua` | R | `dhcp6` | coperta | DHCPv6 e Router Advertisement. |
| `lanMgrIpv6` | `prefix_prefixpool_lua.lua`, `prefix_staticprefix_lua.lua` | R | `ipv6-prefix` | coperta | Prefix delegation e prefissi statici. |
| `lanMgrIpv6` | `dhcp6s_dhcpserver_lua.lua`, `ra_raservice_lua.lua`, `prefix_staticprefix_lua.lua` | W | — | da acquisire tramite HAR | Toggle/configurazione IPv6 e RA. |
| `smEdns0` | `edns0_lua.lua` | R | `edns0` | coperta | Stato EDNS0. |
| `smEdns0` | `edns0_lua.lua` | W | — | da acquisire tramite HAR | Toggle EDNS0. |
| `voipStatus` | `voip_voipstatus_m.lua` | R | `voip` | coperta | Registrazione linee SIP. |
| `flexibleBind` | `voip_flexiblebinding_lua.lua` | R | `voip` | coperta | Binding fisico TEL. |
| `sipMedia` | `voip_sipmedia_lua.lua` | R | `voip-media` | coperta | Codec e priorità per linea. |
| `posOnoff` | `voip_posonoff_lua.lua` | R | `voip-pos` | coperta | Toggle POS per slot. |
| `voipStatus` / `sipMedia` | endpoint SIP corrispondenti | W | — | da acquisire tramite HAR | Credenziali, codec e configurazione SIP/VoIP. Azione sensibile. |
| `upnp` | `upnp_upnp_m.lua`, `upnp_portmapping_lua.lua` | R | `upnp` | coperta | Stato e port mapping dinamici. |
| `upnp` | stessi endpoint | W | — | da acquisire tramite HAR | Toggle UPnP e gestione mapping persistenti. |
| `dms` | `dms_dms_lua.lua` | R | `dms` | coperta | DLNA/media server. |
| `dms` | `dms_dms_lua.lua` | W | — | da acquisire tramite HAR | Configurazione DLNA. |
| `ftp` | `ftp_ftpserver_m.lua` | R | `ftp` | coperta | Server FTP e utenti. |
| `ftp` | `ftp_ftpserver_m.lua` | W | — | da acquisire tramite HAR | Toggle FTP e gestione utenti. |
| `mabrNanoCDN` | `nanocdn_lua.lua` | R | `nanocdn` | coperta | Statistiche runtime TIM IPTV. |
| `mmTopology` | `topo_lua.lua` | R | `topology`, `health` | coperta | Payload JSON EasyMesh. |
| `wlanBssSteeringOnoff` | `wlan_BssSteeringOnoff_lua.lua` | R | `band-steering` | coperta | EasyMesh e band steering master switch. |
| `wlanBssSteeringOnoff` | `wlan_BssSteeringOnoff_lua.lua` | W | — | da acquisire tramite HAR | Toggle EasyMesh/band steering. |
| `WlanWiFiSchedule` | `wlan_wifi_schedule_lua.lua` | R | `wifi-schedule` | coperta | Schedules ricorrenti. |
| `WlanWiFiSchedule` | `wlan_wifi_schedule_lua.lua` | W | — | da acquisire tramite HAR | Creazione/modifica/disabilitazione schedule. |
| `wlanAdvanced` | `wlan_macfilteraclpolicy_lua.lua`, `wlan_macfilterrule_m.lua` | R | `wifi-acl` | coperta | Policy e regole ACL Wi-Fi. |
| `wlanAdvanced` | `wlan_macfilteraclpolicy_lua.lua`, `wlan_macfilterrule_m.lua` | W | — | da acquisire tramite HAR | Gestione ACL Wi-Fi. |
| `parentCtrl` | `firewall_parentctrl_lua.lua` | R | `parental-control` | coperta | Binding MAC/schedule. |
| `parentCtrl` | `firewall_parentctrl_lua.lua` | W | — | da acquisire tramite HAR | Parental control completo. |
| `accountMgr` | `devauth_accountmgr_lua.lua` | R | `admin-users` | coperta | Account e privilegi; password non viene restituita. |
| `accountMgr` | `devauth_accountmgr_lua.lua` | W | — | da acquisire tramite HAR | Cambio password amministratore. Azione sensibile. |
| `loginTimeoutMgr` | `web_login_timeout_lua.lua` | R/W | `web-timeout`, `web-timeout --set MINUTES` | coperta | Timeout 1–60 minuti. |
| `wan3gStatus` | `wwan_mobile_status_lua.lua` | R | `mobile-wan` | coperta | Dongle e stato rete mobile. |
| `usrCfgMgr` | `do_download_usercfg.lua` | R | `config backup` | coperta | Backup binario; output locale con permessi restrittivi. |
| `usrCfgMgr` | endpoint restore configurazione | W | — | da acquisire tramite HAR | Restore; richiede backup preventivo e conferma esplicita. |
| `rebootAndReset` | `devmgr_restartmgr_lua.lua` | W | `reboot` | coperta | POST verificato; richiede conferma salvo `-y`. |
| `rebootAndReset` | endpoint reset/factory | W | — | da acquisire tramite HAR | Reset di fabbrica; azione sensibile. |
| `networkDiag` | `networkdiag_ping_lua.lua` | R/W | `ping` | coperta | Diagnostica asincrona dal modem; non modifica configurazione. |
| `networkDiag` | `networkdiag_traceroute_lua.lua` | R/W | `traceroute` | coperta | Diagnostica asincrona dal modem; non modifica configurazione. |
| `sntp` (`hiddenData`) | `sntp_data` | R | `sntp` | coperta | Endpoint hiddenData, senza arming di una view. |
| `sntp` (`hiddenData`) | `sntp_data` | W | — | da acquisire tramite HAR | Server NTP, timezone e DST. |
| `loginData` | `login_entry`, `logout_entry` | R/W | login automatico, `logout` | coperta | Sessione e cache locale; nessuna credenziale nel report. |
| `upgrade` / firmware | endpoint di upload firmware | W | — | da acquisire tramite HAR | Non implementato; richiede fixture, backup, `--dry-run`/`--yes` e validazione live separata. |

## Gap prioritari risultanti

1. **Wi-Fi write**: radio, SSID/password, visibilità, client cap, ACL e
   scheduling. Sono letture già coperte; serve una HAR per ciascuna azione
   isolata.
2. **Firewall/LAN write**: toggle firewall/DoS, DMZ, hostname DNS e una
   convenzione CLI dedicata per l’edit DHCP.
3. **Servizi e funzioni sensibili**: parental control, UPnP/DLNA/FTP, SNTP,
   IPv6/EDNS0, EasyMesh, DDNS e WAN configurabile.
4. **Azioni ad alto rischio**: password admin, restore, factory reset, VoIP/SIP
   e firmware upgrade. Devono condividere backup preventivo, conferma `--yes`
   e `--dry-run` dove il firmware lo consente.

## Provenienza e aggiornamento

- Endpoint e parent view: costanti `ZTEH388XAPI` e `ROADMAP.md`.
- Comandi: `README.md` e registrazione Typer in `h388x_cli/cli.py`.
- Stato live: da aggiornare dopo ogni discovery con `h388x discover`; il file
  `endpoints.json` resta locale/gitignored perché può contenere seriale e
  campioni autenticati.
- Una riga “da acquisire tramite HAR” passa a “coperta” solo dopo: fixture
  offline minima, lettura prima della scrittura, dry-run/conferma per azioni
  rischiose e verifica live con ripristino dello stato iniziale.
