# H388X-CLI

A command-line interface to manage your ZTE **H388X** modem (TIM HUB+),
firmware family **AGZHM_*** (tested on `AGZHM_1.4.4`).

The goal is to expose every read-only and operational endpoint of the
WebUI directly from the terminal, with table or JSON output.

## Commands

The global `--json` flag (placed *before* the subcommand) outputs JSON
instead of pretty tables, suitable for piping into `jq` or scripts.

### Status & overview

| Command | What it does |
|---------|--------------|
| `info` | Model, serial, firmware/hardware/boot version, build date. |
| `stats` | DSL home-page summary (status, profile, sync rate, SNR margin, attenuation, power, uptime, FEC errors). Supports `--watch N` for live updates. |
| `dsl-interface` | Full DSL PHY view (current/max rates per direction, interleave depth/delay, CRC/FEC counters, encapsulation, Showtime start). |
| `wan` | WAN connections (public IPv4, gateway, DNS, uptime, services). `--all` includes disconnected ones. |
| `mobile-wan` | 3G/4G USB dongle backup status (DongleStatus + operator/signal when plugged). |
| `topology` | EasyMesh topology — controller + agent layers (`MGET_INST_NUM=0` when no satellites). |

### LAN / clients / addressing

| Command | What it does |
|---------|--------------|
| `clients` | LAN + Wi-Fi merged client list. `--leases` shows the full DHCP lease table. |
| `arp` | IPv4 ARP cache per interface. |
| `mac-table` | Bridge L2 forwarding table (MAC ↔ port). |
| `eth` | Ethernet port status (4 LAN + WAN uplink). |
| `dhcp` | DHCPv4 server config + static reservations. |
| `dhcp-reserve-add MAC IP NAME` | Add a static DHCPv4 reservation. IP must be inside the configured pool. |
| `dhcp-reserve-del ID` | Delete a reservation by `_OBJ_InstID` (full path or bare suffix `2`). `-y` to skip confirmation. |
| `dhcp6` | DHCPv6 server + Router Advertisement state. |
| `ipv6-prefix` | DHCPv6-PD pool + static IPv6 prefixes. |
| `dns` | DNS config + bound hostnames (DHCP + manual). |
| `edns0` | EDNS0 client-subnet toggle. |
| `public-lan` | Secondary "public LAN" interface (hotspot/guest IP slot). |

### Wi-Fi

| Command | What it does |
|---------|--------------|
| `wifi` | Radios (2.4 / 5 GHz) + SSID list (main + guest, 8 entries). |
| `wifi-advanced` | Per-radio advanced config (channel, bandwidth, TX power, country). |
| `wifi-ssid-config` | Full SSID config view (hidden flag, max users, security). |
| `wifi-acl` | Per-SSID MAC-filter policy + ACL rules. |
| `wifi-schedule` | Recurring Wi-Fi on/off schedules per AP. |
| `band-steering` | EasyMesh + band-steering master switches. |

### Firewall & access control

| Command | What it does |
|---------|--------------|
| `firewall` | Level, anti-DoS, URL filter master, DMZ summary. |
| `port-forward` | Configured NAT/port-forwarding rules. |
| `port-forward-add DESC PROTO EXT_PORT INTERNAL_IP` | Create a NAT rule. Options: `--int-port`, `--ext-port-end`, `--remote-host[-end]`, `--disable`. |
| `port-forward-del ID` | Delete a NAT rule by `_OBJ_InstID` (full path or bare suffix `9`). `-y` to skip confirmation. |
| `firewall-ipfilter` | User-defined IP-filter rules + priority slot. |
| `firewall-ipfilter-add NAME PROTO` | Add an IP-filter rule. `PROTO` = ICMP/TCP/UDP or 1–255. Options: `--target allow\|deny` (default allow), `--index`, `--disable`, `--ip-version`, `--src-ip/--src-mask`, `--dst-ip/--dst-mask`, `--src-port-min/max`, `--dst-port-min/max`, `--dscp`. |
| `firewall-ipfilter-del ID` | Delete an IP-filter rule by `_OBJ_InstID` (full path or bare suffix `1`). `-y` to skip confirmation. |
| `firewall-urlfilter` | Per-URL filter rules (master toggle in `firewall`). |
| `firewall-urlfilter-add NAME URL` | Add a URL-filter rule (Name 1–32 ASCII, URL 1–128). Needs the master URL filter on in `firewall`. |
| `firewall-urlfilter-del ID` | Delete a URL-filter rule by `_OBJ_InstID` (full path or bare suffix `1`). `-y` to skip confirmation. |
| `parental-control` | Parental-control MAC+schedule bindings. |

### Services

| Command | What it does |
|---------|--------------|
| `voip` | SIP line status (registration + physical TEL bindings). |
| `voip-media` | SIP codec priority per VoIP line (G.722 / G.729 / G.711a). |
| `voip-pos` | VoIP POS (port-on-off) toggles per slot. |
| `upnp` | UPnP IGD state + live port mappings. |
| `dms` | DLNA / DMS media-server config (USB sharing). |
| `ftp` | FTP server state + configured users. |
| `nanocdn` | TIM IPTV multicast→unicast offload runtime stats. |
| `ddns` | DDNS client status. |
| `usb-devs` | Attached USB storage devices. |

### System / admin

| Command | What it does |
|---------|--------------|
| `sntp` | NTP servers, timezone, current local time, DST. |
| `admin-users` | Web admin accounts (username + privilege). |
| `web-timeout` | Web UI idle session timeout (minutes). Add `--set MINUTES` (1–60) to update. |
| `logout` | Explicit modem logout + wipe the cached session for this host. |
| `reboot` | Reboot the modem. `-y` to skip confirmation. |
| `watch INTERVAL CMD…` | Re-run any subcommand every `INTERVAL` seconds (e.g. `h388x watch 5 voip`). Generic Unix `watch(1)`-style wrapper. |

### Discovery (introspection)

| Command | What it does |
|---------|--------------|
| `discover` | Spider the WebUI and dump every reachable `_type=...&_tag=...` endpoint to `endpoints.json` (gitignored, contains modem serial). |

## Installation

Using [uv](https://github.com/astral-sh/uv):

```bash
uv tool install .
```

Or for development:

```bash
uv sync
```

### Shell completion

After installing the `h388x` script (`uv tool install .`), enable
tab-completion for your shell:

```bash
h388x --install-completion        # auto-detects bash / zsh / fish / powershell
```

Restart your shell, then `h388x <TAB><TAB>` lists every subcommand
and `h388x <cmd> --<TAB><TAB>` cycles through its flags. To inspect
the generated script instead of installing it, use
`h388x --show-completion <bash|zsh|fish>`.

Note: completion is wired to the installed `h388x` entry point. When
running the CLI through `uv run python -m h388x_cli.cli` (development
mode) the shell can't detect the program name and completion is not
available — install with `uv tool install .` for that.

## Configuration

Create a `.env` file (see [`.env.example`](./.env.example)) at the project root:

```env
H388X_PASSWORD=your_admin_password_here
H388X_HOST=192.168.1.1   # IP, hostname, or full URL — default 192.168.1.1
H388X_USER=admin         # optional, default admin
```

`H388X_HOST` accepts:

- a bare IP (`192.168.1.1`)
- a hostname (`modem.example.com`, defaults to `http://`)
- a full URL with scheme (`https://modem.example.com:8443`)

`H388X_IP` is still read as a fallback for older configs.

You can also override any value on the command line:

```bash
h388x stats --host 192.168.1.254 --user custom_admin --password your_password
h388x stats --host https://modem.example.com:8443
h388x stats --host https://modem.example.com -k  # --insecure: skip TLS verify
```

## Usage

```bash
# Device info
h388x info

# DSL summary (one-shot) / full PHY view / live refresh
h388x stats
h388x dsl-interface
h388x stats --watch 2

# WAN, clients, leases
h388x wan
h388x wan --all
h388x clients
h388x clients --leases

# Wi-Fi: radios + SSIDs + config
h388x wifi
h388x wifi-advanced
h388x wifi-ssid-config

# Firewall / NAT
h388x firewall
h388x port-forward
h388x firewall-ipfilter

# Mesh topology
h388x topology

# Re-run any subcommand in a loop (Unix watch(1) style)
h388x watch 5 voip                # refresh VoIP every 5 seconds
h388x watch 2 clients --leases    # any sub-flag is forwarded as-is

# Reboot
h388x reboot
h388x reboot -y

# JSON output (global flag, BEFORE the subcommand)
h388x --json info
h388x --json wan | jq '.[] | select(.name=="INTERNET_VD") | .ip_address'
h388x --json clients | jq '.wifi | length'
h388x --json stats --watch 5      # JSON-lines stream, one per refresh
```

Each command authenticates once and **caches the SID cookie** to
`~/.cache/h388x-cli/session-<hash>.json` (0600, per `(host, user)`
pair), so subsequent invocations skip the login handshake. The cache
auto-refreshes on `SessionTimeout`. Run `h388x logout` to clear it
explicitly (e.g. before switching admin user or freeing the modem's
single admin slot).

The H388X allows **only one active admin session at a time**, so log
out from the WebUI before running the CLI.

### Example output

```
            Device Information
┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━┓
┃ Field            ┃ Value               ┃
┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━┩
│ Model            │ H388X               │
│ Serial Number    │ ZTEEGA7PCD0XXXXX    │
│ Software Version │ AGZHM_1.4.4         │
│ Hardware Version │ V10.1.0             │
│ Boot Version     │ V1.0.0              │
│ Firmware Date    │ 2025-05-20 02:23:20 │
└──────────────────┴─────────────────────┘
```

## Notes on AGZHM firmware quirks

- DSL home-page (`stats`) returns SNR / attenuation / power as
  **deci-units** (e.g. `Downstream_noise_margin = 61` ⇒ `6.1 dB`).
  The CLI converts them for display; raw values are preserved in
  `--json`. `dsl-interface` exposes the same scale unchanged.
- A "menu navigation" GET (`menuView`) must precede every `menuData`
  request, otherwise the modem returns a `SessionTimeout` payload.
  Hidden endpoints (`_type=hiddenData`, e.g. `sntp`) skip this step.
- Each data request must include `Cache-Control: no-cache`.
- When using HTTPS / hostname access, the modem also requires
  `Origin` / `Referer` headers that match the host actually used,
  otherwise `menuData` requests fail with `SessionTimeout` even with
  a valid cookie. The CLI sets these automatically.
- Login uses `Password = sha256(password + salt)` (single pass, UTF-8).
- The DHCP endpoint prefixes every `ParaName` with
  `OBJ_DHCPHOSTINFO_ID.`; the CLI strips the prefix transparently.
- The H388X reports **4 WAN instances** (`INTERNET_VD`, `INTERNET_AD`,
  `IPTV_VD`, `IPTV_AD`); on a typical FTTC line only `INTERNET_VD` and
  `IPTV_VD` are `Connected`.
- A handful of `*_homepage_lua.lua` landing endpoints (firewall, USB,
  VoIP, WLAN, accessdev) always return `SessionTimeout`: they arm
  only when reached through real menu navigation. The CLI doesn't
  expose them — equivalent data is fetched via the underlying view
  endpoints instead.

## Testing

Offline test suite (no network, fixtures inline):

```bash
uv run pytest
```

Covers:

- the XML parser (`api._parse_instances`, `_strip_prefix`,
  `_is_session_expired`) including the multi-root case used by
  `voip-media`;
- pydantic alias mapping across a representative set of models;
- end-to-end mocked flow via [`responses`](https://github.com/getsentry/responses)
  for the `menuView → menuData → parse` dance, including the
  auto re-login path on `SessionTimeout`, raw JSON
  (`get_topology`), and the `hiddenData` shortcut (`get_sntp`).

See [`ROADMAP.md`](./ROADMAP.md) for the per-endpoint implementation
checklist.

## Troubleshooting

- **Login failed / "Il sistema non è gestibile"**: the modem allows a
  single admin session. Log out from the WebUI in your browser before
  running the CLI. After repeated failed logins the firmware applies a
  temporary lockout — wait a couple of minutes and retry.
- **`SessionTimeout` errors mid-run**: usually a stale session. The CLI
  re-logs in automatically once; if it still fails, reboot the modem.
- **Empty tables when going through HTTPS / hostname**: make sure
  `H388X_HOST` matches the actual host the modem was reached at — the
  CLI uses it to build the `Origin` / `Referer` headers the firmware
  validates.
- **Tables truncated in narrow terminals**: widen your terminal or use
  `--json` for the full unformatted data.

## Inspirations & Credits

Questo progetto è stato realizzato analizzando e integrando le logiche
di reverse engineering dei seguenti progetti della community:

- **[masoneff3/ha_zteh388x](https://github.com/masoneff3/ha_zteh388x)** —
  Riferimento principale per il protocollo di autenticazione e per gli
  endpoint XML delle statistiche DSL e WAN.
- **[Kioubit/ZTE_H1600-routerAPI](https://github.com/Kioubit/ZTE_H1600-routerAPI)** —
  Riferimento per gli endpoint di reboot (`devmgr_restartmgr_lua.lua`),
  DHCP leases, host LAN/Wi-Fi e gestione dei token CSRF rotanti.
- **[sioakim/zte-router-api](https://github.com/sioakim/zte-router-api)** —
  Riferimento per la lista dispositivi homepage e altri endpoint dei
  modem ZTE F8648P (stessa famiglia firmware).
- **[zte-config-utility](https://github.com/mkst/zte-config-utility)** —
  Struttura generale dei dati dei modem ZTE.
- **[Community Fibra.click](https://fibra.click/)** — Discussioni tecniche
  sui firmware AGZHM del TIM HUB+, in particolare il
  [thread sull'integrazione Home Assistant](https://forum.fibra.click/d/63226-integrazione-home-assistant-tim-hub-zte-h388x/10).
