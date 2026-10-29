# Full usage guide

[Back to the project overview](../README.md).

# H388X-CLI

[![CI](https://github.com/alsd4git/h388x-cli/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/alsd4git/h388x-cli/actions/workflows/tests.yml)
[![Latest release](https://img.shields.io/github/v/release/alsd4git/h388x-cli)](https://github.com/alsd4git/h388x-cli/releases)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)

A command-line interface to manage your ZTE **H388X** modem (TIM HUB+),
firmware family **AGZHM_*** (tested on `AGZHM_1.4.4`).

Inspect modem status and manage supported settings from the terminal.
Commands return readable tables or JSON for scripts. Firmware support is
specific to the AGZHM family. The CLI does not support every H388X firmware.

## Quick start

You need Python 3.10 or later, [uv](https://docs.astral.sh/uv/getting-started/installation/),
access to your modem's local network and its WebUI administrator credentials.
Firmware differences matter; see the [AGZHM firmware notes](#notes-on-agzhm-firmware-quirks).

```bash
uv tool install "git+https://github.com/alsd4git/h388x-cli.git@v0.2.1"
h388x --help
```

Set `H388X_PASSWORD` in your process environment or a private configuration file
using the [configuration guide](#configuration). `H388X_HOST` defaults to
`192.168.1.1`; set it if your modem uses another address. Avoid putting the
password in command-line arguments or shell history.

Read device information without changing modem settings:

```bash
h388x --json info
```

The raw output includes your serial number. Keep it private. For a shareable
subset, the example below uses [jq](https://jqlang.org/) to replace the serial
and omit all other fields. Captured from a real H388X on 2026-10-27; only the
serial was replaced, and no network settings were changed:

```console
$ h388x --json info | jq '{model, serial_number: "REDACTED", software_version}'
{
  "model": "H388X",
  "serial_number": "REDACTED",
  "software_version": "AGZHM_1.4.4"
}
```

Continue with the [command reference](#command-reference) or the
[WebUI coverage inventory](webui-coverage.md). This static walkthrough
requires no animation or video player.

## Command reference

The global `--json` flag (placed *before* the subcommand) outputs JSON
instead of pretty tables, suitable for piping into `jq` or scripts.

### Status & overview

| Command | What it does |
|---------|--------------|
| `info` | Model, serial, firmware/hardware/boot version, build date. |
| `health` | One-shot status overview (info + DSL + WAN + VoIP + mesh). |
| `stats` | DSL home-page summary (status, profile, sync rate, SNR margin, attenuation, power, uptime, FEC errors). Supports `--watch N` for live updates. |
| `dsl-interface` | Full DSL PHY view (current/max rates per direction, interleave depth/delay, CRC/FEC counters, encapsulation, Showtime start). |
| `wan` | WAN connections (public IPv4, gateway, DNS, uptime, services). `--all` includes disconnected ones. |
| `renew-ip` | Not available on the observed AGZHM_1.4.4 firmware: WAN is read-only and no reliable reconnect/renew action was found. The `reboot` fallback interrupts all connectivity. |
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
| `devices` | Unified device view: connected clients (LAN + Wi-Fi) merged with DHCP reservations by MAC, showing observed DHCP hostname vs assigned name, online/reserved. |
| `devices export [FILE]` | Export reservations as portable JSON `[{mac, ip, name}]` (stdout if FILE omitted). |
| `devices import FILE` | Apply names from JSON idempotently by MAC (add/edit, never deletes). `--dry-run` previews the plan. |
| `devices set MAC NAME` | Name a device: edit its reservation or create one (IP from `--ip` or the observed DHCP address). |
| `devices clear MAC` | Remove a device's reservation (`-y` to skip confirmation). |
| `devices edit` | Interactive naming device-by-device (Enter=keep, name=set/rename, `-`=clear; single confirm before writing). |
| `dhcp6` | DHCPv6 server + Router Advertisement state. |
| `ipv6-prefix` | DHCPv6-PD pool + static IPv6 prefixes. |
| `dns` | DNS config + bound hostnames (DHCP + manual). |
| `dns-set DNS1` | Set the DNS servers handed to LAN clients via DHCP. `--dns2`, or `--from-wan` for the ISP DNS. Existing leases keep old DNS until renewal (non-disruptive). |
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
| `port-forward-toggle ID` | Enable/disable a NAT rule (keeps all other fields). `--on`/`--off` to force; default flips current. |
| `port-forward-edit ID` | Edit fields of an existing NAT rule (only the flags you pass change). Options: `--desc`, `--protocol`, `--ext-port`, `--ext-port-end`, `--client`, `--int-port`, `--remote-host[-end]`, `--on`/`--off`. |
| `firewall-ipfilter` | User-defined IP-filter rules + priority slot. |
| `firewall-ipfilter-add NAME PROTO` | Add an IP-filter rule. `PROTO` = ICMP/TCP/UDP or 1–255. Options: `--target allow\|deny` (default allow), `--index`, `--disable`, `--ip-version`, `--src-ip/--src-mask`, `--dst-ip/--dst-mask`, `--src-port-min/max`, `--dst-port-min/max`, `--dscp`. |
| `firewall-ipfilter-del ID` | Delete an IP-filter rule by `_OBJ_InstID` (full path or bare suffix `1`). `-y` to skip confirmation. |
| `firewall-ipfilter-toggle ID` | Enable/disable an IP-filter rule (keeps all other fields). `--on`/`--off` to force; default flips current. |
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
| `config backup [FILE]` | Download the full modem configuration backup (`config.bin`). Read-only; defaults to `config-YYYYmmdd-HHMMSS.bin`. Keep a snapshot before risky changes. |
| `ping HOST` | Ping a host **from the modem** (runs on the gateway). Count/size/timeout are fixed server-side. |
| `traceroute HOST` | Traceroute to a host **from the modem**. `-m/--max-hops`, `--timeout`, `--protocol` (UDP/ICMP). |
| `reboot` | Reboot the modem. `-y` to skip confirmation. |
| `watch INTERVAL CMD…` | Re-run any subcommand every `INTERVAL` seconds (e.g. `h388x watch 5 voip`). Generic Unix `watch(1)`-style wrapper. |

### Discovery (introspection)

| Command | What it does |
|---------|--------------|
| `discover` | Spider the WebUI and dump every reachable `_type=...&_tag=...` endpoint to `endpoints.json` (gitignored, contains modem serial). `--previous FILE` adds a deterministic added/removed/changed comparison. |
| `capabilities` | Show firmware identity, the versioned WebUI capability catalog, coverage status counts, and (when `endpoints.json` exists) which endpoint tags were observed. |

The current page/endpoint/CLI coverage inventory is maintained in
[`docs/webui-coverage.md`](webui-coverage.md). It separates implemented
reads and writes from actions that still require a single-change HAR.

The machine-readable source used by `capabilities` is kept in
`h388x_cli/coverage.py`; its output includes `schema_version` so automation
can reject incompatible formats explicitly.

### Sensitive local output

`devices export FILE` creates a private file and refuses to overwrite an
existing path. Its JSON success response identifies the output file. Omitting
FILE still writes the reservation array to stdout.

Delete commands, `devices clear` and `reboot` require `--yes` when using
`--json` or non-interactive input. JSON changes output formatting only; it
does not authorize a destructive operation. See
[error handling](error-handling.md) for failure semantics.

`discover` reports contain modem identifiers plus samples of authenticated WebUI
responses; configuration backups can contain credentials or other private modem
settings. Both commands write new files with private permissions and refuse to
overwrite an existing path. Conventional names such as `endpoints*.json`,
`h388x-discovery*.json`, `config-*.bin`, and `h388x-config*.bin` are ignored by
this repository.

If you choose an arbitrary custom `--output` or backup filename, treat that file
as sensitive and add an explicit local ignore rule before working with Git. A
`.gitignore` cannot safely anticipate every custom filename.

## Installation

### Tagged release with uv (recommended)

Install the released tag over HTTPS without a
GitHub account or SSH key:

```bash
uv tool install "git+https://github.com/alsd4git/h388x-cli.git@v0.2.1"
uvx --from "git+https://github.com/alsd4git/h388x-cli.git@v0.2.1" h388x --help
```

If you prefer SSH and have configured GitHub SSH access, pin the tool to an
actual released tag:

```bash
uv tool install "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.2.1"
```

For a one-off invocation without keeping a persistent tool environment:

```bash
uvx --from "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.2.1" h388x --help
```

`uvx` is an alias for `uv tool run`; both commands create an isolated tool
environment. The SSH URL deliberately uses the GitHub `git` user, as required
for SSH authentication.

### Published GitHub Release asset

The wheel can also be installed directly:

```bash
uv tool install "https://github.com/alsd4git/h388x-cli/releases/download/v0.2.1/h388x_cli-0.2.1-py3-none-any.whl"
```

The `v0.2.1` Release publishes both a wheel and source distribution. For a
private repository, the verified asset-install flow uses an authenticated
GitHub CLI session to download the wheel, then installs that local artifact with
`uv`:

```bash
gh release download v0.2.1 -R alsd4git/h388x-cli -p "h388x_cli-0.2.1-py3-none-any.whl"
uv tool install ./h388x_cli-0.2.1-py3-none-any.whl
h388x --help
```

For a one-off check directly from the downloaded wheel:

```bash
uvx --from ./h388x_cli-0.2.1-py3-none-any.whl h388x --help
```

On Windows, if `uv tool install` succeeds but `h388x` is not found, run
`uv tool update-shell` once and reopen the terminal so the uv tool directory
is added to `PATH`.

### Local development

```bash
git clone git@github.com:alsd4git/h388x-cli.git
cd h388x-cli
uv sync --locked --dev
uv run h388x --help
```

To install the current checkout as a persistent local tool while developing:

```bash
uv tool install .
```

Release creation and versioning are documented in [`RELEASING.md`](../RELEASING.md).

### Shell completion

After installing the `h388x` script as a persistent tool, enable
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
available — install the release (or current checkout) as a persistent tool for that.

## Configuration

The CLI loads configuration in this order (higher entries take precedence):

1. Process environment variables.
2. A `.env` file in the current working directory.
3. `$XDG_CONFIG_HOME/h388x-cli/config.env`, or
   `~/.config/h388x-cli/config.env` when `XDG_CONFIG_HOME` is unset or empty.

Paths are explicit: the CLI does not search parent directories for `.env` files.
For a project-local setup, create `.env` in the directory where you run the CLI
(see [`.env.example`](../.env.example)):

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
h388x stats --host 192.168.1.254 --user custom_admin
h388x stats --host https://modem.example.com:8443
h388x stats --host https://modem.example.com -k  # --insecure: skip TLS verify
```

Avoid passing passwords on the command line in normal use: they can be saved
in shell history or exposed to other local processes. Prefer `H388X_PASSWORD`
in a `.env` file (which is ignored by Git) or in the command environment.

### Optional real-device smoke test

The regular test suite never contacts a modem. To verify the login flow and a
single **read-only** device-information request against your own H388X, create
the `.env` file above and explicitly opt in:

```bash
H388X_REAL_SMOKE=1 uv run pytest -m real_device
```

This test does not change modem settings and disables the CLI session cache,
but it does create an admin session. Log out of the WebUI first (the modem
allows only one admin session) and run `h388x logout` afterwards if you want to
free that slot immediately. For a self-signed HTTPS modem endpoint, add
`H388X_INSECURE=1` only on a trusted local network.

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

See [`docs/webui-coverage.md`](webui-coverage.md) for the detailed
endpoint/command coverage inventory and [`ROADMAP.md`](../ROADMAP.md) for future
priorities.

## License

Released under the [MIT License](../LICENSE).

## Contributing and security

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development checks, endpoint
contributions and HAR redaction. Report vulnerabilities privately as described
in [SECURITY.md](../SECURITY.md).

## Troubleshooting

- **Login failed / "The system cannot be managed"**: the modem allows a
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

This project was built by studying and integrating reverse-engineering work
from the following community projects:

- **[masoneff3/ha_zteh388x](https://github.com/masoneff3/ha_zteh388x)** —
  Primary reference for the authentication protocol and the XML endpoints
  used for DSL and WAN statistics.
- **[Kioubit/ZTE_H1600-routerAPI](https://github.com/Kioubit/ZTE_H1600-routerAPI)** —
  Reference for the reboot endpoint (`devmgr_restartmgr_lua.lua`), DHCP
  leases, LAN/Wi-Fi hosts, and rotating CSRF tokens.
- **[sioakim/zte-router-api](https://github.com/sioakim/zte-router-api)** —
  Reference for the homepage device list and other endpoints on ZTE F8648P
  modems from the same firmware family.
- **[zte-config-utility](https://github.com/mkst/zte-config-utility)** —
  General structure of ZTE modem data.
- **[Fibra.click community](https://fibra.click/)** — Technical discussions
  about TIM HUB+ AGZHM firmware, especially the
  [Home Assistant integration thread](https://forum.fibra.click/d/63226-integrazione-home-assistant-tim-hub-zte-h388x/10).
