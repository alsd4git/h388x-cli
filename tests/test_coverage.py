from h388x_cli.coverage import COVERAGE_CATALOG
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
