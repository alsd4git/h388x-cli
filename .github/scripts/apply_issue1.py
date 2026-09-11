from pathlib import Path
from textwrap import dedent, indent


def replace_between(text: str, start: str, end: str, replacement: str) -> str:
    i = text.index(start)
    j = text.index(end, i)
    return text[:i] + replacement.rstrip() + "\n\n" + text[j:]


def method(source: str) -> str:
    return indent(dedent(source).strip() + "\n", "    ")


api_path = Path("h388x_cli/api.py")
api = api_path.read_text(encoding="utf-8")
api = api.replace(
    "from pathlib import Path\n",
    "from pathlib import Path\nfrom urllib.parse import urlsplit\n",
    1,
)
api = api.replace(
    "from .validation import (\n",
    "from .errors import ParseError, ProtocolError, SessionExpiredError, TransportError\n"
    "from .validation import (\n",
    1,
)

old_host = '''        host = (host or "").strip()
        if "://" in host:
            self.base_url = host.rstrip("/")
        else:
            self.base_url = f"http://{host}".rstrip("/")
'''
new_host = '''        host = (host or "").strip()
        candidate = host if "://" in host else f"http://{host}"
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"}:
            raise ProtocolError(f"unsupported modem URL scheme: {parsed.scheme!r}")
        if not parsed.hostname:
            raise ProtocolError("modem host is empty or invalid")
        if parsed.username is not None or parsed.password is not None:
            raise ProtocolError("modem URL must not contain user information")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ProtocolError("modem URL must contain only scheme, host and optional port")
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
'''
if old_host not in api:
    raise SystemExit("host normalization block not found")
api = api.replace(old_host, new_host, 1)

api = replace_between(
    api,
    "    @classmethod\n    def _parse_instances(",
    "    @staticmethod\n    def _is_session_expired",
    method(
        '''
        @classmethod
        def _parse_instances(cls, xml_text: str, root_element: str) -> List[Dict[str, str]]:
            """Parse the standard Instance/ParaName/ParaValue envelope.

            A syntactically valid response with no matching instances is a real empty
            result. Malformed XML or mismatched name/value cardinality is a protocol
            failure and must never be reported as an empty table.
            """
            try:
                tree = ET.fromstring(xml_text)
            except ET.ParseError as exc:
                raise ParseError(f"invalid XML while parsing {root_element}: {exc}") from exc

            out: List[Dict[str, str]] = []
            for index, instance in enumerate(tree.findall(f".//{root_element}/Instance")):
                names = [
                    cls._strip_prefix(node.text or "")
                    for node in instance.findall("ParaName")
                ]
                values = [node.text or "" for node in instance.findall("ParaValue")]
                if len(names) != len(values):
                    raise ParseError(
                        f"malformed {root_element} instance {index}: "
                        f"{len(names)} ParaName values but {len(values)} ParaValue values"
                    )
                out.append(dict(zip(names, values)))
            return out
        '''
    ),
)

# Insert two tiny transport/protocol helpers directly after session-expiry detection.
needle = '''    @staticmethod
    def _is_session_expired(text: str) -> bool:
        return "SessionTimeout" in text

'''
replacement = needle + method(
    '''
    @staticmethod
    def _require_http_success(resp: requests.Response, context: str) -> None:
        if 200 <= resp.status_code < 400:
            return
        raise ProtocolError(f"{context}: HTTP {resp.status_code}")

    def _get_response(self, url: str, *, timeout: float = 8) -> requests.Response:
        try:
            resp = self.session.get(url, headers=self.NO_CACHE, timeout=timeout)
        except requests.RequestException as exc:
            raise TransportError(f"GET {url} failed: {exc}") from exc
        self._require_http_success(resp, f"GET {url}")
        return resp
    '''
)
if needle not in api:
    raise SystemExit("session-expiry helper block not found")
api = api.replace(needle, replacement, 1)

api = replace_between(
    api,
    "    def _menudata(\n",
    "    def _refresh_session_token(",
    method(
        '''
        def _menudata(
            self,
            view_url: str,
            data_url: str,
            root_element: str,
            retry: bool = True,
        ) -> List[Dict[str, str]]:
            """Fetch menuView + menuData, retrying one expired session."""
            self._get_response(f"{self.base_url}{view_url}")
            resp = self._get_response(f"{self.base_url}{data_url}")
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata(view_url, data_url, root_element, retry=False)
                raise SessionExpiredError(
                    f"session expired while reading {data_url}; automatic re-login failed"
                )
            return self._parse_instances(resp.text, root_element)
        '''
    ),
)

api = replace_between(
    api,
    "    def _post_action(\n",
    "    def _menudata_multi(",
    method(
        '''
        def _post_action(
            self,
            view_url: str,
            data_url: str,
            action: str,
            fields: Dict[str, str],
            retry: bool = True,
        ) -> Tuple[bool, str]:
            """POST a write action while preserving the public ``(ok, body)`` contract."""
            try:
                view = self.session.get(
                    f"{self.base_url}{view_url}", headers=self.NO_CACHE, timeout=8
                )
            except requests.RequestException as exc:
                return False, f"transport error arming view: {exc}"
            if not 200 <= view.status_code < 400:
                return False, f"protocol error arming view: HTTP {view.status_code}"

            if not self._fetch_fresh_session_token():
                if retry and self.login():
                    return self._post_action(view_url, data_url, action, fields, retry=False)
                return False, "could not refresh session token; write was not attempted"

            payload = {
                "IF_ACTION": action,
                **{k: ("" if v is None else str(v)) for k, v in fields.items()},
                "_sessionTOKEN": self.session_token or "",
            }
            try:
                resp = self.session.post(
                    f"{self.base_url}{data_url}",
                    data=payload,
                    headers=self.NO_CACHE,
                    timeout=10,
                )
            except requests.RequestException as exc:
                return False, f"transport error posting action: {exc}"

            body = resp.text
            if self._is_session_expired(body):
                if retry and self.login():
                    return self._post_action(view_url, data_url, action, fields, retry=False)
                return False, body
            if not 200 <= resp.status_code < 400:
                return False, f"HTTP {resp.status_code}: {body}"

            self._refresh_session_token(body)
            try:
                root = ET.fromstring(body)
            except ET.ParseError as exc:
                return False, f"protocol error: invalid XML response: {exc}"
            error_str = root.findtext(".//IF_ERRORSTR")
            if error_str is None:
                return False, "protocol error: response does not contain IF_ERRORSTR"
            return error_str.strip() == "SUCC", body
        '''
    ),
)

api = replace_between(
    api,
    "    def _menudata_multi(\n",
    "    # ---------------------------------------------------------------- DSL stats",
    method(
        '''
        def _menudata_multi(
            self,
            view_url: str,
            data_url: str,
            root_elements: List[str],
            retry: bool = True,
        ) -> Dict[str, List[Dict[str, str]]]:
            """Like ``_menudata`` but parse multiple roots from one response."""
            self._get_response(f"{self.base_url}{view_url}")
            resp = self._get_response(f"{self.base_url}{data_url}")
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata_multi(view_url, data_url, root_elements, retry=False)
                raise SessionExpiredError(
                    f"session expired while reading {data_url}; automatic re-login failed"
                )
            return {
                root: self._parse_instances(resp.text, root)
                for root in root_elements
            }
        '''
    ),
)

api = replace_between(
    api,
    "    def get_wifi_clients(",
    "    # ---------------------------------------------------------------- Wi-Fi",
    method(
        '''
        def get_wifi_clients(self, retry: bool = True) -> List[Dict[str, str]]:
            """Return Wi-Fi clients after reproducing the WebUI arming sequence."""
            self._get_response(f"{self.base_url}{self.LOCALNET_VIEW_URL}")
            wlan = self._get_response(f"{self.base_url}{self.WLAN_APS_URL}")
            if self._is_session_expired(wlan.text):
                if retry and self.login():
                    return self.get_wifi_clients(retry=False)
                raise SessionExpiredError("session expired while arming Wi-Fi client view")
            clients = self._get_response(f"{self.base_url}{self.WIFI_CLIENTS_URL}")
            if self._is_session_expired(clients.text):
                if retry and self.login():
                    return self.get_wifi_clients(retry=False)
                raise SessionExpiredError("session expired while reading Wi-Fi clients")
            return self._parse_instances(clients.text, "OBJ_ACCESSDEV_ID")
        '''
    ),
)

api = replace_between(
    api,
    "    def _menudata_raw(\n",
    "    def get_topology(",
    method(
        '''
        def _menudata_raw(
            self,
            view_url: str,
            data_url: str,
            retry: bool = True,
        ) -> str:
            """Like ``_menudata`` but return the validated raw response body."""
            self._get_response(f"{self.base_url}{view_url}")
            resp = self._get_response(f"{self.base_url}{data_url}")
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._menudata_raw(view_url, data_url, retry=False)
                raise SessionExpiredError(
                    f"session expired while reading {data_url}; automatic re-login failed"
                )
            return resp.text
        '''
    ),
)

api = replace_between(
    api,
    "    def get_topology(",
    "    def get_band_steering(",
    method(
        '''
        def get_topology(self, retry: bool = True) -> Dict[str, Any]:
            """Return the EasyMesh topology, raising ``ParseError`` on invalid JSON."""
            body = self._menudata_raw(self.TOPOLOGY_VIEW_URL, self.TOPOLOGY_URL, retry)
            try:
                return _json.loads(body)
            except _json.JSONDecodeError as exc:
                raise ParseError(f"invalid topology JSON: {exc}") from exc
        '''
    ),
)

api = replace_between(
    api,
    "    def _hiddendata(\n",
    "    def get_sntp(",
    method(
        '''
        def _hiddendata(
            self, data_url: str, root_element: str, retry: bool = True,
        ) -> List[Dict[str, str]]:
            """Fetch a hiddenData endpoint without collapsing failures to an empty list."""
            resp = self._get_response(f"{self.base_url}{data_url}")
            if self._is_session_expired(resp.text):
                if retry and self.login():
                    return self._hiddendata(data_url, root_element, retry=False)
                raise SessionExpiredError(
                    f"session expired while reading {data_url}; automatic re-login failed"
                )
            return self._parse_instances(resp.text, root_element)
        '''
    ),
)

api_path.write_text(api, encoding="utf-8")


# Make the installed console entry point the exception boundary. Direct library
# users receive typed exceptions; CLI users receive one stable document/message.
cli_path = Path("h388x_cli/cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = cli.replace(
    "from .discovery import Spider\n",
    "from .discovery import Spider\nfrom .errors import H388XError\n",
    1,
)
old_bottom = '''if __name__ == "__main__":
    app()
'''
new_bottom = '''def run_cli() -> None:
    """Console entry point with stable handling for operational API errors."""
    try:
        app()
    except H388XError as exc:
        if state.json:
            _emit_json({"ok": False, "error": {"type": exc.code, "message": str(exc)}})
        else:
            console.print(f"[red]{exc.code}:[/red] {exc}")
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    run_cli()
'''
if old_bottom not in cli:
    raise SystemExit("CLI bottom entry point not found")
cli = cli.replace(old_bottom, new_bottom, 1)
cli_path.write_text(cli, encoding="utf-8")


pyproject_path = Path("pyproject.toml")
pyproject = pyproject_path.read_text(encoding="utf-8")
pyproject = pyproject.replace(
    'h388x = "h388x_cli.cli:app"',
    'h388x = "h388x_cli.cli:run_cli"',
    1,
)
pyproject_path.write_text(pyproject, encoding="utf-8")


# Update legacy expectations whose old behavior intentionally collapsed errors.
test_api_path = Path("tests/test_api_flow.py")
tests = test_api_path.read_text(encoding="utf-8")
tests = tests.replace(
    "from h388x_cli.api import ZTEH388XAPI\n",
    "from h388x_cli.api import ZTEH388XAPI\n"
    "from h388x_cli.errors import ParseError, SessionExpiredError\n",
    1,
)
old_timeout = '''@responses.activate
def test_menudata_returns_empty_on_session_timeout_when_no_relogin(api):
    """If we say ``retry=False`` and the modem says SessionTimeout, we get []."""
    view = f"{HOST}/?_type=menuView&_tag=accountMgr&Menu3Location=0"
    data = f"{HOST}/?_type=menuData&_tag=devauth_accountmgr_lua.lua"
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root>SessionTimeout</root>", status=200)

    rows = api._menudata(
        "/?_type=menuView&_tag=accountMgr&Menu3Location=0",
        "/?_type=menuData&_tag=devauth_accountmgr_lua.lua",
        "OBJ_USERINFO_ID",
        retry=False,
    )
    assert rows == []
'''
new_timeout = '''@responses.activate
def test_menudata_raises_session_expired_when_retry_is_exhausted(api):
    """An expired session is not a legitimate empty table."""
    view = f"{HOST}/?_type=menuView&_tag=accountMgr&Menu3Location=0"
    data = f"{HOST}/?_type=menuData&_tag=devauth_accountmgr_lua.lua"
    responses.add(responses.GET, view, body="<root/>", status=200)
    responses.add(responses.GET, data, body="<root>SessionTimeout</root>", status=200)

    with pytest.raises(SessionExpiredError):
        api._menudata(
            "/?_type=menuView&_tag=accountMgr&Menu3Location=0",
            "/?_type=menuData&_tag=devauth_accountmgr_lua.lua",
            "OBJ_USERINFO_ID",
            retry=False,
        )
'''
if old_timeout not in tests:
    raise SystemExit("legacy SessionTimeout test not found")
tests = tests.replace(old_timeout, new_timeout, 1)
old_topology = '''@responses.activate
def test_get_topology_returns_empty_on_invalid_json(api):
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_VIEW_URL}",
        body="<root/>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_URL}",
        body="not json {{{",
        status=200,
    )
    assert api.get_topology(retry=False) == {}
'''
new_topology = '''@responses.activate
def test_get_topology_raises_on_invalid_json(api):
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_VIEW_URL}",
        body="<root/>",
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HOST}{api.TOPOLOGY_URL}",
        body="not json {{{",
        status=200,
    )
    with pytest.raises(ParseError):
        api.get_topology(retry=False)
'''
if old_topology not in tests:
    raise SystemExit("legacy topology parse test not found")
tests = tests.replace(old_topology, new_topology, 1)
test_api_path.write_text(tests, encoding="utf-8")


Path("tests/test_error_semantics.py").write_text(
    dedent(
        '''
        import json

        import pytest
        import requests
        import responses

        from h388x_cli import cli
        from h388x_cli.api import ZTEH388XAPI
        from h388x_cli.errors import ParseError, ProtocolError, TransportError


        HOST = "http://modem.test"


        def test_parse_instances_distinguishes_valid_empty_from_invalid_xml():
            assert ZTEH388XAPI._parse_instances("<root/>", "OBJ_X") == []
            with pytest.raises(ParseError):
                ZTEH388XAPI._parse_instances("not xml", "OBJ_X")


        def test_parse_instances_rejects_mismatched_name_value_cardinality():
            body = (
                "<root><OBJ_X><Instance>"
                "<ParaName>A</ParaName><ParaValue>1</ParaValue>"
                "<ParaName>B</ParaName>"
                "</Instance></OBJ_X></root>"
            )
            with pytest.raises(ParseError, match="ParaName"):
                ZTEH388XAPI._parse_instances(body, "OBJ_X")


        @responses.activate
        def test_menudata_transport_failure_is_explicit(tmp_path):
            api = ZTEH388XAPI(HOST, cache_enabled=False, cache_dir=tmp_path)
            responses.add(
                responses.GET,
                f"{HOST}{api.ADMIN_USERS_VIEW_URL}",
                body=requests.ConnectionError("offline"),
            )
            with pytest.raises(TransportError, match="offline"):
                api.get_admin_users(retry=False)


        @responses.activate
        def test_menudata_http_failure_is_protocol_error(tmp_path):
            api = ZTEH388XAPI(HOST, cache_enabled=False, cache_dir=tmp_path)
            responses.add(
                responses.GET,
                f"{HOST}{api.ADMIN_USERS_VIEW_URL}",
                body="broken",
                status=503,
            )
            with pytest.raises(ProtocolError, match="HTTP 503"):
                api.get_admin_users(retry=False)


        @pytest.mark.parametrize(
            "host",
            [
                "ftp://192.168.1.1",
                "http://admin:secret@192.168.1.1",
                "http://192.168.1.1/admin",
                "http://192.168.1.1?x=1",
            ],
        )
        def test_constructor_rejects_unsafe_or_ambiguous_base_urls(host):
            with pytest.raises(ProtocolError):
                ZTEH388XAPI(host, cache_enabled=False)


        @responses.activate
        def test_post_action_does_not_post_without_fresh_csrf_token(tmp_path):
            api = ZTEH388XAPI(HOST, "admin", "password", cache_enabled=False, cache_dir=tmp_path)
            api.session_token = "STALE"
            responses.add(responses.GET, f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}", body="<root/>")
            responses.add(
                responses.GET,
                f"{HOST}/?_type=loginData&_tag=login_entry",
                body="not-json",
            )
            api.login = lambda: False  # type: ignore[assignment]

            ok, message = api.set_web_login_timeout(10)

            assert ok is False
            assert "write was not attempted" in message
            assert not [call for call in responses.calls if call.request.method == "POST"]


        @responses.activate
        def test_post_action_parses_success_structurally(tmp_path):
            api = ZTEH388XAPI(HOST, "admin", "password", cache_enabled=False, cache_dir=tmp_path)
            api.session_token = "OLD"
            responses.add(responses.GET, f"{HOST}{api.WEB_TIMEOUT_VIEW_URL}", body="<root/>")
            responses.add(
                responses.GET,
                f"{HOST}/?_type=loginData&_tag=login_entry",
                json={"sess_token": "FRESH"},
            )
            responses.add(
                responses.POST,
                f"{HOST}{api.WEB_TIMEOUT_URL}",
                body="<root><IF_ERRORSTR>  SUCC  </IF_ERRORSTR><IF_ERRORID>0</IF_ERRORID></root>",
            )
            ok, _ = api.set_web_login_timeout(10)
            assert ok is True


        def test_console_entrypoint_turns_api_error_into_stable_human_exit(monkeypatch, capsys):
            cli.state.json = False

            def fail():
                raise TransportError("modem offline")

            monkeypatch.setattr(cli, "app", fail)
            with pytest.raises(SystemExit) as caught:
                cli.run_cli()
            assert caught.value.code == 1
            assert "transport_error" in capsys.readouterr().out


        def test_console_entrypoint_turns_api_error_into_json(monkeypatch, capsys):
            cli.state.json = True

            def fail():
                raise ParseError("broken payload")

            monkeypatch.setattr(cli, "app", fail)
            with pytest.raises(SystemExit) as caught:
                cli.run_cli()
            assert caught.value.code == 1
            payload = json.loads(capsys.readouterr().out)
            assert payload == {
                "ok": False,
                "error": {"type": "parse_error", "message": "broken payload"},
            }
        '''
    ).lstrip(),
    encoding="utf-8",
)
