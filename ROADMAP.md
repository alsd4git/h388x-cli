# h388x-cli roadmap

This roadmap tracks public project work. Detailed reverse-engineering notes,
live modem observations, and session handoff material stay outside the Git
history.

## Current state

- Read-only coverage spans WAN, DSL, LAN, DHCP, Wi-Fi, firewall, DNS, IPv6,
  VoIP, UPnP, FTP, DLNA, EasyMesh, mobile WAN, diagnostics, and system status.
- JSON output is available for automation, with stable schema metadata.
- `discover --previous` compares endpoint inventories across runs.
- `capabilities` reports the detected firmware family and coverage summary.
- Safe write support includes web-session timeout, port forwarding, DHCP
  reservations, firewall IP/URL rules, DNS servers distributed by DHCP, and
  device naming through reservations.
- The test suite runs offline with mocked modem responses.

## Near-term work

1. Keep the read-only API and JSON schema stable.
2. Improve error types, exit-code documentation, timeout handling, cache
   permissions, and coverage reporting in CI.
3. Add fixtures and HAR-backed implementations for missing Wi-Fi, firewall,
   DMZ, DHCP, DNS, scheduling, ACL, and service-management writes.
4. Add declarative snapshot diff and plan/apply workflows.
5. Document automation patterns for cron, Home Assistant, and similar tools.

## Higher-risk work

Administrator password changes, configuration restore, factory reset, VoIP/SIP
changes, firmware updates, WAN changes, and disruptive Wi-Fi changes require a
backup, explicit confirmation, dry-run support where possible, and a separate
live validation plan with out-of-band access.

## Development workflow

- Keep new endpoint work read-first and fixture-backed.
- Record one isolated WebUI change in a HAR before implementing a write.
- Validate writes on disposable values, then restore the initial modem state.
- Never commit credentials, public IPs, modem identifiers, or live endpoint
  URLs.
