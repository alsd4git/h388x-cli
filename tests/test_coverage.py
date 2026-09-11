from h388x_cli.coverage import COVERAGE_CATALOG, build_capabilities
from h388x_cli.cli import app


def test_catalog_includes_existing_local_network_commands():
    ids = {item["id"] for item in COVERAGE_CATALOG}

    assert {
        "lan.public",
        "lan.usb",
        "firewall.parental-control",
        "firewall.parental-control-write",
    } <= ids


def test_catalog_ids_are_unique_and_command_references_exist():
    ids = [item["id"] for item in COVERAGE_CATALOG]
    registered = {
        command.name or command.callback.__name__ for command in app.registered_commands
    }
    registered.update(group.name for group in app.registered_groups)

    assert len(ids) == len(set(ids))
    for item in COVERAGE_CATALOG:
        for command in item["commands"]:
            assert command.split()[0] in registered, (
                f"{item['id']} references unknown command {command!r}"
            )


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
