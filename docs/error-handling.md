# Error handling

`h388x-cli` distinguishes a valid empty modem response from an operational failure.
Read operations therefore raise typed exceptions instead of returning `[]`, `{}` or an
empty string when transport, session, HTTP or parsing fails.

## Python API

All operational exceptions inherit from `h388x_cli.errors.H388XError`:

- `TransportError` — the HTTP exchange could not be completed locally.
- `AuthenticationError` — authentication could not be established.
- `SessionExpiredError` — an authenticated request returned `SessionTimeout` and the
  single automatic re-login attempt did not recover it.
- `ProtocolError` — the modem returned an unacceptable HTTP/protocol response.
- `ParseError` — a successful response was malformed or did not match the expected
  H388X payload shape.

A syntactically valid response with no matching instances remains a normal empty list.
Write operations keep their existing `(ok, body)` return contract so callers are not
forced through an incompatible API change.

## CLI exit codes

The installed `h388x` entry point converts `H388XError` exceptions into one concise
human-readable error, or a structured JSON error when `--json` is enabled.

- `0`: command completed successfully.
- `1`: operational failure (authentication/session, transport/protocol/parsing, or a
  command/write failure explicitly handled by the CLI).
- `2`: invalid CLI invocation/arguments, following Click/Typer conventions.

Scripts should use the exit status for success/failure and, when applicable, `--json`
for machine-readable details. They should not interpret an empty table as evidence that
the modem request itself succeeded unless the command exits with status `0`.
