from pathlib import Path

path = Path("tests/test_parsers.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from h388x_cli.api import ZTEH388XAPI\n",
    "from h388x_cli.api import ZTEH388XAPI\nfrom h388x_cli.errors import ParseError\n",
    1,
)
old = '''def test_parse_malformed_xml_returns_empty_list():
    """Bad XML must not raise; the API layer logs nothing and returns []."""
    assert ZTEH388XAPI._parse_instances("not xml at all <<", "OBJ_X") == []
'''
new = '''def test_parse_malformed_xml_raises_parse_error():
    """Bad XML is a protocol failure, not a legitimate empty collection."""
    with pytest.raises(ParseError):
        ZTEH388XAPI._parse_instances("not xml at all <<", "OBJ_X")
'''
if old not in text:
    raise SystemExit("legacy malformed XML test not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
