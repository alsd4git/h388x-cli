from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
start = text.index("## Installation\n")
end = text.index("### Shell completion", start)
replacement = '''## Installation

### Tagged release with uv (recommended)

The repository is currently private, so the clean no-clone installation path uses
Git over SSH. Configure GitHub SSH access first, then pin the tool to an actual
release tag:

```bash
uv tool install "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.1.0"
```

The first `v0.1.0` tag will be created from `main` after the current hardening PR is
merged. Until that tag exists, use the development workflow below rather than
installing an unpinned branch.

For a one-off invocation without keeping a persistent tool environment:

```bash
uvx --from "git+ssh://git@github.com/alsd4git/h388x-cli.git@v0.1.0" h388x --help
```

`uvx` is an alias for `uv tool run`; both commands create an isolated tool
environment. The SSH URL deliberately uses the GitHub `git` user, as required for
private Git repository authentication.

### Local development

```bash
git clone git@github.com:alsd4git/h388x-cli.git
cd h388x-cli
uv sync --locked --dev
uv run h388x --help
```

To install the current checkout as a persistent local tool while developing:

```bash
uv tool install .
```

Release creation and versioning are documented in [`RELEASING.md`](RELEASING.md).

'''
text = text[:start] + replacement + text[end:]
text = text.replace(
    "After installing the `h388x` script (`uv tool install .`), enable\n",
    "After installing the `h388x` script as a persistent tool, enable\n",
    1,
)
text = text.replace(
    "available — install with `uv tool install .` for that.",
    "available — install the release (or current checkout) as a persistent tool for that.",
    1,
)
path.write_text(text, encoding="utf-8")
