"""Shared CLI state, options and authenticated API construction."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

import typer
from dotenv import load_dotenv
from rich.console import Console

from .api import ZTEH388XAPI

# Loading a project .env is intentionally a CLI concern. Importing the API
# package alone no longer causes environment/config discovery side effects.
load_dotenv()

console = Console()


class State:
    json: bool = False


state = State()


def _emit_json(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")
    sys.stdout.flush()


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
        console.print(
            "[red]Error: Password is required. "
            "Set H388X_PASSWORD in .env or use --password.[/red]"
        )
        raise typer.Exit(code=1)

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
        console.print(
            "[red]Login failed. Check credentials, IP and that no other "
            "admin session is open in a browser.[/red]"
        )
        raise typer.Exit(code=1)
    return api
