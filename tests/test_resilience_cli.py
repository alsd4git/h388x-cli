import json
import subprocess

from typer.testing import CliRunner

from h388x_cli import cli


runner = CliRunner()


def test_stats_watch_rejects_zero_or_negative_interval():
    assert runner.invoke(cli.app, ["stats", "--watch", "0"]).exit_code == 2
    assert runner.invoke(cli.app, ["stats", "--watch", "-1"]).exit_code == 2


def test_generic_watch_rejects_zero_interval():
    assert runner.invoke(cli.app, ["watch", "0", "info"]).exit_code == 2


def test_generic_watch_propagates_child_failure(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/h388x")
    monkeypatch.setattr(cli.os, "system", lambda _cmd: 0)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 7),
    )

    result = runner.invoke(cli.app, ["watch", "1", "info"])
    assert result.exit_code == 7


def test_generic_watch_keep_going_retries_after_failure(monkeypatch):
    calls = []

    def run(*args, **kwargs):
        calls.append(args[0])
        if len(calls) == 1:
            return subprocess.CompletedProcess(args[0], 3)
        raise KeyboardInterrupt

    monkeypatch.setattr("shutil.which", lambda _name: "/usr/bin/h388x")
    monkeypatch.setattr(cli.os, "system", lambda _cmd: 0)
    monkeypatch.setattr("subprocess.run", run)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    result = runner.invoke(cli.app, ["watch", "1", "--keep-going", "info"])
    assert result.exit_code == 0
    assert len(calls) == 2
    assert "exited 3" in result.stdout


def test_logout_uses_cached_session_without_password(monkeypatch):
    instances = []

    class FakeApi:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.has_cached_session = True
            self.login_calls = 0
            self.logout_calls = 0
            self.close_calls = 0
            instances.append(self)

        def login(self):
            self.login_calls += 1
            return True

        def logout(self):
            self.logout_calls += 1

        def close(self):
            self.close_calls += 1

    monkeypatch.delenv("H388X_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "ZTEH388XAPI", FakeApi)

    result = runner.invoke(cli.app, ["--json", "logout"])

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"logout": "ok"}
    api = instances[0]
    assert api.kwargs["password"] == ""
    assert api.login_calls == 0
    assert api.logout_calls == 1


def test_logout_without_cache_or_password_fails_without_login(monkeypatch):
    instances = []

    class FakeApi:
        def __init__(self, **kwargs):
            self.has_cached_session = False
            self.login_calls = 0
            instances.append(self)

        def login(self):
            self.login_calls += 1
            return True

        def close(self):
            pass

    monkeypatch.delenv("H388X_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "ZTEH388XAPI", FakeApi)

    result = runner.invoke(cli.app, ["--json", "logout"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["logout"] == "failed"
    assert "no cached session" in payload["error"]
    assert instances[0].login_calls == 0
