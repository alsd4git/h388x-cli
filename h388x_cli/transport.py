"""HTTP/session/cache transport primitives for the H388X WebUI protocol."""

from __future__ import annotations

import hashlib
import json as _json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlsplit

import requests

from .errors import ParseError, ProtocolError, SessionExpiredError, TransportError


def _default_cache_dir() -> Path:
    """Return the per-user cache directory for h388x-cli."""
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "h388x-cli"


class H388XTransport:
    """Reusable authenticated transport used by :class:`ZTEH388XAPI`."""

    NO_CACHE = {"Cache-Control": "no-cache"}

    def __init__(
        self,
        host: str = "192.168.1.1",
        username: str = "admin",
        password: str = "",
        verify_tls: bool = True,
        cache_enabled: bool = True,
        cache_dir: Optional[Path] = None,
    ):
        """
        ``host`` can be a bare IP/hostname (``192.168.1.1``,
        ``modem.example.com``) or a full URL with explicit scheme
        (``http://192.168.1.1``, ``https://modem.example.com:8443``).
        When the scheme is omitted, ``http://`` is assumed; any trailing
        slash is stripped so ``base_url`` is safe to concatenate with
        absolute paths.

        When ``cache_enabled`` is true (default) a previously persisted
        SID cookie + session token for this ``(host, username)`` pair is
        loaded so subsequent CLI invocations skip the login handshake.
        Pass a custom ``cache_dir`` to override the default
        ``~/.cache/h388x-cli`` location (mostly useful for tests).
        """
        host = (host or "").strip()
        candidate = host if "://" in host else f"http://{host}"
        parsed = urlsplit(candidate)
        if parsed.scheme not in {"http", "https"}:
            raise ProtocolError(f"unsupported modem URL scheme: {parsed.scheme!r}")
        if not parsed.hostname:
            raise ProtocolError("modem host is empty or invalid")
        if parsed.username is not None or parsed.password is not None:
            raise ProtocolError("modem URL must not contain user information")
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ProtocolError(
                "modem URL must contain only scheme, host and optional port"
            )
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = verify_tls
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "X-Requested-With": "XMLHttpRequest",
                # The modem's CSRF check refuses menuData requests whose Origin
                # / Referer doesn't match its own host. On direct LAN access this
                # is set automatically by the browser; over HTTPS reverse proxies
                # (or anywhere the requests session isn't a real browser) we
                # have to set them explicitly or every menuData returns
                # SessionTimeout even with a valid SID cookie.
                "Origin": self.base_url,
                "Referer": f"{self.base_url}/",
            }
        )
        self.session_token: Optional[str] = None

        self.cache_enabled = cache_enabled
        self._cache_dir = cache_dir or _default_cache_dir()
        if cache_enabled:
            self._load_cache()

    def _cache_path(self) -> Path:
        """Per-(host, user) cache file path under the cache directory."""
        key = hashlib.sha256(f"{self.base_url}|{self.username}".encode()).hexdigest()[
            :16
        ]
        return self._cache_dir / f"session-{key}.json"

    def _load_cache(self) -> bool:
        """Hydrate the requests session from a previously saved cache.

        Returns True when a usable cache was found and applied. Any
        IO/JSON error is swallowed — a missing or corrupted cache just
        forces a fresh login on next request.
        """
        path = self._cache_path()
        try:
            with path.open("r") as f:
                data = _json.load(f)
        except (OSError, ValueError):
            return False
        token = data.get("session_token")
        cookies = data.get("cookies") or {}
        if not token or not cookies:
            return False
        self.session_token = token
        # Set the restored cookies pinned to the modem host. Without an
        # explicit domain, requests defaults to ``domain=""`` and any
        # ``Set-Cookie`` reply from the server (which carries the request
        # host as its domain) would coexist as a duplicate — causing
        # ``CookieConflictError`` on ``cookies.get("SID")``.
        from urllib.parse import urlparse

        host = urlparse(self.base_url).hostname or ""
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=host, path="/")
        return True

    def _save_cache(self) -> None:
        """Persist the live SID cookie + session token to disk (0600)."""
        if not self.cache_enabled or not self.session_token:
            return
        cookies = {c.name: c.value for c in self.session.cookies}
        if "SID" not in cookies:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        path = self._cache_path()
        payload = {
            "host": self.base_url,
            "user": self.username,
            "session_token": self.session_token,
            "cookies": cookies,
        }
        tmp = path.with_suffix(".tmp")
        try:
            with tmp.open("w") as f:
                _json.dump(payload, f)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass

    def _clear_cache(self) -> None:
        """Remove the on-disk cache for this (host, user) pair, if any."""
        try:
            self._cache_path().unlink(missing_ok=True)
        except OSError:
            pass

    def _has_sid_cookie(self) -> bool:
        """True iff the session jar carries at least one ``SID`` cookie.

        Avoids ``CookieConflictError`` from ``RequestsCookieJar.get`` when
        more than one ``SID`` is present (different domain/path scopes).
        """
        return any(c.name == "SID" for c in self.session.cookies)

    @property
    def has_cached_session(self) -> bool:
        """Whether a token and at least one SID cookie are ready for reuse."""
        return bool(self.session_token and self._has_sid_cookie())

    def login(self) -> bool:
        try:
            self.session.get(f"{self.base_url}/", timeout=8)

            r1 = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_entry", timeout=8
            )
            self.session_token = r1.json().get("sess_token")
            if not self.session_token:
                return False

            r2 = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_token", timeout=8
            )
            try:
                salt = (ET.fromstring(r2.text).text or "").strip()
            except ET.ParseError:
                m = re.search(r"<[^>]+>(.*?)</[^>]+>", r2.text)
                salt = m.group(1).strip() if m else ""
            if not salt:
                return False

            hashed_pw = hashlib.sha256(f"{self.password}{salt}".encode()).hexdigest()
            payload = {
                "Username": self.username,
                "Password": hashed_pw,
                "_sessionTOKEN": self.session_token,
                "action": "login",
            }
            r3 = self.session.post(
                f"{self.base_url}/?_type=loginData&_tag=login_entry",
                data=payload,
                timeout=8,
            )

            try:
                new_token = r3.json().get("sess_token")
                if new_token:
                    self.session_token = new_token
            except ValueError:
                pass

            ok = self._has_sid_cookie()
            if ok:
                self._save_cache()
            return ok
        except requests.RequestException:
            return False

    @staticmethod
    def _strip_prefix(name: str) -> str:
        # Some endpoints (e.g. dhcp4s_dhcphostinfo_m.lua) prefix every ParaName
        # with the root element name, e.g. ``OBJ_DHCPHOSTINFO_ID.IPAddr``.
        # Normalize to the bare field name.
        if "." in name:
            return name.rsplit(".", 1)[-1]
        return name

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
            raise ParseError(
                f"invalid XML while parsing {root_element}: {exc}"
            ) from exc

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

    @staticmethod
    def _is_session_expired(text: str) -> bool:
        return "SessionTimeout" in text

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

    def _refresh_session_token(self, body: str) -> None:
        """Update ``self.session_token`` from a POST response, if present.

        The modem rotates ``_sessionTOKEN`` on every successful write and
        embeds the new value in the response (either as the JSON field
        ``sess_token`` for ``loginData`` flows, or inside ``<sess_token>``
        in the standard XML response envelope). Silently no-op on any
        parse error — the next request will just trigger a SessionTimeout
        + re-login.
        """
        try:
            tok = _json.loads(body).get("sess_token")
            if tok:
                self.session_token = tok
                return
        except (ValueError, TypeError):
            pass
        m = re.search(r"<sess_token>([^<]+)</sess_token>", body)
        if m:
            self.session_token = m.group(1).strip()

    def _fetch_fresh_session_token(self) -> bool:
        """Pull the current ``_sessionTOKEN`` for our SID cookie.

        The modem rotates the CSRF token at every authenticated request,
        and ``login_entry`` (the same endpoint used during login) returns
        the live value as JSON ``{"sess_token": "..."}``. Called right
        before a write so we don't fight a stale token loaded from the
        session cache. Returns True on success.
        """
        try:
            r = self.session.get(
                f"{self.base_url}/?_type=loginData&_tag=login_entry",
                headers=self.NO_CACHE,
                timeout=8,
            )
            tok = r.json().get("sess_token")
            if tok:
                self.session_token = tok
                return True
        except (requests.RequestException, ValueError):
            pass
        return False

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
                return self._post_action(
                    view_url, data_url, action, fields, retry=False
                )
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
                return self._post_action(
                    view_url, data_url, action, fields, retry=False
                )
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
                return self._menudata_multi(
                    view_url, data_url, root_elements, retry=False
                )
            raise SessionExpiredError(
                f"session expired while reading {data_url}; automatic re-login failed"
            )
        return {root: self._parse_instances(resp.text, root) for root in root_elements}

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

    def _hiddendata(
        self,
        data_url: str,
        root_element: str,
        retry: bool = True,
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
