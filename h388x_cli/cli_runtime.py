"""Shared CLI state, options and authenticated API construction."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from dotenv import dotenv_values
from rich.console import Console

from .api import ZTEH388XAPI

# Configuration is intentionally loaded by the CLI before its option defaults
# are constructed. Explicit paths avoid searching parent directories, and
# preserve the original process environment while allowing the cwd file to
# override the user config file.
_process_environment = os.environ.copy()
_xdg_config_home = os.getenv("XDG_CONFIG_HOME")
_user_config_dir = (
    Path(_xdg_config_home).expanduser() if _xdg_config_home else Path.home() / ".config"
)
for _config_path in (
    _user_config_dir / "h388x-cli" / "config.env",
    Path.cwd() / ".env",
):
    if _config_path.is_file():
        for _key, _value in dotenv_values(_config_path).items():
            if _value is not None and _key not in _process_environment:
                os.environ[_key] = _value

console = Console()


class State:
    json: bool = False


state = State()


def require_explicit_confirmation(yes: bool) -> None:
    """Require --yes when a destructive operation cannot prompt safely."""
    if yes or (not state.json and sys.stdin.isatty()):
        return
    message = "This operation requires --yes in JSON or non-interactive mode."
    fail_cli(message, "confirmation_required")


def _emit_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


def fail_cli(message: str, error_type: str) -> None:
    """Report a command failure in the selected output format and exit."""
    if state.json:
        _emit_json(
            {
                "ok": False,
                "error": {
                    "type": error_type,
                    "message": message,
                },
            }
        )
    else:
        console.print(message, style="red", markup=False)
    raise typer.Exit(code=1)


def configure_output_encoding() -> None:
    """Escape unencodable characters on legacy terminals and output pipes."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


def _host_opt() -> str:
    default = os.getenv("H388X_HOST") or os.getenv("H388X_IP", "192.168.1.1")
    return typer.Option(
        default,
        "--host",
        "-H",
        help=(
            "Modem host: IP, hostname, or full URL. Examples: "
            "`192.168.1.1`, `modem.example.com`, "
            "`https://modem.example.com:8443`. "
            "Plain hostnames default to http://."
        ),
    )


def _user_opt() -> str:
    return typer.Option(os.getenv("H388X_USER", "admin"), help="Admin username")


def _pwd_opt() -> Optional[str]:
    return typer.Option(None, help="Admin password (or set H388X_PASSWORD)")


def _insecure_opt() -> bool:
    return typer.Option(
        False,
        "--insecure",
        "-k",
        help="Skip TLS certificate verification (useful for self-signed HTTPS).",
    )


def get_api(
    host: str,
    user: str,
    password: Optional[str],
    insecure: bool = False,
) -> ZTEH388XAPI:
    password = password or os.getenv("H388X_PASSWORD", "")
    if not password:
        fail_cli(
            "Password is required. Set H388X_PASSWORD in config.env, .env or use --password.",
            "authentication_error",
        )

    if insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    api = ZTEH388XAPI(
        host=host, username=user, password=password, verify_tls=not insecure
    )
    if api.has_cached_session:
        return api

    if state.json:
        ok = api.login()
    else:
        with console.status("[bold green]Connecting to modem..."):
            ok = api.login()
    if not ok:
        api.session.close()
        fail_cli(
            "Login failed. Check credentials, host and active admin sessions.",
            "authentication_error",
        )
    return api
