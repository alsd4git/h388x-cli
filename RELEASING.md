# Releasing h388x-cli

`h388x-cli` uses Semantic Versioning-style tags (`vMAJOR.MINOR.PATCH`) and GitHub Releases.
The project is built and tested with `uv`; publishing to PyPI is intentionally not enabled yet.

## Before tagging

1. Update `version` in `pyproject.toml`.
2. Update `CHANGELOG.md` with the release notes.
3. Run the full local validation:

   ```bash
   uv sync --locked --dev
   uv run ruff check h388x_cli tests
   uv run ruff format --check h388x_cli tests
   uv run pytest
   uv build
   ```

4. Optionally verify the wheel in a clean environment:

   ```bash
   uv venv --python 3.14 .venv-release-smoke
   uv pip install --python .venv-release-smoke/bin/python dist/*.whl
   .venv-release-smoke/bin/h388x --help
   ```

## Create the release

Create and push an annotated tag matching the package version:

```bash
git tag -a v0.1.0 -m "h388x-cli v0.1.0"
git push origin v0.1.0
```

The `Release` workflow builds the sdist and wheel, smoke-tests the wheel on Python 3.14,
and creates a GitHub Release with the package artifacts and generated release notes.

## PyPI

PyPI publication is deliberately separate from the GitHub release process. If it is enabled
later, prefer PyPI Trusted Publishing / OIDC rather than storing a long-lived API token in the
repository.
