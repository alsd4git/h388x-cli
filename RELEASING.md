# Releasing h388x-cli

`h388x-cli` uses `vMAJOR.MINOR.PATCH` tags and GitHub Releases. Development,
validation and packaging use `uv`; publishing to PyPI is intentionally not enabled.

## Before tagging

A release tag must point to a commit already merged into `main`. Do not tag a feature
branch or an unmerged pull request.

1. Update `project.version` in `pyproject.toml`.
2. Update `CHANGELOG.md` with the release notes.
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

For the first release the current package version is `0.1.0`, so after the release commit is
on `main`:

```bash
git switch main
git pull --ff-only
git tag -a v0.1.0 -m "h388x-cli v0.1.0"
git push origin v0.1.0
```

For subsequent releases, use the exact `vX.Y.Z` matching `project.version`.

The tag-triggered `Release` workflow deliberately fails before publishing if:

- the tag does not exactly match `v<project.version>`;
- the locked environment cannot be reproduced;
- Ruff or the test suite fails;
- the sdist/wheel cannot be built;
- the wheel cannot be installed cleanly on Python 3.14;
- the installed wheel metadata version does not match the tag.

Only after those checks does it create the GitHub Release and attach `dist/*`.

## Installing a private tagged release with uv

While the repository is private, the clean no-clone path is Git over SSH. The machine must
already have GitHub SSH access to this repository:

```bash
uv tool install "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.1.0"
```

For a one-off invocation without a persistent tool install:

```bash
uvx --from "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.1.0" h388x --help
```

Use an existing released tag; do not use an unpinned branch as the recommended install path.

## PyPI

PyPI publication remains separate from GitHub Releases. If it is enabled later, prefer
Trusted Publishing / OIDC instead of storing a long-lived API token in repository secrets.
