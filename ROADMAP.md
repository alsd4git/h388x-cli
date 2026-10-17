# h388x-cli roadmap

This roadmap tracks public project work. Detailed reverse-engineering notes,
live modem observations, and session handoff material stay outside the Git
history.

## Current state

- Read-only coverage spans WAN, DSL, LAN, DHCP, Wi-Fi, firewall, DNS, IPv6,
  VoIP, UPnP, FTP, DLNA, EasyMesh, mobile WAN, diagnostics, and system status.
- JSON output is available for automation, with stable schema metadata and
  explicit operational error semantics for transport, authentication/session,
  HTTP/protocol, and parsing failures.
- `discover --previous` compares endpoint inventories across runs.
- `capabilities` reports the detected firmware family plus versioned
  `schema_version=2` coverage states (`none`, `partial`, `complete`) with
  observed/missing endpoint evidence.
- Safe write support includes web-session timeout, port forwarding, DHCP
  reservations, firewall IP/URL rules, DNS servers distributed by DHCP, and
  device naming through reservations. Mutating workflows are validation-first
  and report failed or partially applied bulk operations explicitly.
- The API/CLI internals are split into transport/runtime and domain modules
  while keeping the public `ZTEH388XAPI` and CLI command surface stable.
- The offline test suite is fixture/mocking based. CI covers Python 3.10-3.14,
  Ruff lint/format, coverage, package build, and clean wheel-install smoke
  checks.
- `v0.2.0` is published as a GitHub Release. The tag, release workflow, wheel,
  source distribution, and installation from the actual private Release wheel
  have all been validated end-to-end.

## Near-term work

1. Keep the read-only API and JSON schemas stable. Add regression tests for
   meaningful behavior and raise coverage gates only when useful tests justify
   it.
2. Add a dedicated DHCP reservation edit CLI and extend the existing
   validation-first model into declarative snapshot/diff/plan/apply workflows.
3. Add fixtures and HAR-backed implementations for missing Wi-Fi, firewall,
   DMZ, DHCP, DNS, scheduling, ACL, and service-management writes.
4. Document automation patterns for cron, Home Assistant, and similar tools.

## Higher-risk work

Administrator password changes, configuration restore, factory reset, VoIP/SIP
changes, firmware updates, WAN changes, and disruptive Wi-Fi changes require a
backup, explicit confirmation, dry-run support where possible, and a separate
live validation plan with out-of-band access.

## Development workflow

- Keep new endpoint work read-first and fixture-backed.
- Record one isolated WebUI change in a HAR before implementing a write.
- Validate writes on disposable values, then restore the initial modem state.
- Add tests for real contracts and regressions, not to chase an arbitrary
  coverage percentage.
- Never commit credentials, public IPs, modem identifiers, or live endpoint
  URLs.
