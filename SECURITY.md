# Security policy

## Supported versions

Security fixes target the latest release and `main`. Older releases may require
an upgrade. The project is currently alpha and tested on TIM HUB+ ZTE H388X
AGZHM_1.4.4; firmware differences may affect behavior.

## Reporting a vulnerability

Use GitHub private vulnerability reporting when enabled:

https://github.com/alsd4git/h388x-cli/security/advisories/new

If private reporting is unavailable, contact the maintainer through an existing
private channel before sending details. Do not open a public issue containing
credentials, exploits against a live modem or unredacted captures.

Include the affected version, firmware, a minimal reproduction, expected
behavior and impact. Use synthetic values and attach only redacted material.
Do not test against devices without their owner's authorization.

## Local credentials and exports

Session caches and modem exports can grant access to the device or expose
network credentials. POSIX files are written with private permissions. On
Windows, access depends on the filesystem ACLs; keep exports in a private user
directory and check access before sharing or synchronizing them.

Follow CONTRIBUTING.md when preparing a HAR or protocol fixture. If a real
credential is exposed, rotate it and invalidate the affected modem session.
