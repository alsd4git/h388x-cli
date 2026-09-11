from pathlib import Path
from textwrap import indent

path = Path("h388x_cli/cli.py")
text = path.read_text(encoding="utf-8")
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
path.write_text(text, encoding="utf-8")
