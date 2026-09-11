from pathlib import Path

# Capability detection: a multi-endpoint capability is complete only when all
# declared endpoint tags were observed. Expose the evidence instead of a lossy bool.
path = Path("h388x_cli/coverage.py")
text = path.read_text(encoding="utf-8")
text = text.replace('COVERAGE_SCHEMA_VERSION = "1"', 'COVERAGE_SCHEMA_VERSION = "2"', 1)
old = '''        endpoints = capability.get("endpoints", [])
        capability["detected"] = bool(endpoints) and any(
            tag in tags for tag in endpoints
        )
'''
new = '''        endpoints = list(capability.get("endpoints", []))
        observed = [endpoint for endpoint in endpoints if endpoint in tags]
        missing = [endpoint for endpoint in endpoints if endpoint not in tags]
        if not observed:
            detection = "none"
        elif missing:
            detection = "partial"
        else:
            detection = "complete"
        capability["detected"] = bool(endpoints) and detection == "complete"
        capability["detection"] = detection
        capability["observed_endpoints"] = observed
        capability["missing_endpoints"] = missing
'''
if old not in text:
    raise SystemExit("capability detection block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")

# Focused behavior tests for the semantics above.
path = Path("tests/test_coverage.py")
tests = path.read_text(encoding="utf-8")
tests = tests.replace(
    "from h388x_cli.coverage import COVERAGE_CATALOG\n",
    "from h388x_cli.coverage import COVERAGE_CATALOG, build_capabilities\n",
    1,
)
tests += '''


def _discovery_with(*tags):
    return {"endpoints": [{"tag": tag} for tag in tags]}


def _capability(payload, capability_id):
    return next(item for item in payload["capabilities"] if item["id"] == capability_id)


def test_single_endpoint_capability_detection_is_complete():
    payload = build_capabilities(discovery=_discovery_with("devmgr_statusmgr_lua.lua"))
    item = _capability(payload, "device.info")
    assert item["detected"] is True
    assert item["detection"] == "complete"
    assert item["observed_endpoints"] == ["devmgr_statusmgr_lua.lua"]
    assert item["missing_endpoints"] == []


def test_multi_endpoint_capability_detection_reports_partial_evidence():
    payload = build_capabilities(discovery=_discovery_with("wlan_basiconoff_lua.lua"))
    item = _capability(payload, "wifi.status")
    assert item["detected"] is False
    assert item["detection"] == "partial"
    assert item["observed_endpoints"] == ["wlan_basiconoff_lua.lua"]
    assert item["missing_endpoints"] == ["wlan_status_lua.lua"]


def test_multi_endpoint_capability_detection_requires_all_endpoints():
    payload = build_capabilities(
        discovery=_discovery_with("wlan_basiconoff_lua.lua", "wlan_status_lua.lua")
    )
    item = _capability(payload, "wifi.status")
    assert item["detected"] is True
    assert item["detection"] == "complete"
    assert item["missing_endpoints"] == []


def test_capability_without_observed_endpoints_reports_none():
    payload = build_capabilities(discovery=_discovery_with())
    item = _capability(payload, "wifi.status")
    assert item["detected"] is False
    assert item["detection"] == "none"
    assert item["observed_endpoints"] == []
'''
path.write_text(tests, encoding="utf-8")

# The capability payload shape/meaning changed intentionally, so bump the
# smoke-test contract alongside COVERAGE_SCHEMA_VERSION.
path = Path("tests/test_cli_smoke.py")
smoke = path.read_text(encoding="utf-8")
old_schema_assert = '    assert payload["schema_version"] == "1"\n'
if old_schema_assert not in smoke:
    raise SystemExit("capability schema smoke assertion not found")
path.write_text(
    smoke.replace(old_schema_assert, '    assert payload["schema_version"] == "2"\n', 1),
    encoding="utf-8",
)

# Broaden only conventional sensitive-output names; arbitrary names are called
# out explicitly in documentation because a .gitignore cannot protect them.
path = Path(".gitignore")
gitignore = path.read_text(encoding="utf-8")
gitignore = gitignore.replace("endpoints.json\n", "endpoints*.json\nh388x-discovery*.json\n", 1)
gitignore = gitignore.replace("config-*.bin\n", "config-*.bin\nh388x-config*.bin\n", 1)
path.write_text(gitignore, encoding="utf-8")

path = Path("README.md")
readme = path.read_text(encoding="utf-8")
anchor = '''The machine-readable source used by `capabilities` is kept in
`h388x_cli/coverage.py`; its output includes `schema_version` so automation
can reject incompatible formats explicitly.
'''
replacement = anchor + '''
### Sensitive local output

`discover` reports contain modem identifiers plus samples of authenticated WebUI
responses; configuration backups can contain credentials or other private modem
settings. Both commands write new files with private permissions and refuse to
overwrite an existing path. Conventional names such as `endpoints*.json`,
`h388x-discovery*.json`, `config-*.bin`, and `h388x-config*.bin` are ignored by
this repository.

If you choose an arbitrary custom `--output` or backup filename, treat that file
as sensitive and add an explicit local ignore rule before working with Git. A
`.gitignore` cannot safely anticipate every custom filename.
'''
if anchor not in readme:
    raise SystemExit("README coverage anchor not found")
path.write_text(readme.replace(anchor, replacement, 1), encoding="utf-8")
