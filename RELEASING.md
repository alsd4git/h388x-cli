# Releasing h388x-cli

`h388x-cli` uses `vMAJOR.MINOR.PATCH` tags and GitHub Releases. Development,
validation and packaging use `uv`; publishing to PyPI is intentionally not enabled.

## Before tagging

A release tag must point to a commit already merged into `main`. Do not tag a feature
branch or an unmerged pull request.

1. Update `project.version` in `pyproject.toml`.
2. Move completed entries from `[Unreleased]` into the new version section in
   `CHANGELOG.md`.
3. Refresh and verify the lockfile after the version change:

   ```bash
   uv lock
   uv sync --locked --dev
   ```

4. Run the same functional quality gates used by CI:

   ```bash
   uv run ruff check h388x_cli tests
   uv run ruff format --check h388x_cli tests
   uv run pytest
   uv build
   ```

5. Verify the wheel in a clean Python 3.14 environment:

   ```bash
   uv venv --python 3.14 .venv-release-smoke
   uv pip install --python .venv-release-smoke/bin/python dist/*.whl
   .venv-release-smoke/bin/h388x --help
   ```

6. Commit the version/changelog/lockfile changes and merge them to `main` before tagging.

## Create the release

Create an annotated tag whose version exactly matches `project.version`, then push it:

```bash
git switch main
git pull --ff-only github main
git tag -a vX.Y.Z -m "h388x-cli vX.Y.Z"
git push github vX.Y.Z
```

In the maintainer checkout, `github` points to GitHub and `origin` points to
the personal Git mirror. Check `git remote -v` before tagging. For a fresh
clone whose `origin` is GitHub, use `origin` in the commands above.

Confirm the GitHub Actions checks for the release commit passed before pushing
the tag.

## Public repository setup

Before changing repository visibility, merge the publication fixes and verify
the release artifacts. After publication:

- Enable private vulnerability reporting under GitHub security settings.
- Protect `main` with a ruleset requiring pull requests and the quality, test,
  coverage and package checks. Prevent force pushes and branch deletion.
- Verify the HTTPS tag and direct-wheel install examples in README from a
  clean environment without repository credentials.
- Update README to make HTTPS installation the default and retain SSH as an
  authenticated alternative.

Keep PyPI publishing separate until its release workflow is configured.

The tag-triggered `Release` workflow deliberately fails before publishing if:

- the tag does not exactly match `v<project.version>`;
- the locked environment cannot be reproduced;
- Ruff or the test suite fails;
- the sdist/wheel cannot be built;
- the wheel cannot be installed cleanly on Python 3.14;
- the installed wheel metadata version does not match the tag.

Only after those checks does it create the GitHub Release and attach `dist/*`.

## Verify the published private Release asset

For a private repository, use an authenticated GitHub CLI session to download the
actual published wheel and test that artifact rather than only the local build. Replace
`X.Y.Z` in both the tag and filename:

```bash
gh release download vX.Y.Z -R alsd4git/h388x-cli -p "h388x_cli-X.Y.Z-py3-none-any.whl"
uvx --from ./h388x_cli-X.Y.Z-py3-none-any.whl h388x --help
```

To verify the persistent-tool path as well:

```bash
uv tool install ./h388x_cli-X.Y.Z-py3-none-any.whl
h388x --help
```

On Windows, if the install succeeds but the executable is not found, run
`uv tool update-shell` once and reopen the terminal.

## Installing a private tagged release with uv

The shortest no-clone path remains Git over SSH. The machine must already have
GitHub SSH access to this repository:

```bash
uv tool install "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.2.0"
```

For a one-off invocation without a persistent tool install:

```bash
uvx --from "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.2.0" h388x --help
```

Use an existing released tag; do not use an unpinned branch as the recommended install path.

## PyPI

PyPI publication remains separate from GitHub Releases. If it is enabled later, prefer
Trusted Publishing / OIDC instead of storing a long-lived API token in repository secrets.
