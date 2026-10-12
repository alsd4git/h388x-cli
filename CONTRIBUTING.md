# Contributing

This project targets the TIM HUB+ ZTE H388X with AGZHM firmware. State your
firmware version when reporting behavior on another release or device.

## Development

Use Python 3.10 or later and `uv`:

```bash
uv sync --locked --dev
uv run ruff check h388x_cli tests
uv run ruff format --check h388x_cli tests
uv run pytest
uv build
```

The default tests run offline. Real-device smoke tests are opt-in; see README
for setup. New behavior should have focused tests for protocol contracts and
failure cases. Keep changes scoped and use Conventional Commits.

## New endpoints and writes

Implement reads before writes. Keep endpoint methods in the appropriate API
domain module, update the capability catalog and WebUI coverage matrix, and
preserve existing command names and JSON contracts.

For a new write, capture one isolated WebUI change and document its request
sequence, field names and firmware. Use disposable values and restore the
initial state after live verification. Coordinate disruptive tests with the
device owner before changing Wi-Fi, WAN, credentials or other network settings.

## Reports and HAR files

Start with the command, firmware, expected result and redacted error. Never
attach a raw HAR, discovery report, session cache or configuration backup.

Before sharing a minimal request/response example, replace:

- passwords, SIP credentials, API keys and authentication hashes;
- cookies, authorization headers, session tokens and download tokens;
- serial numbers, MAC addresses, public IP addresses and remote modem URLs;
- SSIDs, device names, phone numbers and other identifying values.

Check URL query strings, request bodies, response bodies and headers. Replace
values consistently so request relationships remain understandable. Keep only
the requests needed to reproduce the behavior; prefer synthetic fixtures over
live captures. Keep the original capture outside the repository.

Report suspected vulnerabilities privately using SECURITY.md.
