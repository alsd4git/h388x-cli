# Changelog

All notable changes to `h388x-cli` will be documented in this file.

The project follows Semantic Versioning-style releases while the command and JSON interfaces are still stabilizing.

## [Unreleased]

### Fixed

- Keep authentication, unexpected empty-response and write-precondition errors
  machine-readable in JSON mode.
- Preserve typed operational failure codes during device imports without
  exposing raw exception messages.

- Avoid Unicode encoding failures when displaying CLI output on legacy Windows
  terminals or pipes with limited character sets.

- Require explicit `--yes` for destructive commands in JSON and non-interactive
  mode, before contacting the modem.
- Protect device reservation exports with private permissions and no-overwrite
  semantics.
- Load user configuration and the current directory's `.env` using explicit
  paths while preserving process environment overrides.
- Replace raw write-error responses with token-free summaries and numeric modem
  error IDs, including bulk device failures.

- Ignore session caches with invalid JSON structures or invalid token/cookie types.
- Write session caches through unique private temporary files and replace them
  atomically, preserving the previous cache when replacement fails.

### Added

- Verify that release tags point to commits on `main` before publishing.
- Run package install/entry-point smoke checks on Windows and macOS as well as
  Linux.

- Public HTTPS installation examples, contribution guidelines, a security
  reporting policy and redaction prompts in issue templates.
- GitHub remote and repository protection guidance for releases and publication.

## [0.1.0] - 2026-10-05

Initial tagged development release.

### Added

- Typed operational error hierarchy for transport, session, protocol and parsing failures.
- Centralized validation for DHCP reservations, port forwarding and firewall write operations.
- Regression coverage for bulk preflight/partial failures, HTTP/parser failures, discovery session recovery and watch/logout behavior.
- Coverage reporting and clean wheel install smoke tests.
- Tag-driven GitHub Release workflow and an `uv`-first release guide.
- Published wheel and source distribution attached to the GitHub Release.

### Changed

- Standardized package metadata and project naming around **TIM HUB+ ZTE H388X**.
- Expanded CI to Python 3.10 through 3.14 and modernized GitHub Actions/uv setup.
- `devices import` now validates the complete plan before writing, stops on the first failed write and reports partial application explicitly.
- Mutating write APIs validate known protocol/WebUI constraints before contacting the modem.
- Read APIs no longer disguise transport/session/protocol/parser failures as empty data.
- Discovery resolves relative assets correctly, avoids substring-based action false positives and recovers one expired session safely.
- Generic `watch` propagates child failures by default; `--keep-going` is an explicit opt-in.
- `logout` can release a valid cached session without requiring the admin password again.

### Verified

- Release workflow passed Ruff, 240 tests (1 opt-in real-device test skipped), package build, clean Python 3.14 wheel installation, CLI smoke, and metadata/tag checks.
- The actual private GitHub Release wheel was downloaded with `gh`, installed with `uv tool install`, and the installed `h388x --help` entry point was verified on Windows.
