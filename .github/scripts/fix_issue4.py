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

# The compatibility tuple is executable code, so it must follow every import.
path = Path("h388x_cli/cli.py")
text = path.read_text(encoding="utf-8")
compat = '''# Backward-compatible internal helper aliases retained across the CLI split.
_LEGACY_DEVICE_HELPERS = (
    _norm_mac, _merge_devices, _reservations_export, _plan_import
)
'''
if compat not in text:
    raise SystemExit("legacy helper compatibility block not found")
text = text.replace(compat + "\n", "", 1)
anchor = 'app = typer.Typer(help="H388X Modem CLI Management Tool", no_args_is_help=True)\n'
if anchor not in text:
    raise SystemExit("Typer app declaration not found")
text = text.replace(anchor, compat + "\n" + anchor, 1)
path.write_text(text, encoding="utf-8")
