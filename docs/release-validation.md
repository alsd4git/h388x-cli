# Release validation for v0.2.0

Validated on 2026-10-13. Functional changes were reviewed at `eb47a8e` before
the release version and documentation update.

## Source and history

Gitleaks was run locally against every available Git ref using
`gitleaks git --redact --log-opts='--all'`. It reported two findings:

- `81e8530`, `h388x_cli/cli_runtime.py`: an API constructor expression.
- `33090e8`, `h388x_cli/cli.py`: the same API constructor in an older layout.

Both findings were checked manually and are false positives, not embedded
credentials. Gitleaks exits nonzero for these findings. No additional findings
were reported. Checks of historical file names and known modem identifiers
found no committed `.env`, HAR, config backup, firmware, session export or
private modem URL. `.env.example` contains examples only.

These checks cover reachable history in the local checkout, not every external
copy of the repository or deleted server refs. The maintainer's author email
is intentionally retained in Git metadata.

## Code provenance

The maintainer states that almost all implementation was written for this CLI,
with no known license conflicts in the retained code.
The upstream projects credited in README were used as protocol research
references. The incompatible `zte_modem_tools` port was removed before commit
and is absent from the reachable project history. MIT remains the project
license. This records the maintainer's provenance statement and does not claim
an independent legal review of every historical line.

## Functional verification

- Offline suite: 276 tests passed, one opt-in real-device test skipped.
- Local opt-in modem smoke: login, device-information read and logout passed.
  Cache was disabled and no modem configuration was changed. Credentials and
  device identifiers are excluded from this record.
- Ruff lint and formatting passed.
- GitHub Actions on `eb47a8e` passed all ten jobs: Python 3.10 through 3.14,
  coverage, quality and package-install smoke on Linux, Windows and macOS.
  Run: https://github.com/alsd4git/h388x-cli/actions/runs/38379669828

The versioned release commit must pass CI again before the tag is pushed.
The release workflow then checks tag/version equality and ancestry on `main`,
runs quality checks and installs the built wheel before attaching artifacts.
The actual uploaded wheel must be downloaded and smoke-tested after release.

## Visibility

The repository remains private. Public HTTPS installation, branch rulesets
and private vulnerability reporting must be verified separately if visibility
changes later. PyPI publishing is not enabled.
