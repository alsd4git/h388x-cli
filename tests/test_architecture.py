from h388x_cli import cli
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
    for mixin in (
        WanDslMixin,
        LanMixin,
        WifiMixin,
        FirewallMixin,
        ServicesMixin,
        SystemMixin,
    ):
        assert issubclass(ZTEH388XAPI, mixin)


def test_devices_subapp_and_legacy_helpers_remain_exported_from_cli():
    assert cli.devices_app is not None
    assert callable(cli._norm_mac)
    assert callable(cli._merge_devices)
    assert callable(cli._reservations_export)
    assert callable(cli._plan_import)
