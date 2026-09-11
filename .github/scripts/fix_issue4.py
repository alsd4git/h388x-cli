import re
from pathlib import Path

# Domain methods keep using the typed errors defined before the split.
for filename in ("h388x_cli/api_services.py", "h388x_cli/api_wifi.py"):
    path = Path(filename)
    text = path.read_text(encoding="utf-8")
    anchor = "from pydantic import ValidationError\n"
    if "from .errors import ParseError, SessionExpiredError\n" not in text:
        text = text.replace(
            anchor,
            anchor + "\nfrom .errors import ParseError, SessionExpiredError\n",
            1,
        )
    path.write_text(text, encoding="utf-8")

# Preserve the pre-refactor import path used by callers/tests. The redundant
# alias is intentional: it is an explicit re-export from api.py.
api_path = Path("h388x_cli/api.py")
api = api_path.read_text(encoding="utf-8")
api = api.replace(
    "from .transport import H388XTransport\n",
    "from .transport import H388XTransport, _default_cache_dir as _default_cache_dir\n",
    1,
)
api_path.write_text(api, encoding="utf-8")

# The compatibility tuple is executable code, so it must follow every import.
# Remove every copy regardless of whitespace, then add exactly one before app=.
path = Path("h388x_cli/cli.py")
text = path.read_text(encoding="utf-8")
pattern = re.compile(
    r"\n?# Backward-compatible internal helper aliases retained across the CLI split\.\n"
    r"_LEGACY_DEVICE_HELPERS\s*=\s*\(.*?\)\n",
    re.DOTALL,
)
text, removed = pattern.subn("\n", text)
if removed < 1:
    raise SystemExit("legacy helper compatibility block not found")
compat = '''# Backward-compatible internal helper aliases retained across the CLI split.
_LEGACY_DEVICE_HELPERS = (
    _norm_mac,
    _merge_devices,
    _reservations_export,
    _plan_import,
)

'''
anchor = 'app = typer.Typer(help="H388X Modem CLI Management Tool", no_args_is_help=True)\n'
if anchor not in text:
    raise SystemExit("Typer app declaration not found")
text = text.replace(anchor, compat + anchor, 1)
path.write_text(text, encoding="utf-8")
