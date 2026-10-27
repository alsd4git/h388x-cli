"""Keep the documented shareable info example redacted and reproducible."""

import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from h388x_cli import cli


@pytest.mark.skipif(shutil.which("jq") is None, reason="README example requires jq")
def test_quick_start_info_filter_redacts_serial(monkeypatch):
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    match = re.search(r"^\$ h388x --json info \| jq (.+)$", readme, re.MULTILINE)
    assert match, "Missing executable quick-start redaction example"
    api = MagicMock()
    api.get_device_info.return_value = {
        "ModelName": "H388X",
        "SoftwareVer": "AGZHM_1.4.4",
        "SerialNumber": "PRIVATE-SERIAL",
        "HardwareVer": "PRIVATE-HARDWARE",
    }
    monkeypatch.setattr(cli, "get_api", lambda *args, **kwargs: api)
    result = CliRunner().invoke(cli.app, ["--json", "info"])
    assert result.exit_code == 0
    filtered = subprocess.run(
        ["jq", *shlex.split(match.group(1))],
        input=result.stdout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "PRIVATE" not in filtered
    assert json.loads(filtered) == {
        "model": "H388X",
        "serial_number": "REDACTED",
        "software_version": "AGZHM_1.4.4",
    }
    api.close.assert_called_once()
