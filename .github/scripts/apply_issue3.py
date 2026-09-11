from pathlib import Path
from textwrap import dedent, indent


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement.rstrip() + "\n\n" + text[j:]


def method(source: str) -> str:
    return indent(dedent(source).strip() + "\n", "    ")


# ---------------------------------------------------------------- discovery
path = Path("h388x_cli/discovery.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    "from urllib.parse import urlsplit\n",
    "from urllib.parse import quote, urlencode, urljoin, urlsplit\n",
    1,
)

old_tokens = '''_MUTATING_TOKENS = (
    "add", "set", "del", "delete", "remove", "update", "edit",
    "save", "submit", "apply", "action",
    "restart", "reboot", "reset", "logout", "logoff",
    "upgrade", "upload", "download", "export", "import",
    "factory", "default", "clear", "wipe", "backup", "restore",
    "start", "stop", "enable", "disable", "kick", "block",
    "ping", "trace", "diag", "test",
)
'''
new_tokens = '''_MUTATING_TOKENS = frozenset({
    "add", "set", "del", "delete", "remove", "update", "edit",
    "save", "submit", "apply", "action",
    "restart", "reboot", "reset", "logout", "logoff",
    "upgrade", "upload", "download", "export", "import",
    "factory", "default", "clear", "wipe", "backup", "restore",
    "start", "stop", "enable", "disable", "kick", "block",
    "ping", "trace", "diag", "test",
})

# A few AGZHM tags concatenate an action with a role suffix instead of using
# an underscore (for example ``restartmgr``). Restrict prefix matching to
# those known action families; importantly, generic ``set*`` is NOT here, so
# read-only nouns such as ``setting`` / ``settings`` are not false positives.
_MUTATING_COMPOUND_PREFIXES = (
    "restartmgr", "rebootmgr", "resetmgr", "upgrademgr",
    "download", "upload", "backup", "restore",
)
'''
if old_tokens not in text:
    raise SystemExit("mutating token block not found")
text = text.replace(old_tokens, new_tokens, 1)

old_url = '''    def url(self) -> str:
        qs = f"_type={self.type}&_tag={self.tag}"
        for k, v in self.extras.items():
            qs += f"&{k}={v}"
        return f"/?{qs}"
'''
new_url = '''    def url(self) -> str:
        pairs = [("_type", self.type), ("_tag", self.tag), *self.extras.items()]
        # Keep slash/dot readable in firmware tag names while encoding values
        # that would otherwise corrupt the query string (spaces, &, =, ...).
        return "/?" + urlencode(pairs, quote_via=quote, safe="/.")
'''
if old_url not in text:
    raise SystemExit("Endpoint.url block not found")
text = text.replace(old_url, new_url, 1)

old_enqueue = '''    def _enqueue_asset(self, path: str, source: str) -> None:
        path = self._normalize_path(path)
'''
new_enqueue = '''    def _enqueue_asset(self, path: str, source: str) -> None:
        path = self._normalize_path(path, source=source)
'''
if old_enqueue not in text:
    raise SystemExit("asset enqueue block not found")
text = text.replace(old_enqueue, new_enqueue, 1)

text = replace_between(
    text,
    "    @staticmethod\n    def _normalize_path(",
    "    # ------------------------------------------------------- endpoints",
    method(
        '''
        @staticmethod
        def _normalize_path(p: str, source: str = "/") -> str:
            """Resolve a local asset path relative to the document that linked it.

            Absolute/external URLs are deliberately rejected: discovery only follows
            same-origin relative/root-relative assets and strips query/fragment noise.
            """
            if not p:
                return ""
            parsed = urlsplit(p)
            if parsed.scheme or parsed.netloc:
                return ""

            if p.startswith("/"):
                joined = p
            else:
                base = source if source.startswith("/") else "/"
                base_path = urlsplit(base).path or "/"
                joined = urljoin(base_path, p)

            resolved = urlsplit(joined)
            if resolved.scheme or resolved.netloc:
                return ""
            path = resolved.path or "/"
            if not path.startswith("/"):
                path = "/" + path
            return path
        '''
    ),
)

text = replace_between(
    text,
    "    @staticmethod\n    def _looks_mutating(",
    "    def _fetch_endpoint(",
    method(
        '''
        @staticmethod
        def _looks_mutating(tag: str) -> bool:
            """Conservatively classify action-like endpoint tags.

            Matching is token-based rather than raw substring-based, avoiding false
            positives such as ``settings_status_lua.lua`` containing ``set``.
            CamelCase action names are split before tokenization.
            """
            camel_split = re.sub(r"([a-z0-9])([A-Z])", r"\\1_\\2", tag)
            tokens = re.findall(r"[a-z0-9]+", camel_split.lower())
            if any(token in _MUTATING_TOKENS for token in tokens):
                return True
            return any(
                token.startswith(prefix)
                for token in tokens
                for prefix in _MUTATING_COMPOUND_PREFIXES
            )
        '''
    ),
)

text = replace_between(
    text,
    "    def _do_fetch_endpoint(",
    "    @staticmethod\n    def _classify_body",
    method(
        '''
        def _do_fetch_endpoint(
            self, ep: Endpoint, retry_session: bool = True
        ) -> Optional[str]:
            """GET one endpoint, recovering one expired authenticated session."""
            if self._requests_made >= self.max_requests:
                if not ep.fetched:
                    ep.skipped_reason = "request-budget"
                return None
            url = f"{self.api.base_url}{ep.url()}"
            attempted = False
            try:
                self._tick(f"{ep.type:10s} GET {ep.url()}")
                self._requests_made += 1
                attempted = True
                r = self.api.session.get(url, headers=self.api.NO_CACHE, timeout=8)
                text = r.text

                if self.api._is_session_expired(text):
                    if retry_session and self.api.login():
                        # Re-arm menuData after login before replaying it; login resets
                        # the per-session WebUI navigation state on AGZHM firmware.
                        if ep.type == "menuData" and self._requests_made < self.max_requests:
                            parent = self._data_parent_view.get(ep.tag)
                            if parent:
                                self._arm_view(parent, source=f"rearm-for:{ep.url()}")
                            elif ep.tag.endswith("_homepage_lua.lua"):
                                self._arm_view("homePage", source=f"rearm-for:{ep.url()}")
                        if self._requests_made < self.max_requests:
                            return self._do_fetch_endpoint(ep, retry_session=False)
                        ep.error = "session recovered but request budget prevented retry"
                    else:
                        ep.error = "session expired and automatic re-login failed"
                    ep.fetched = True
                    ep.status = r.status_code
                    ep.content_type = r.headers.get("Content-Type", "")
                    ep.bytes = len(text)
                    ep.sample = text[: self.sample_chars]
                    ep.shape = "session-timeout"
                    self._errors += 1
                    return None

                ep.fetched = True
                ep.status = r.status_code
                ep.content_type = r.headers.get("Content-Type", "")
                ep.bytes = len(text)
                ep.sample = text[: self.sample_chars]
                if not 200 <= r.status_code < 400:
                    ep.error = f"HTTP {r.status_code}"
                    self._errors += 1
                    return None
                self._classify_body(ep, text)
                return text
            except requests.RequestException as exc:
                ep.error = str(exc)
                self._errors += 1
                return None
            finally:
                if attempted:
                    time.sleep(self.delay)
        '''
    ),
)

path.write_text(text, encoding="utf-8")


# --------------------------------------------------------------------- CLI
path = Path("h388x_cli/cli.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '''        help="Refresh stats every N seconds (Ctrl+C to stop).",
    ),
):
    """Display DSL line statistics (optionally live with --watch)."""
''',
    '''        help="Refresh stats every N seconds (Ctrl+C to stop).",
        min=0.1,
    ),
):
    """Display DSL line statistics (optionally live with --watch)."""
''',
    1,
)

text = replace_between(
    text,
    "@app.command(\n    context_settings={\"allow_extra_args\": True, \"ignore_unknown_options\": True},\n)\ndef watch(\n",
    "# --------------------------------------------------------------------- logout",
    dedent(
        '''
        @app.command(
            context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
        )
        def watch(
            ctx: typer.Context,
            interval: float = typer.Argument(
                ...,
                help="Refresh every N seconds (decimals allowed).",
                min=0.1,
            ),
            keep_going: bool = typer.Option(
                False,
                "--keep-going",
                help="Continue refreshing when the child command exits non-zero.",
            ),
            command: List[str] = typer.Argument(
                ...,
                help=(
                    "h388x subcommand to repeat, with its own flags. "
                    "Example: `h388x watch 5 voip` or `h388x watch 2 clients --leases`."
                ),
            ),
        ):
            """Re-run any h388x command in a loop (Unix watch(1) style).

            By default a failed child command stops the wrapper and propagates its
            exit status. Use ``--keep-going`` only when repeated retries are intended.
            """
            import shutil
            import subprocess

            h388x_bin = shutil.which("h388x")
            if h388x_bin:
                argv = [h388x_bin, *command]
            else:
                argv = [sys.executable, "-m", "h388x_cli.cli", *command]

            clear_cmd = "cls" if os.name == "nt" else "clear"
            try:
                while True:
                    os.system(clear_cmd)
                    result = subprocess.run(argv, check=False)
                    if result.returncode and not keep_going:
                        code = result.returncode if 1 <= result.returncode <= 255 else 1
                        raise typer.Exit(code=code)
                    if result.returncode and keep_going:
                        console.print(
                            f"[yellow]Child command exited {result.returncode}; retrying.[/yellow]"
                        )
                    time.sleep(interval)
            except KeyboardInterrupt:
                return
        '''
    ).strip(),
)

text = replace_between(
    text,
    "@app.command()\ndef logout(\n",
    "# --------------------------------------------------------------------- reboot",
    dedent(
        '''
        @app.command()
        def logout(
            host: str = _host_opt(),
            user: str = _user_opt(),
            password: Optional[str] = _pwd_opt(),
            insecure: bool = _insecure_opt(),
        ):
            """Log out of the modem and clear the cached session for this host.

            A valid cached SID/token is enough: unlike ordinary commands, logout does
            not require the admin password merely to reuse and release that session.
            """
            resolved_password = password or os.environ.get("H388X_PASSWORD") or ""
            api = ZTEH388XAPI(
                host=host,
                username=user,
                password=resolved_password,
                verify_tls=not insecure,
            )
            try:
                if not api.has_cached_session:
                    if not resolved_password:
                        if state.json:
                            _emit_json({
                                "logout": "failed",
                                "error": "no cached session and no password available",
                            })
                        else:
                            console.print(
                                "[red]No cached session and no password available.[/red]"
                            )
                        raise typer.Exit(code=1)
                    if not api.login():
                        if state.json:
                            _emit_json({"logout": "failed", "error": "login failed"})
                        else:
                            console.print("[red]Login failed.[/red]")
                        raise typer.Exit(code=1)

                api.logout()
                if state.json:
                    _emit_json({"logout": "ok"})
                else:
                    console.print("[green]Session terminated and cache cleared.[/green]")
            except typer.Exit:
                raise
            except Exception as exc:
                if state.json:
                    _emit_json({"logout": "failed", "error": str(exc)})
                else:
                    console.print(f"[red]Logout failed: {exc}[/red]")
                raise typer.Exit(code=1)
            finally:
                try:
                    api.close()
                except Exception:
                    pass
        '''
    ).strip(),
)
path.write_text(text, encoding="utf-8")


# -------------------------------------------------------------------- tests
path = Path("tests/test_discovery.py")
tests = path.read_text(encoding="utf-8")
tests += dedent(
    '''

    def test_endpoint_url_encodes_extra_query_values_without_mangling_tag():
        ep = Endpoint(
            type="menuData",
            tag="foo/bar.lua",
            extras={"name": "a b&c", "value": "x=y"},
        )
        assert ep.url() == "/?_type=menuData&_tag=foo/bar.lua&name=a%20b%26c&value=x%3Dy"


    def test_asset_paths_resolve_relative_to_referring_asset():
        assert Spider._normalize_path("../common/app.js", "/js/pages/status.html") == "/js/common/app.js"
        assert Spider._normalize_path("./widget.js?cache=1#x", "/js/pages/status.html") == "/js/pages/widget.js"
        assert Spider._normalize_path("/root/app.js", "/js/pages/status.html") == "/root/app.js"
        assert Spider._normalize_path("https://evil.example/x.js", "/js/pages/status.html") == ""
        assert Spider._normalize_path("//evil.example/x.js", "/js/pages/status.html") == ""


    def test_mutating_classifier_uses_semantic_tokens_not_substrings():
        assert Spider._looks_mutating("settings_status_lua.lua") is False
        assert Spider._looks_mutating("wlan_setting_lua.lua") is False
        assert Spider._looks_mutating("firewall_add_rule_lua.lua") is True
        assert Spider._looks_mutating("do_download_usercfg.lua") is True
        assert Spider._looks_mutating("devmgr_restartmgr_lua.lua") is True
        assert Spider._looks_mutating("firmwareUpdate.lua") is True


    def test_session_timeout_relogin_retries_and_records_only_final_payload():
        api = MagicMock()
        api.base_url = "http://modem.test"
        api.NO_CACHE = {}
        timeout = MagicMock()
        timeout.status_code = 200
        timeout.headers = {"Content-Type": "text/xml"}
        timeout.text = "<root>SessionTimeout</root>"
        success = MagicMock()
        success.status_code = 200
        success.headers = {"Content-Type": "text/xml"}
        success.text = "<root><OBJ_X></OBJ_X></root>"
        api.session.get.side_effect = [timeout, success]
        api._is_session_expired.side_effect = lambda body: "SessionTimeout" in body
        api.login.return_value = True
        spider = Spider(api, max_requests=2, delay=0)
        ep = Endpoint(type="menuView", tag="statusMgr")

        body = spider._do_fetch_endpoint(ep)

        assert body == success.text
        assert api.login.call_count == 1
        assert api.session.get.call_count == 2
        assert spider._requests_made == 2
        assert ep.shape == "xml-empty"
        assert ep.sample == success.text
        assert ep.error is None


    def test_session_timeout_failed_relogin_is_recorded_as_error():
        api = MagicMock()
        api.base_url = "http://modem.test"
        api.NO_CACHE = {}
        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Type": "text/xml"}
        response.text = "<root>SessionTimeout</root>"
        api.session.get.return_value = response
        api._is_session_expired.return_value = True
        api.login.return_value = False
        spider = Spider(api, max_requests=2, delay=0)
        ep = Endpoint(type="menuView", tag="statusMgr")

        assert spider._do_fetch_endpoint(ep) is None
        assert ep.shape == "session-timeout"
        assert "re-login failed" in ep.error
        assert spider._errors == 1


    def test_session_retry_respects_spider_request_budget():
        api = MagicMock()
        api.base_url = "http://modem.test"
        api.NO_CACHE = {}
        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Type": "text/xml"}
        response.text = "<root>SessionTimeout</root>"
        api.session.get.return_value = response
        api._is_session_expired.return_value = True
        api.login.return_value = True
        spider = Spider(api, max_requests=1, delay=0)
        ep = Endpoint(type="menuView", tag="statusMgr")

        assert spider._do_fetch_endpoint(ep) is None
        assert api.session.get.call_count == 1
        assert "request budget" in ep.error
        assert spider._requests_made == 1
    '''
)
path.write_text(tests, encoding="utf-8")


Path("tests/test_resilience_cli.py").write_text(
    dedent(
        '''
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
        '''
    ).lstrip(),
    encoding="utf-8",
)
