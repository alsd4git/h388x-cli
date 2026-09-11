"""Unit tests for the ``devices`` (device-naming, route A) helpers.

These exercise merge/export/import planning and fail-safe bulk application
without contacting a modem. HTTP write protocol coverage lives in
``test_api_flow.py``.
"""

from h388x_cli import cli
from h388x_cli.devices import (
    apply_import_plan,
    is_valid_mac,
    merge_devices,
    norm_mac,
    plan_import,
    reservations_export,
)
from h388x_cli.models import Client, DhcpBinding


def _client(**kw):
    return Client.model_validate(kw)


def _binding(**kw):
    return DhcpBinding.model_validate(kw)


class _FakeWriteApi:
    def __init__(self, outcomes=None):
        self.outcomes = iter(outcomes or [])
        self.calls = []

    def _result(self):
        return next(self.outcomes, (True, "ok"))

    def add_dhcp_reservation(self, *, mac, ip_address, name):
        self.calls.append(("add", mac, ip_address, name))
        return self._result()

    def edit_dhcp_reservation(self, inst_id, *, name, ip_address):
        self.calls.append(("edit", inst_id, ip_address, name))
        return self._result()


# --- _norm_mac --------------------------------------------------------------


def test_norm_mac_lowercases_and_strips():
    assert norm_mac("  AA:BB:CC:00:11:22 ") == "aa:bb:cc:00:11:22"
    assert norm_mac(None) == ""
    assert norm_mac("") == ""


def test_norm_mac_accepts_common_representations():
    expected = "aa:bb:cc:00:11:22"
    assert norm_mac("AA-BB-CC-00-11-22") == expected
    assert norm_mac("AABB.CC00.1122") == expected
    assert norm_mac("AABBCC001122") == expected
    assert is_valid_mac(expected) is True
    assert is_valid_mac("not-a-mac") is False


def test_cli_keeps_legacy_device_helper_imports():
    assert cli._norm_mac is norm_mac
    assert cli._merge_devices is merge_devices
    assert cli._reservations_export is reservations_export
    assert cli._plan_import is plan_import


# --- _merge_devices ---------------------------------------------------------


def test_merge_joins_client_and_reservation_by_mac_case_insensitive():
    clients = [
        _client(
            HostName="laptop",
            IPAddress="192.168.1.50",
            MACAddress="AA:BB:CC:00:11:22",
            AliasName="LAN1",
        )
    ]
    bindings = [
        _binding(
            _OBJ_InstID="DEV.V4DP.Sr.Pl1.Bd1",
            Name="Laptop-Fisso",
            IPAddr="192.168.1.50",
            MACAddr="aa:bb:cc:00:11:22",
        )
    ]

    rows = merge_devices(clients, bindings)

    assert len(rows) == 1
    row = rows[0]
    assert row["online"] is True
    assert row["reserved"] is True
    assert row["hostname"] == "laptop"
    assert row["name"] == "Laptop-Fisso"
    assert row["ipv4"] == "192.168.1.50"
    assert row["reservation_id"] == "DEV.V4DP.Sr.Pl1.Bd1"


def test_merge_reservation_only_device_shows_offline_with_reserved_ip():
    bindings = [
        _binding(
            _OBJ_InstID="DEV.V4DP.Sr.Pl1.Bd2",
            Name="NAS",
            IPAddr="192.168.1.20",
            MACAddr="DE:AD:BE:EF:00:01",
        )
    ]

    rows = merge_devices([], bindings)

    assert len(rows) == 1
    row = rows[0]
    assert row["online"] is False
    assert row["reserved"] is True
    assert row["ipv4"] == "192.168.1.20"
    assert row["hostname"] is None


def test_merge_connected_without_reservation():
    clients = [
        _client(
            HostName="phone",
            IPAddress="192.168.1.30",
            MACAddress="11:22:33:44:55:66",
            AliasName="SSID1",
        )
    ]

    rows = merge_devices(clients, [])

    assert len(rows) == 1
    assert rows[0]["online"] is True
    assert rows[0]["reserved"] is False
    assert rows[0]["name"] is None


def test_merge_matches_dash_and_colon_mac_formats():
    clients = [
        _client(
            HostName="phone",
            IPAddress="192.168.1.30",
            MACAddress="11-22-33-44-55-66",
        )
    ]
    bindings = [
        _binding(
            _OBJ_InstID="DEV.V4DP.Sr.Pl1.Bd3",
            Name="Phone",
            IPAddr="192.168.1.30",
            MACAddr="11:22:33:44:55:66",
        )
    ]

    rows = merge_devices(clients, bindings)
    assert len(rows) == 1
    assert rows[0]["online"] is True
    assert rows[0]["reserved"] is True


def test_merge_skips_entries_without_mac():
    clients = [_client(HostName="ghost", IPAddress="192.168.1.99")]
    bindings = [_binding(_OBJ_InstID="X", Name="n", IPAddr="1.2.3.4")]

    assert merge_devices(clients, bindings) == []


# --- _reservations_export ---------------------------------------------------


def test_export_sorts_by_ip_and_only_includes_mac_rows():
    bindings = [
        _binding(_OBJ_InstID="B", Name="b", IPAddr="192.168.1.100", MACAddr="22:22"),
        _binding(_OBJ_InstID="A", Name="a", IPAddr="192.168.1.20", MACAddr="11:11"),
        _binding(_OBJ_InstID="C", Name="no-mac", IPAddr="192.168.1.5"),
    ]

    out = reservations_export(bindings)

    assert out == [
        {"mac": "11:11", "ip": "192.168.1.20", "name": "a"},
        {"mac": "22:22", "ip": "192.168.1.100", "name": "b"},
    ]


# --- _plan_import -----------------------------------------------------------


def _existing():
    return [
        _binding(
            _OBJ_InstID="DEV.V4DP.Sr.Pl1.Bd1",
            Name="NAS",
            IPAddr="192.168.1.20",
            MACAddr="DE:AD:BE:EF:00:01",
        )
    ]


def test_plan_import_marks_identical_entry_unchanged():
    entries = [{"mac": "DE:AD:BE:EF:00:01", "ip": "192.168.1.20", "name": "NAS"}]
    plan = plan_import(entries, _existing())
    assert [p["action"] for p in plan] == ["unchanged"]


def test_plan_import_is_idempotent_case_insensitive():
    entries = [{"mac": "de:ad:be:ef:00:01", "ip": "192.168.1.20", "name": "NAS"}]
    plan = plan_import(entries, _existing())
    assert plan[0]["action"] == "unchanged"


def test_plan_import_detects_rename_as_edit():
    entries = [{"mac": "DE:AD:BE:EF:00:01", "ip": "192.168.1.20", "name": "NAS2"}]
    plan = plan_import(entries, _existing())
    assert plan[0]["action"] == "edit"
    assert plan[0]["id"] == "DEV.V4DP.Sr.Pl1.Bd1"
    assert plan[0]["old_name"] == "NAS"


def test_plan_import_new_mac_is_add():
    entries = [{"mac": "AA:BB:CC:00:11:22", "ip": "192.168.1.50", "name": "Laptop"}]
    plan = plan_import(entries, _existing())
    assert plan[0]["action"] == "add"
    assert plan[0]["id"] is None


def test_plan_import_missing_mac_is_error():
    plan = plan_import([{"mac": "", "ip": "1.2.3.4", "name": "x"}], _existing())
    assert plan[0]["action"] == "error"
    assert "mac" in plan[0]["error"]


def test_plan_import_invalid_mac_is_error():
    plan = plan_import(
        [{"mac": "not-a-mac", "ip": "192.168.1.30", "name": "x"}], _existing()
    )
    assert plan[0]["action"] == "error"
    assert "invalid mac" in plan[0]["error"]


def test_plan_import_missing_ip_on_add_is_error():
    plan = plan_import([{"mac": "99:99:99:99:99:99", "name": "x"}], _existing())
    assert plan[0]["action"] == "error"
    assert "ip" in plan[0]["error"]


def test_plan_import_rejects_invalid_ip_before_apply():
    plan = plan_import(
        [{"mac": "aa:bb:cc:00:11:22", "ip": "999.1.1.1", "name": "Laptop"}],
        _existing(),
    )
    assert plan[0]["action"] == "error"
    assert "IPv4" in plan[0]["error"]


def test_plan_import_rejects_missing_name_before_apply():
    plan = plan_import(
        [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": ""}],
        _existing(),
    )
    assert plan[0]["action"] == "error"
    assert "name" in plan[0]["error"]


def test_plan_import_empty_ip_on_existing_keeps_current_ip():
    entries = [{"mac": "DE:AD:BE:EF:00:01", "name": "NAS-Renamed"}]
    plan = plan_import(entries, _existing())
    assert plan[0]["action"] == "edit"
    assert plan[0]["ip"] == "192.168.1.20"


def test_plan_import_non_object_entry_is_error():
    plan = plan_import(["oops"], _existing())  # type: ignore[list-item]
    assert plan[0]["action"] == "error"
    assert "must be an object" in plan[0]["error"]


def test_plan_import_duplicate_mac_is_error_after_normalization():
    plan = plan_import(
        [
            {"mac": "AA-BB-CC-00-11-22", "ip": "192.168.1.50", "name": "Laptop"},
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.51", "name": "Laptop2"},
        ],
        _existing(),
    )
    assert plan[0]["action"] == "add"
    assert plan[1]["action"] == "error"
    assert "duplicate mac" in plan[1]["error"]


# --- apply_import_plan ------------------------------------------------------


def test_apply_import_plan_does_no_writes_when_preflight_has_errors():
    plan = plan_import(
        [
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "Laptop"},
            {"mac": "bad", "ip": "192.168.1.60", "name": "Bad"},
        ],
        _existing(),
    )
    api = _FakeWriteApi()

    ok, summary = apply_import_plan(api, plan)

    assert ok is False
    assert api.calls == []
    assert summary == {
        "applied": 0,
        "failed": 0,
        "skipped": 1,
        "partial": False,
        "preflight_errors": 1,
    }
    assert plan[0]["skipped"] == "preflight failed"


def test_apply_import_plan_stops_after_first_failure_and_reports_partial_state():
    plan = plan_import(
        [
            {"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "One"},
            {"mac": "aa:bb:cc:00:11:23", "ip": "192.168.1.51", "name": "Two"},
            {"mac": "aa:bb:cc:00:11:24", "ip": "192.168.1.52", "name": "Three"},
        ],
        _existing(),
    )
    api = _FakeWriteApi([(True, "ok"), (False, "firmware rejected write")])

    ok, summary = apply_import_plan(api, plan)

    assert ok is False
    assert len(api.calls) == 2
    assert summary == {
        "applied": 1,
        "failed": 1,
        "skipped": 1,
        "partial": True,
        "preflight_errors": 0,
    }
    assert plan[0]["ok"] is True
    assert plan[1]["ok"] is False
    assert plan[2]["skipped"] == "previous write failed"


def test_apply_import_plan_success_is_explicit():
    plan = plan_import(
        [{"mac": "aa:bb:cc:00:11:22", "ip": "192.168.1.50", "name": "Laptop"}],
        _existing(),
    )
    api = _FakeWriteApi([(True, "ok")])

    ok, summary = apply_import_plan(api, plan)

    assert ok is True
    assert summary["applied"] == 1
    assert summary["failed"] == 0
    assert summary["partial"] is False
