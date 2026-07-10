"""Opt-in, read-only smoke test for a real H388X modem.

This test is deliberately skipped unless ``H388X_REAL_SMOKE=1`` is set. It
uses the same ``H388X_*`` configuration as the CLI, does not write a session
cache, and only reads the device-information endpoint.
"""

import os

import pytest
from dotenv import load_dotenv

from h388x_cli.api import ZTEH388XAPI


@pytest.mark.real_device
def test_real_modem_device_info_smoke():
    """Authenticate and read device information without mutating the modem."""
    if os.getenv("H388X_REAL_SMOKE") != "1":
        pytest.skip("set H388X_REAL_SMOKE=1 to run against a real modem")

    load_dotenv()
    host = os.getenv("H388X_HOST") or os.getenv("H388X_IP", "192.168.1.1")
    username = os.getenv("H388X_USER", "admin")
    password = os.getenv("H388X_PASSWORD")
    if not password:
        pytest.fail("H388X_PASSWORD is required when H388X_REAL_SMOKE=1")

    api = ZTEH388XAPI(
        host=host,
        username=username,
        password=password,
        verify_tls=os.getenv("H388X_INSECURE") != "1",
        cache_enabled=False,
    )
    try:
        assert api.login(), "login failed; check host, credentials, and active WebUI sessions"
        assert api.get_device_info(), "device information endpoint returned no data"
    finally:
        api.close()
