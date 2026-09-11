from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path("h388x_cli")


def method_ranges_and_sources(source: str):
    tree = ast.parse(source)
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ZTEH388XAPI"
    )
    lines = source.splitlines(keepends=True)
    result = {}
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start_line = min(
            [node.lineno, *(decorator.lineno for decorator in node.decorator_list)]
        )
        start = start_line - 1
        end = node.end_lineno
        result[node.name] = (start, end, "".join(lines[start:end]))
    return lines, result


def classify(name: str) -> str:
    transport = {
        "__init__",
        "_cache_path",
        "_load_cache",
        "_save_cache",
        "_clear_cache",
        "_has_sid_cookie",
        "has_cached_session",
        "login",
        "_strip_prefix",
        "_parse_instances",
        "_is_session_expired",
        "_require_http_success",
        "_get_response",
        "_menudata",
        "_refresh_session_token",
        "_fetch_fresh_session_token",
        "_post_action",
        "_menudata_multi",
        "_menudata_raw",
        "_hiddendata",
    }
    if name in transport:
        return "transport"
    if (
        "port_forward" in name
        or "firewall" in name
        or name
        in {
            "get_url_filter_global",
            "get_dmz",
            "_prefixed",
            "_set_rule_enabled",
            "add_url_filter_rule",
            "del_url_filter_rule",
            "add_ip_filter_rule",
            "del_ip_filter_rule",
            "set_ip_filter_enabled",
            "get_parental_control",
        }
    ):
        return "firewall"
    if name.startswith("get_wifi") or name == "get_band_steering":
        return "wifi"
    if (
        "dhcp" in name
        or name
        in {
            "get_lan_clients",
            "get_dns_local",
            "get_dns_hostnames",
            "get_mac_table",
            "get_arp_table",
            "get_eth_lan_ports",
            "get_ipv6_prefix",
            "get_public_lan",
            "get_usb_devs",
            "get_edns0",
        }
    ):
        return "lan"
    if "dsl" in name or "wan" in name or name in {"get_ddns", "get_eth_wan_port"}:
        return "wan"
    if name.startswith(
        ("get_voip", "get_upnp", "get_dms", "get_ftp", "get_nanocdn", "get_sntp", "get_topology")
    ):
        return "services"
    return "system"


def write_api_modules() -> None:
    path = ROOT / "api.py"
    source = path.read_text(encoding="utf-8")
    lines, methods = method_ranges_and_sources(source)

    groups: dict[str, list[str]] = {
        "transport": [],
        "wan": [],
        "lan": [],
        "wifi": [],
        "firewall": [],
        "services": [],
        "system": [],
    }
    for name, (_start, _end, method_source) in methods.items():
        groups[classify(name)].append(method_source)

    if not groups["transport"] or not groups["system"]:
        raise SystemExit("unexpected API method classification")

    transport_header = '''"""HTTP/session/cache transport primitives for the H388X WebUI protocol."""

from __future__ import annotations

import hashlib
import json as _json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from .errors import ParseError, ProtocolError, SessionExpiredError, TransportError


def _default_cache_dir() -> Path:
    """Return the per-user cache directory for h388x-cli."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "h388x-cli"


class H388XTransport:
    """Reusable authenticated transport used by :class:`ZTEH388XAPI`."""

    NO_CACHE = {"Cache-Control": "no-cache"}

'''
    (ROOT / "transport.py").write_text(
        transport_header + "\n".join(groups["transport"]), encoding="utf-8"
    )

    mixin_header = '''from __future__ import annotations

import html as _html
import json as _json
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import requests
from pydantic import ValidationError

from .validation import (
    DhcpReservationSpec,
    IpFilterSpec,
    PortForwardSpec,
    UrlFilterSpec,
    validation_error_message,
)

'''
    names = {
        "wan": "WanDslMixin",
        "lan": "LanMixin",
        "wifi": "WifiMixin",
        "firewall": "FirewallMixin",
        "services": "ServicesMixin",
        "system": "SystemMixin",
    }
    for group, class_name in names.items():
        doc = f'"""H388X {group} endpoint implementation mixin."""\n\n'
        body = f"class {class_name}:\n" + "\n".join(groups[group])
        (ROOT / f"api_{group}.py").write_text(
            doc + mixin_header + body, encoding="utf-8"
        )

    # Remove every method from the original class; constants and firmware URL
    # declarations remain in one place on the public ZTEH388XAPI class.
    remove_ranges = sorted(
        ((start, end) for start, end, _src in methods.values()), reverse=True
    )
    for start, end in remove_ranges:
        del lines[start:end]
    compact = "".join(lines)

    # The cache helper now belongs to transport.py.
    cache_start = compact.index("def _default_cache_dir()")
    class_start = compact.index("class ZTEH388XAPI:", cache_start)
    compact = compact[:cache_start] + compact[class_start:]

    compact = compact.replace(
        "class ZTEH388XAPI:",
        "class ZTEH388XAPI(\n"
        "    H388XTransport,\n"
        "    WanDslMixin,\n"
        "    LanMixin,\n"
        "    WifiMixin,\n"
        "    FirewallMixin,\n"
        "    ServicesMixin,\n"
        "    SystemMixin,\n"
        "):",
        1,
    )
    compact = compact.replace(
        "import requests\n",
        "import requests\n\n"
        "from .api_firewall import FirewallMixin\n"
        "from .api_lan import LanMixin\n"
        "from .api_services import ServicesMixin\n"
        "from .api_system import SystemMixin\n"
        "from .api_wan import WanDslMixin\n"
        "from .api_wifi import WifiMixin\n"
        "from .transport import H388XTransport\n",
        1,
    )
    compact = compact.replace('    NO_CACHE = {"Cache-Control": "no-cache"}\n', "", 1)
    path.write_text(compact, encoding="utf-8")


def write_cli_runtime() -> None:
    (ROOT / "cli_runtime.py").write_text(
        '''"""Shared CLI state, options and authenticated API construction."""

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
    sys.stdout.write("\\n")
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
''',
        encoding="utf-8",
    )


def split_devices_cli() -> None:
    path = ROOT / "cli.py"
    text = path.read_text(encoding="utf-8")

    start_marker = "# -------------------------------------------------------------------- devices\n"
    end_marker = "# ---------------------------------------------------------------------- dhcp6\n"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    block = text[start:end]
    block = block.replace('app.add_typer(devices_app, name="devices")\n', "", 1)

    header = '''"""Typer sub-application for MAC-keyed device naming workflows."""

from __future__ import annotations

import json
from typing import List, Optional

import typer
from rich.table import Table
from rich.text import Text

from .cli_runtime import (
    _emit_json,
    _host_opt,
    _insecure_opt,
    _pwd_opt,
    _user_opt,
    console,
    get_api,
    state,
)
from .devices import (
    apply_import_plan as _apply_import_plan,
    merge_devices as _merge_devices,
    norm_mac as _norm_mac,
    plan_import as _plan_import,
    reservations_export as _reservations_export,
)
from .models import Client, DhcpBinding

'''
    (ROOT / "cli_devices.py").write_text(header + block, encoding="utf-8")

    old_device_import = '''from .devices import (
    apply_import_plan as _apply_import_plan,
    merge_devices as _merge_devices,
    norm_mac as _norm_mac,
    plan_import as _plan_import,
    reservations_export as _reservations_export,
)
'''
    text = text.replace(old_device_import, "", 1)
    text = text.replace("from dotenv import load_dotenv\n", "", 1)
    text = text.replace("from rich.console import Console\n", "", 1)
    text = text.replace(
        "from .api import ZTEH388XAPI\n",
        "from .api import ZTEH388XAPI\n"
        "from .cli_devices import (\n"
        "    _merge_devices,\n"
        "    _norm_mac,\n"
        "    _plan_import,\n"
        "    _reservations_export,\n"
        "    devices_app,\n"
        ")\n"
        "from .cli_runtime import (\n"
        "    _emit_json,\n"
        "    _host_opt,\n"
        "    _insecure_opt,\n"
        "    _pwd_opt,\n"
        "    _user_opt,\n"
        "    console,\n"
        "    get_api,\n"
        "    state,\n"
        ")\n",
        1,
    )
    text = text.replace("load_dotenv()\n\n", "", 1)
    text = text.replace("console = Console()\n\n", "", 1)

    state_start = text.index("# --------------------------------------------------------------------- state\n")
    callback_start = text.index("@app.callback()", state_start)
    text = text[:state_start] + text[callback_start:]

    emit_start = text.index("def _emit_json(payload: Any) -> None:\n")
    table_marker = "# -------------------------------------------------------------- table builders\n"
    table_start = text.index(table_marker, emit_start)
    text = text[:emit_start] + text[table_start:]

    # Replace the large in-file subapp with registration of the extracted one.
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    replacement = (
        "# -------------------------------------------------------------------- devices\n\n"
        "app.add_typer(devices_app, name=\"devices\")\n\n\n"
    )
    text = text[:start] + replacement + text[end:]

    # Keep the long-standing helper aliases available from h388x_cli.cli for
    # callers/tests that imported them before the internal split.
    import_anchor = ")\nfrom .cli_runtime import ("
    pos = text.index(import_anchor)
    runtime_end = text.index(")\n", pos + len(import_anchor)) + 2
    compatibility = (
        "\n\n# Backward-compatible internal helper aliases retained across the CLI split.\n"
        "_LEGACY_DEVICE_HELPERS = (\n"
        "    _norm_mac, _merge_devices, _reservations_export, _plan_import\n"
        ")\n"
    )
    text = text[:runtime_end] + compatibility + text[runtime_end:]
    path.write_text(text, encoding="utf-8")

    # Commands moved to cli_devices resolve their own get_api binding now.
    test_path = Path("tests/test_devices_cli.py")
    tests = test_path.read_text(encoding="utf-8")
    tests = tests.replace(
        "from h388x_cli import cli\n",
        "from h388x_cli import cli, cli_devices\n",
        1,
    )
    tests = tests.replace(
        'monkeypatch.setattr(cli, "get_api", lambda *_args, **_kwargs: api)',
        'monkeypatch.setattr(cli_devices, "get_api", lambda *_args, **_kwargs: api)',
    )
    test_path.write_text(tests, encoding="utf-8")


def update_quality_gates() -> None:
    tests_path = Path(".github/workflows/tests.yml")
    tests = tests_path.read_text(encoding="utf-8")
    lint_line = "      - run: uv run ruff check h388x_cli tests\n"
    format_line = "      - run: uv run ruff format --check h388x_cli tests\n"
    if format_line not in tests:
        tests = tests.replace(lint_line, lint_line + format_line, 1)
    tests_path.write_text(tests, encoding="utf-8")

    release_path = Path(".github/workflows/release.yml")
    release = release_path.read_text(encoding="utf-8")
    release_gate = "          uv run ruff check h388x_cli tests\n          uv run pytest\n"
    if "ruff format --check" not in release:
        release = release.replace(
            release_gate,
            "          uv run ruff check h388x_cli tests\n"
            "          uv run ruff format --check h388x_cli tests\n"
            "          uv run pytest\n",
            1,
        )
    release_path.write_text(release, encoding="utf-8")

    releasing_path = Path("RELEASING.md")
    releasing = releasing_path.read_text(encoding="utf-8")
    releasing = releasing.replace(
        "   uv run ruff check h388x_cli tests\n   uv run pytest\n",
        "   uv run ruff check h388x_cli tests\n"
        "   uv run ruff format --check h388x_cli tests\n"
        "   uv run pytest\n",
        1,
    )
    old_note = '''Repository-wide `ruff format --check` is enabled as a CI/release gate once the baseline
formatting migration tracked in #4 is complete; until then `ruff check` is the formatting-neutral
quality gate.

'''
    releasing = releasing.replace(old_note, "")
    releasing_path.write_text(releasing, encoding="utf-8")

    pyproject_path = Path("pyproject.toml")
    pyproject = pyproject_path.read_text(encoding="utf-8")
    pyproject = pyproject.replace("fail_under = 35", "fail_under = 40", 1)
    pyproject_path.write_text(pyproject, encoding="utf-8")


def add_architecture_test() -> None:
    Path("tests/test_architecture.py").write_text(
        '''from h388x_cli import cli
from h388x_cli.api import ZTEH388XAPI
from h388x_cli.api_firewall import FirewallMixin
from h388x_cli.api_lan import LanMixin
from h388x_cli.api_services import ServicesMixin
from h388x_cli.api_system import SystemMixin
from h388x_cli.api_wan import WanDslMixin
from h388x_cli.api_wifi import WifiMixin
from h388x_cli.transport import H388XTransport


def test_public_api_class_composes_transport_and_domain_mixins():
    assert issubclass(ZTEH388XAPI, H388XTransport)
    for mixin in (WanDslMixin, LanMixin, WifiMixin, FirewallMixin, ServicesMixin, SystemMixin):
        assert issubclass(ZTEH388XAPI, mixin)


def test_devices_subapp_and_legacy_helpers_remain_exported_from_cli():
    assert cli.devices_app is not None
    assert callable(cli._norm_mac)
    assert callable(cli._merge_devices)
    assert callable(cli._reservations_export)
    assert callable(cli._plan_import)
''',
        encoding="utf-8",
    )


write_api_modules()
write_cli_runtime()
split_devices_cli()
update_quality_gates()
add_architecture_test()
