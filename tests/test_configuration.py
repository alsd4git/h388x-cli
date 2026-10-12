"""Configuration loading tests for CLI defaults."""

import json
import os
import subprocess
import sys
from pathlib import Path


def test_config_precedence_outside_repository(tmp_path):
    """User config, cwd .env, then process env feed defaults before CLI import."""
    repo_root = Path(__file__).resolve().parents[1]
    outside_repo = tmp_path / "outside"
    outside_repo.mkdir()
    user_config = tmp_path / "xdg" / "h388x-cli" / "config.env"
    user_config.parent.mkdir(parents=True)
    user_config.write_text(
        "H388X_HOST=user-config-host\nH388X_USER=user-config-user\n",
        encoding="utf-8",
    )
    (outside_repo / ".env").write_text(
        "H388X_HOST=cwd-host\nH388X_USER=cwd-user\n", encoding="utf-8"
    )

    env = os.environ.copy()
    for key in ("H388X_HOST", "H388X_IP", "H388X_USER", "H388X_PASSWORD"):
        env.pop(key, None)
    env.update(
        {
            "H388X_HOST": "process-host",
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "PYTHONPATH": str(repo_root),
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import inspect, json; from h388x_cli.cli import stats; "
                "params = inspect.signature(stats).parameters; "
                "print(json.dumps({key: params[key].default.default "
                "for key in ('host', 'user')}))"
            ),
        ],
        cwd=outside_repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {"host": "process-host", "user": "cwd-user"}
