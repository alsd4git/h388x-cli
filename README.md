# H388X-CLI

A command-line interface to manage your ZTE **H388X** modem (TIM HUB+),
firmware family **AGZHM_*** (tested on `AGZHM_1.4.4`).

The goal is to expose every operation that's reasonable to do from the WebUI
directly from the terminal, with table or JSON output.

## Features

| Command | What it does |
|---------|--------------|
| `info` | Model, serial number, firmware/hardware/boot version, build date. |
| `stats` | DSL statistics: status, profile, sync rate (D/U), max attainable rate, SNR margin, attenuation, transmit power, line uptime, FEC errors. Supports `--watch N` for live updates. |
| `wan` | WAN connections: name, status, public IPv4, gateway, DNS, uptime, services. `--all` to include disconnected/unconfigured ones. |
| `clients` | All currently-connected devices (LAN + Wi-Fi merged). `--leases` shows the full DHCP lease table instead. |
| `reboot` | Reboot the modem. `-y` to skip confirmation. |

The global `--json` flag (placed *before* the subcommand) outputs JSON
instead of pretty tables, suitable for piping into `jq` or scripts. With
`stats --watch --json` you get one JSON line per refresh (JSON Lines).

## Installation

Using [uv](https://github.com/astral-sh/uv):

```bash
uv tool install .
```

Or for development:

```bash
uv sync
```

## Configuration

Create a `.env` file (see [`.env.example`](./.env.example)) at the project root:

```env
H388X_PASSWORD=your_admin_password_here
H388X_IP=192.168.1.1     # optional, default 192.168.1.1
H388X_USER=admin         # optional, default admin
```

You can also override any value on the command line:

```bash
h388x stats --ip 192.168.1.254 --user custom_admin --password your_password
```

## Usage

```bash
# Device info
h388x info

# DSL statistics (one-shot)
h388x stats

# DSL statistics, refresh every 2 seconds
h388x stats --watch 2

# WAN connections (only Connected ones)
h388x wan
h388x wan --all          # include disconnected/unconfigured

# Connected devices (LAN + Wi-Fi)
h388x clients
h388x clients --leases   # full DHCP lease table

# Reboot
h388x reboot
h388x reboot -y          # no confirmation

# JSON output (global flag, BEFORE the subcommand)
h388x --json info
h388x --json wan | jq '.[] | select(.name=="INTERNET_VD") | .ip_address'
h388x --json clients | jq '.wifi | length'
h388x --json stats --watch 5      # JSON-lines stream, one per refresh
```

Each command opens a fresh admin session, performs the request, and logs out
cleanly. The H388X allows **only one active admin session at a time**, so
make sure you are logged out from the WebUI before running the CLI.

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

- DSL data endpoint returns SNR / attenuation / power as **deci-units**
  (e.g. `Downstream_noise_margin = 61` ⇒ `6.1 dB`). The CLI converts them
  for display; raw values are preserved in `--json`.
- A "menu navigation" GET (`menuView`) must precede every `menuData` request,
  otherwise the modem returns a `SessionTimeout` payload.
- Each data request must include `Cache-Control: no-cache`.
- Login uses `Password = sha256(password + salt)` (single pass, UTF-8).
- The DHCP endpoint prefixes every `ParaName` with `OBJ_DHCPHOSTINFO_ID.`;
  the CLI strips the prefix transparently.
- The H388X reports **4 WAN instances** (`INTERNET_VD`, `INTERNET_AD`,
  `IPTV_VD`, `IPTV_AD`); on a typical FTTC line only `INTERNET_VD` and
  `IPTV_VD` are `Connected`.
- **Not exposed by this firmware** (probed and confirmed unavailable):
  syslog/system logs, Wi-Fi radio configuration, port-forwarding/NAT rules,
  optical/PON status, byte counters. The corresponding endpoints used by
  other ZTE firmwares (e.g. `wlan_basic_lua.lua`, `optical_info_lua.lua`,
  `eth_interface_status_lua.lua`) all return `SessionTimeout` here.

## Troubleshooting

- **Login failed / "Il sistema non è gestibile"**: the modem allows a single
  admin session. Logout from the WebUI in your browser before running the
  CLI. After repeated failed logins the firmware applies a temporary
  lockout — wait a couple of minutes and retry.
- **`SessionTimeout` errors mid-run**: usually a stale session. The CLI
  re-logs in automatically once; if it still fails, reboot the modem.
- **Tables truncated in narrow terminals**: widen your terminal or use
  `--json` for the full unformatted data.

## Inspirations & Credits

Questo progetto è stato realizzato analizzando e integrando le logiche di
reverse engineering dei seguenti progetti della community:

- **[masoneff3/ha_zteh388x](https://github.com/masoneff3/ha_zteh388x)** —
  Riferimento principale per il protocollo di autenticazione e per gli
  endpoint XML delle statistiche DSL e WAN.
- **[Kioubit/ZTE_H1600-routerAPI](https://github.com/Kioubit/ZTE_H1600-routerAPI)** —
  Riferimento per gli endpoint di reboot (`devmgr_restartmgr_lua.lua`),
  DHCP leases, host LAN/Wi-Fi e gestione dei token CSRF rotanti.
- **[sioakim/zte-router-api](https://github.com/sioakim/zte-router-api)** —
  Riferimento per la lista dispositivi homepage e altri endpoint dei modem
  ZTE F8648P (stessa famiglia firmware).
- **[zte-config-utility](https://github.com/mkst/zte-config-utility)** —
  Struttura generale dei dati dei modem ZTE.
- **[Community Fibra.click](https://fibra.click/)** — Discussioni tecniche
  sui firmware AGZHM del TIM HUB+, in particolare il
  [thread sull'integrazione Home Assistant](https://forum.fibra.click/d/63226-integrazione-home-assistant-tim-hub-zte-h388x/10).
