"""H388X system endpoint implementation mixin."""

from __future__ import annotations

import html as _html
import time
from typing import Any, Dict, List, Tuple

import requests


class SystemMixin:
    def get_device_info(self, retry: bool = True) -> Dict[str, str]:
        instances = self._menudata(
            self.DEV_INFO_VIEW_URL, self.DEV_INFO_URL, "OBJ_DEVINFO_ID", retry
        )
        return instances[0] if instances else {}

    def get_ra(self, retry: bool = True) -> Dict[str, str]:
        """Return the IPv6 Router Advertisement service config (OBJ_RAIS_ID)."""
        rows = self._menudata(
            self.DHCP6_VIEW_URL,
            self.RA_URL,
            "OBJ_RAIS_ID",
            retry,
        )
        return rows[0] if rows else {}

    def get_admin_users(self, retry: bool = True) -> List[Dict[str, str]]:
        """Return web admin accounts (OBJ_USERINFO_ID, ``devauth_accountmgr``).

        Each instance exposes ``Username`` and ``Right`` (privilege
        level). The modem's ``encode`` hint marks ``Password`` /
        ``NewPassword`` as write-only, so they never appear here.
        """
        return self._menudata(
            self.ADMIN_USERS_VIEW_URL,
            self.ADMIN_USERS_URL,
            "OBJ_USERINFO_ID",
            retry,
        )

    def get_web_login_timeout(self, retry: bool = True) -> Dict[str, str]:
        """Return web UI session timeout (OBJ_USERIF_ID, single row).

        ``Timeout`` is expressed in minutes; controls how long an idle
        admin session stays valid before requiring a fresh login.
        """
        rows = self._menudata(
            self.WEB_TIMEOUT_VIEW_URL,
            self.WEB_TIMEOUT_URL,
            "OBJ_USERIF_ID",
            retry,
        )
        return rows[0] if rows else {}

    def set_web_login_timeout(
        self, minutes: int, inst_id: str = "IGD"
    ) -> Tuple[bool, str]:
        """Set the web UI idle session timeout (minutes).

        Posts ``IF_ACTION=Apply`` with ``Timeout`` and ``_InstID`` to
        ``web_login_timeout_lua.lua``. Returns ``(ok, raw_body)``.
        See ``firmware/notes/2026-05-29-write-actions-protocol.md`` for
        the convention.
        """
        return self._post_action(
            self.WEB_TIMEOUT_VIEW_URL,
            self.WEB_TIMEOUT_URL,
            action="Apply",
            fields={"_InstID": inst_id, "Timeout": str(int(minutes))},
        )

    def reboot(self) -> bool:
        # Reboot follows the same view-arming and rotating-CSRF-token flow as
        # every other write action. The previous implementation reused the
        # cached token after two GETs, so the modem rejected the POST as an
        # expired page before it could restart.
        ok, _body = self._post_action(
            self.REBOOT_VIEW_URL,
            self.REBOOT_URL,
            action="Restart",
            fields={"Btn_restart": ""},
        )
        return ok

    def download_config_backup(self, retry: bool = True) -> Tuple[bool, Any]:
        """Download the full modem configuration backup (``config.bin``).

        Non-mutating: it only reads and serializes the current config.
        Mirrors the WebUI "Backup configurazione" button:

        1. GET the ``usrCfgMgr`` view to arm it and read the per-render
           ``TOKEN_DOWNLOAD``. The view returns a "fake 404" reload page
           unless the session was just logged in, so when the token is
           absent we re-``login()`` once and retry.
        2. POST the ``fDownload`` multipart form (``config`` + the
           ``TOKEN_DOWNLOAD``) to ``do_download_usercfg.lua``; the modem
           streams back the binary config as an ``octet-stream``
           attachment.

        Returns ``(True, bytes)`` with the raw config on success, or
        ``(False, error_message)`` otherwise.
        """
        try:
            view = self.session.get(
                f"{self.base_url}{self.USRCFG_VIEW_URL}",
                headers=self.NO_CACHE,
                timeout=15,
            )
            m = self._TOKEN_DOWNLOAD_RE.search(view.text)
            if not m:
                # View not armed (fake-404). A fresh login arms it.
                if retry and self.login():
                    return self.download_config_backup(retry=False)
                return False, "could not arm config backup view (no TOKEN_DOWNLOAD)"

            token_download = _html.unescape(m.group(1))
            resp = self.session.post(
                f"{self.base_url}{self.CONFIG_DOWNLOAD_URL}",
                files={
                    "config": ("", ""),
                    "TOKEN_DOWNLOAD": ("", token_download),
                },
                headers=self.NO_CACHE,
                timeout=60,
            )
            ctype = resp.headers.get("Content-Type", "")
            if (
                resp.status_code != 200
                or "octet-stream" not in ctype
                or b"SessionTimeout" in resp.content[:200]
            ):
                if retry and self.login():
                    return self.download_config_backup(retry=False)
                return False, (
                    f"unexpected download response (status={resp.status_code}, "
                    f"content-type={ctype!r}, {len(resp.content)} bytes)"
                )
            return True, resp.content
        except requests.RequestException as e:
            return False, f"requests error: {e}"

    def _run_diagnostic(
        self,
        data_url: str,
        action: str,
        root: str,
        fields: Dict[str, str],
        result_key: str,
        still_running,
        poll_interval: float,
        max_wait: float,
    ) -> Tuple[bool, str]:
        """Start a TR-069-style diagnostic and poll for its result.

        POSTs ``IF_ACTION=<action>`` to kick the diagnostic off, then GETs
        the same endpoint every ``poll_interval`` seconds (up to
        ``max_wait``) until ``still_running(row)`` is False, at which point
        the ``result_key`` field holds the textual output. Returns
        ``(True, text)`` on success or ``(False, message)`` otherwise.
        """
        ok, body = self._post_action(
            self.NETDIAG_VIEW_URL,
            data_url,
            action=action,
            fields=fields,
        )
        if not ok:
            return False, f"could not start diagnostic: {body[:200]}"

        deadline = time.monotonic() + max_wait
        while time.monotonic() < deadline:
            try:
                r = self.session.get(
                    f"{self.base_url}{data_url}", headers=self.NO_CACHE, timeout=15
                )
            except requests.RequestException as e:
                return False, f"requests error while polling: {e}"
            rows = self._parse_instances(r.text, root)
            row = rows[0] if rows else {}
            if not still_running(row):
                val = row.get(result_key)
                if val and val != "NULL":
                    return True, _html.unescape(val)
                return False, (
                    "diagnostic finished without a result "
                    f"(state={row.get('DiagnosticsState')!r})"
                )
            time.sleep(poll_interval)
        return False, f"timeout after {max_wait:g}s waiting for diagnostic result"

    def ping(
        self,
        host: str,
        *,
        poll_interval: float = 3.0,
        max_wait: float = 60.0,
    ) -> Tuple[bool, str]:
        """Run a ping from the modem to ``host`` and return the output.

        Non-mutating: it only executes a diagnostic ping. Result text is
        the modem's own ``PingAck`` (per-reply lines + summary stats).

        The WebUI ping form only exposes the target ``Host`` (and an
        interface selector); repeat count / packet size / timeout are
        fixed server-side (4 × 56 bytes), so they are not parameters here.
        """
        fields = {
            "_InstID": "",
            "Host": host,
            "Interface": "",
        }
        return self._run_diagnostic(
            self.PING_URL,
            "PingDiagnosis",
            "OBJ_DEVPING_ID",
            fields,
            result_key="PingAck",
            still_running=lambda row: (row.get("PingAck") or "NULL") == "NULL",
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

    def traceroute(
        self,
        host: str,
        *,
        max_hops: int = 30,
        timeout_ms: int = 5000,
        protocol: str = "UDP",
        poll_interval: float = 3.0,
        max_wait: float = 120.0,
    ) -> Tuple[bool, str]:
        """Run a traceroute from the modem to ``host`` and return the output.

        Non-mutating: it only executes a diagnostic traceroute. Result
        text is the modem's own ``Result`` (per-hop lines).

        The WebUI form exposes ``Host``, ``MaxHopCount``, ``Timeout`` and
        ``Protocol``; probes-per-hop / packet size / DSCP are fixed
        server-side, so they are not parameters here.
        """
        fields = {
            "_InstID": "",
            "Host": host,
            "Interface": "",
            "Timeout": str(timeout_ms),
            "MaxHopCount": str(max_hops),
            "Protocol": protocol,
            "Control": "0",
        }
        return self._run_diagnostic(
            self.TRACEROUTE_URL,
            "TraceRouteDiagnosis",
            "OBJ_TRACERT_ID",
            fields,
            result_key="Result",
            still_running=lambda row: row.get("Flag") == "1",
            poll_interval=poll_interval,
            max_wait=max_wait,
        )

    def close(self) -> None:
        """Tear down the local requests session, keeping the modem session
        alive on the server so subsequent CLI invocations can resume from
        the on-disk cache. Called by the normal per-command teardown.
        """
        # Re-save the cookies even after read-only operations: the modem
        # bumps the SID's lifetime on every authenticated request, and we
        # might also have refreshed ``session_token`` mid-flow.
        self._save_cache()
        try:
            self.session.close()
        except Exception:
            pass

    def logout(self) -> None:
        """Explicitly log out of the modem session and wipe the cache.

        Use this when you want the next ``login()`` to start from a
        clean slate (e.g. switching admin user, or freeing the single
        admin slot the modem allows). The CLI exposes it as
        ``h388x logout``.
        """
        if self.session_token:
            try:
                # ``_sessionTOKEN`` rotates on authenticated requests. A
                # token restored from the local cache can therefore be stale
                # even though the SID cookie is still valid; refresh it before
                # asking the modem to release the admin session.
                self._fetch_fresh_session_token()
                self.session.post(
                    f"{self.base_url}/?_type=loginData&_tag=logout_entry",
                    data={
                        "IF_LogOff": "1",
                        "_sessionTOKEN": self.session_token,
                    },
                    headers=self.NO_CACHE,
                    timeout=8,
                )
            except requests.RequestException:
                pass
        self._clear_cache()
        self.session.cookies.clear()
        self.session.close()
