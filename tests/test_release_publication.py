import os
from pathlib import Path
import shutil
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/publish-release.sh"
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="requires bash")


@pytest.fixture
def publication(tmp_path):
    mock = tmp_path / "gh"
    mock.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$TEST_GH_LOG"\n'
        'if [ "$1" = api ]; then\n'
        '  [ "$TEST_LOOKUP_EXIT" = 0 ] || exit "$TEST_LOOKUP_EXIT"\n'
        '  printf "%s\\n" "$TEST_EXISTS"\n'
        "fi\n"
    )
    mock.chmod(0o700)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "example.whl").write_text("fixture")
    log = tmp_path / "calls.log"
    env = {
        **os.environ,
        "PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", ""),
        "GITHUB_REPOSITORY": "example/project",
        "GITHUB_REF_NAME": "v0.2.0",
        "TEST_GH_LOG": str(log),
        "TEST_EXISTS": "false",
        "TEST_LOOKUP_EXIT": "0",
    }

    def run(**overrides):
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=tmp_path,
            env={**env, **overrides},
            capture_output=True,
            text=True,
            check=False,
        )
        return result, log.read_text() if log.exists() else ""

    return run


def test_create_missing_release(publication):
    result, calls = publication()
    assert result.returncode == 0, result.stderr
    assert "owner=example" in calls and "name=project" in calls
    assert "tag=v0.2.0" in calls
    assert "release create v0.2.0 dist/example.whl --verify-tag" in calls


def test_preserve_existing_release(publication):
    result, calls = publication(TEST_EXISTS="true")
    assert result.returncode == 0, result.stderr
    assert "preserving notes and assets" in result.stdout
    assert "release create" not in calls
    assert "upload" not in calls and "edit" not in calls


@pytest.mark.parametrize("response", ["", "null", "unexpected"])
def test_reject_unexpected_lookup_response(publication, response):
    result, calls = publication(TEST_EXISTS=response)
    assert result.returncode != 0
    assert "release create" not in calls


def test_lookup_failure_does_not_publish(publication):
    result, calls = publication(TEST_LOOKUP_EXIT="17")
    assert result.returncode == 17
    assert "release create" not in calls


@pytest.mark.parametrize("variable", ["GITHUB_REPOSITORY", "GITHUB_REF_NAME"])
def test_missing_context_fails_before_lookup(publication, variable):
    result, calls = publication(**{variable: ""})
    assert result.returncode != 0
    assert variable in result.stderr
    assert not calls
