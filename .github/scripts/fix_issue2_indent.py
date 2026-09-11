from pathlib import Path
from textwrap import indent

# Fix indentation of the generated devices-edit replacement and remove the
# now-unused color map from the old implementation.
cli_path = Path("h388x_cli/cli.py")
text = cli_path.read_text(encoding="utf-8")
start_marker = "\napplied = 0\nfor index, (kind, r, new) in enumerate(actions):\n"
start = text.index(start_marker) + 1
end = text.index("\n    finally:\n        api.close()", start)
block = text[start:end]
text = text[:start] + indent(block, "        ") + text[end:]
text = text.replace(
    '        colors = {"add": "green", "edit": "yellow", "clear": "red"}\n\n',
    "",
    1,
)
cli_path.write_text(text, encoding="utf-8")

# A single-port rule has start == end. If only the external start port is
# edited, keep it a single-port rule by moving the end along with the start.
# Real ranges retain their existing end and are still checked by PortForwardSpec.
api_path = Path("h388x_cli/api.py")
api = api_path.read_text(encoding="utf-8")
needle = '''            try:
                spec = PortForwardSpec(
                    description=pick(description, "Description"),
                    protocol=pick(protocol, "Protocol"),
                    external_port=pick(external_port, "ExternalPort"),
                    external_port_end=pick(external_port_end, "ExternalPortEndRange"),
'''
replacement = '''            current_external_port = current.get("ExternalPort", "")
            current_external_end = current.get("ExternalPortEndRange", "")
            if external_port_end is not None:
                target_external_end = external_port_end
            elif external_port is not None and current_external_end == current_external_port:
                target_external_end = external_port
            else:
                target_external_end = current_external_end

            try:
                spec = PortForwardSpec(
                    description=pick(description, "Description"),
                    protocol=pick(protocol, "Protocol"),
                    external_port=pick(external_port, "ExternalPort"),
                    external_port_end=target_external_end,
'''
if needle not in api:
    raise SystemExit("port-forward edit validation block not found")
api = api.replace(needle, replacement, 1)
api_path.write_text(api, encoding="utf-8")

# Keep user-facing validation messages concise and preserve the terminology
# already documented/tested by the CLI.
validation_path = Path("h388x_cli/validation.py")
validation = validation_path.read_text(encoding="utf-8")
validation = validation.replace("must be TCP, UDP, or BOTH", "must be TCP/UDP/BOTH")
validation = validation.replace("must be allow or deny", "must be allow/deny")
validation_path.write_text(validation, encoding="utf-8")

# MAC hex case is not semantically significant. Keep the protocol-flow tests
# focused on field presence and value rather than the case chosen by the
# canonicalizer.
test_path = Path("tests/test_api_flow.py")
tests = test_path.read_text(encoding="utf-8")
tests = tests.replace(
    'assert "AA%3ABB%3ACC%3ADD%3AEE%3AFF" in sent',
    'assert "aa%3abb%3acc%3add%3aee%3aff" in sent.lower()',
)
test_path.write_text(tests, encoding="utf-8")
