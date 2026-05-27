"""
Read-only endpoint discovery spider for the H388X web UI.

The goal is to crawl the modem's authenticated web UI and produce a
machine-readable map of every URL of the form

    /?_type=<TYPE>&_tag=<TAG>[&extra=...]

reachable from the home page or from any HTML/JS asset that the UI
serves. The spider is **strictly read-only**:

- HTTP GET only.
- Endpoints whose ``_tag`` looks mutating (add/del/set/restart/...) are
  recorded as "skipped" rather than being fetched, even with GET.
- A small per-request delay is enforced.

The output JSON (one document) is meant to be analyzed offline to
extend the CLI with new commands.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse, urlsplit

import requests

from .api import ZTEH388XAPI


# ---------------------------------------------------------------- regex bag

# Match strings like "_type=menuData&_tag=foo_bar.lua" or
# `_type=menuView&_tag=fooView` anywhere in HTML/JS/strings.
_RE_QUERY = re.compile(
    r"_type=(?P<type>[A-Za-z0-9_]+)&_tag=(?P<tag>[A-Za-z0-9_./-]+)"
    r"(?P<extra>(?:&[A-Za-z0-9_]+=[^\s\"'<>&]+)*)"
)

# Match ``href="..."``/``src="..."`` to follow local assets (HTML, JS).
_RE_ATTR_URL = re.compile(
    r"""(?:href|src)\s*=\s*(?P<q>['"])(?P<url>[^'"]+)(?P=q)""",
    re.IGNORECASE,
)

# Match the inline ``var menuTreeJSON = [ ... ];`` definition emitted by
# the home page on H388X firmwares. Captures the JSON array literal.
_RE_MENU_TREE = re.compile(
    r"var\s+menuTreeJSON\s*=\s*(\[.*?\])\s*;",
    re.DOTALL,
)

# Conservative deny-list: if a ``_tag`` matches this, we record the URL
# but do NOT GET it. Some routers run actions on GET as well as POST.
_MUTATING_TOKENS = (
    "add", "set", "del", "delete", "remove", "update", "edit",
    "save", "submit", "apply", "action",
    "restart", "reboot", "reset", "logout", "logoff",
    "upgrade", "upload", "download", "export", "import",
    "factory", "default", "clear", "wipe", "backup", "restore",
    "start", "stop", "enable", "disable", "kick", "block",
    "ping", "trace", "diag", "test",
)

# Asset extensions worth fetching to mine for endpoint references.
_ASSET_EXTS = (".html", ".htm", ".js", ".lua", ".css", ".json", ".xml")


# ------------------------------------------------------------------ models

@dataclass
class Endpoint:
    """A single discovered URL of shape ``/?_type=...&_tag=...``."""

    type: str                          # e.g. "menuData", "menuView", "loginData"
    tag: str                           # e.g. "devmgr_statusmgr_lua.lua"
    extras: Dict[str, str] = field(default_factory=dict)
    discovered_in: List[str] = field(default_factory=list)

    fetched: bool = False
    skipped_reason: Optional[str] = None
    status: Optional[int] = None
    content_type: Optional[str] = None
    bytes: Optional[int] = None

    # Classification of the parsed body. ``shape`` is one of:
    #   - "xml-instances": OBJ_FOO_ID with one or more <Instance>
    #   - "xml-empty":     OBJ_FOO_ID present but no <Instance> (empty list)
    #   - "xml-flat":      ajax_response_xml_root with direct fields
    #   - "json":          JSON payload (e.g. topo_lua.lua)
    #   - "session-timeout": <IF_ERRORSTR>SessionTimeout</IF_ERRORSTR>
    #   - "html":          HTML body (404 wrapper or template)
    #   - "empty":         zero bytes
    #   - None:            not parsed yet / not applicable
    shape: Optional[str] = None
    root_element: Optional[str] = None
    instance_count: Optional[int] = None
    field_names: List[str] = field(default_factory=list)
    sample: Optional[str] = None       # first ~600 chars of the response
    error: Optional[str] = None

    def url(self) -> str:
        qs = f"_type={self.type}&_tag={self.tag}"
        for k, v in self.extras.items():
            qs += f"&{k}={v}"
        return f"/?{qs}"

    def key(self) -> Tuple[str, str, Tuple[Tuple[str, str], ...]]:
        return (self.type, self.tag, tuple(sorted(self.extras.items())))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url(),
            "type": self.type,
            "tag": self.tag,
            "extras": self.extras,
            "discovered_in": self.discovered_in,
            "fetched": self.fetched,
            "skipped_reason": self.skipped_reason,
            "status": self.status,
            "content_type": self.content_type,
            "bytes": self.bytes,
            "shape": self.shape,
            "root_element": self.root_element,
            "instance_count": self.instance_count,
            "field_names": self.field_names,
            "sample": self.sample,
            "error": self.error,
        }


@dataclass
class Asset:
    """A static asset (HTML/JS/CSS) we fetched to mine for endpoints."""

    path: str
    status: int
    bytes: int
    content_type: str
    found_endpoints: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status,
            "bytes": self.bytes,
            "content_type": self.content_type,
            "found_endpoints": self.found_endpoints,
            "error": self.error,
        }


# ------------------------------------------------------------------ spider

# Seed views known to exist on this firmware (from the existing API and from
# tile-homepage data tags observed on /). Anything else is discovered
# organically by mining the HTML/JS responses.
_SEED_VIEWS: Tuple[str, ...] = (
    # Confirmed-working from h388x_cli.api:
    "dslWanStatus",
    "statusMgr",
    "rebootAndReset",
    "lanMgrIpv4",
    "localNetStatus",
    # Synthetic view that arms the dashboard tile endpoints
    # (``*_homepage_lua.lua``). Not exposed in menuTreeJSON.
    "homePage",
)

# Dashboard tile endpoints (``*_homepage_lua.lua``). They are not linked
# from the HTML nor the menuTreeJSON in some firmwares, but they are
# always there and yield rich data once armed via the ``homePage`` view.
# (tag, extras) pairs.
_SEED_HOMEPAGE_TILES: Tuple[Tuple[str, Dict[str, str]], ...] = (
    ("firewall_homepage_lua.lua", {}),
    ("usb_homepage_lua.lua", {}),
    ("voip_homepage_lua.lua", {}),
    ("accessdev_homepage_lua.lua", {"InstNum": "5"}),
    ("wlan_homepage_lua.lua", {"InstNum": "5"}),
)


class Spider:
    """
    BFS spider over the modem web UI.

    Usage:
        api = ZTEH388XAPI(...); api.login()
        spider = Spider(api, max_requests=300, delay=0.15)
        result = spider.run()    # {"endpoints": [...], "assets": [...], "stats": {...}}
    """

    def __init__(
        self,
        api: ZTEH388XAPI,
        max_requests: int = 400,
        delay: float = 0.15,
        sample_chars: int = 600,
        progress_cb=None,
    ):
        self.api = api
        self.max_requests = max_requests
        self.delay = delay
        self.sample_chars = sample_chars
        self.progress_cb = progress_cb

        self._endpoints: Dict[Tuple[str, str, Tuple[Tuple[str, str], ...]], Endpoint] = {}
        self._assets: Dict[str, Asset] = {}
        self._asset_queue: deque = deque()
        self._endpoint_queue: deque = deque()
        self._visited_assets: Set[str] = set()
        self._requests_made = 0
        self._errors = 0
        # menuData tag → menuView tag that owns it (from menuTreeJSON).
        # Used to "arm" the data endpoint by fetching its parent view first.
        self._data_parent_view: Dict[str, str] = {}

    # ---------------------------------------------------------- public

    def run(self) -> Dict[str, Any]:
        # Seed: home page (which carries menuTreeJSON) + every known view.
        # Use the same Menu3Location=0 the browser uses so that menuView →
        # menuData arming behaves like a real navigation.
        self._enqueue_asset("/", source="seed")
        for tag in _SEED_VIEWS:
            self._record_endpoint(
                "menuView", tag, {"Menu3Location": "0"}, source="seed"
            )
        for tag, extras in _SEED_HOMEPAGE_TILES:
            self._record_endpoint("menuData", tag, dict(extras), source="seed")

        # Single interleaved loop: drain assets (cheap, mine HTML/JS) before
        # endpoints, so per-page JS scoperti dopo una view vengono
        # processati subito. Endpoint processing keeps view→data pairing
        # via priority enqueue inside _fetch_endpoint.
        while self._requests_made < self.max_requests:
            if self._asset_queue:
                self._fetch_asset(self._asset_queue.popleft())
                continue
            if self._endpoint_queue:
                self._fetch_endpoint(self._endpoint_queue.popleft())
                continue
            break

        return self._build_result()

    # ---------------------------------------------------------- assets

    def _enqueue_asset(self, path: str, source: str) -> None:
        path = self._normalize_path(path)
        if not path or path in self._visited_assets:
            return
        # Only follow local "interesting" assets, plus the bare root.
        if path != "/" and not any(path.lower().endswith(ext) for ext in _ASSET_EXTS):
            return
        self._visited_assets.add(path)
        self._asset_queue.append(path)

    def _fetch_asset(self, path: str) -> None:
        url = f"{self.api.base_url}{path}"
        try:
            self._tick(f"asset      GET {path}")
            r = self.api.session.get(url, headers=self.api.NO_CACHE, timeout=8)
            self._requests_made += 1
            ctype = r.headers.get("Content-Type", "")
            text = r.text
            asset = Asset(
                path=path,
                status=r.status_code,
                bytes=len(text),
                content_type=ctype,
            )
            # Mine for endpoint URLs in any text-ish payload.
            n_found = 0
            for tp, tag, extras in self._extract_endpoints(text):
                self._record_endpoint(tp, tag, extras, source=path)
                n_found += 1
            # Mine the embedded menuTreeJSON for the real navigation tree.
            n_found += self._mine_menu_tree(text, source=path)
            asset.found_endpoints = n_found
            # Mine for further static assets to follow.
            for href in self._extract_asset_links(text):
                self._enqueue_asset(href, source=path)
            self._assets[path] = asset
        except requests.RequestException as e:
            self._errors += 1
            self._assets[path] = Asset(
                path=path, status=0, bytes=0, content_type="", error=str(e)
            )
        finally:
            time.sleep(self.delay)

    def _mine_menu_tree(self, text: str, source: str) -> int:
        """Find ``var menuTreeJSON = [...]`` and enqueue all real menuView/menuData."""
        m = _RE_MENU_TREE.search(text)
        if not m:
            return 0
        try:
            tree = json.loads(m.group(1))
        except json.JSONDecodeError:
            return 0
        added = 0

        def walk(nodes: List[Dict[str, Any]]) -> None:
            nonlocal added
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                node_id = node.get("id")
                view_tag: Optional[str] = None
                if isinstance(node_id, str) and node_id and node_id != "homePage":
                    view_tag = node_id
                    # Browser sends Menu3Location=0 by default for menuView GETs.
                    if self._record_endpoint(
                        "menuView", node_id, {"Menu3Location": "0"},
                        source=f"{source}#menuTreeJSON",
                    ):
                        added += 1
                for area in node.get("area", []) or []:
                    if not isinstance(area, dict):
                        continue
                    a = area.get("area")
                    if isinstance(a, str) and a.endswith(".lua"):
                        if view_tag and a not in self._data_parent_view:
                            self._data_parent_view[a] = view_tag
                        if self._record_endpoint(
                            "menuData", a, {},
                            source=f"{source}#menuTreeJSON",
                        ):
                            added += 1
                children = node.get("children")
                if isinstance(children, list):
                    walk(children)

        walk(tree)
        return added

    @staticmethod
    def _extract_asset_links(text: str) -> List[str]:
        out: List[str] = []
        for m in _RE_ATTR_URL.finditer(text):
            url = m.group("url").strip()
            if not url or url.startswith(("data:", "javascript:", "mailto:", "#",
                                          "http://", "https://", "//")):
                continue
            out.append(url)
        return out

    @staticmethod
    def _normalize_path(p: str) -> str:
        if not p:
            return ""
        # Drop query/fragment from asset URLs (we only want to mine static assets;
        # endpoints are handled separately via _extract_endpoints).
        s = urlsplit(p)
        if s.scheme or s.netloc:
            return ""
        path = s.path or "/"
        if not path.startswith("/"):
            path = "/" + path
        return path

    # ------------------------------------------------------- endpoints

    @staticmethod
    def _extract_endpoints(text: str) -> List[Tuple[str, str, Dict[str, str]]]:
        out: List[Tuple[str, str, Dict[str, str]]] = []
        for m in _RE_QUERY.finditer(text):
            tp = m.group("type")
            tag = m.group("tag")
            extras: Dict[str, str] = {}
            extra_str = m.group("extra") or ""
            for chunk in extra_str.split("&"):
                if "=" in chunk:
                    k, _, v = chunk.partition("=")
                    if k:
                        extras[k] = v
            out.append((tp, tag, extras))
        return out

    def _record_endpoint(
        self,
        tp: str,
        tag: str,
        extras: Dict[str, str],
        source: str,
        prioritize: bool = False,
    ) -> Optional["Endpoint"]:
        ep = Endpoint(type=tp, tag=tag, extras=extras)
        key = ep.key()
        if key in self._endpoints:
            existing = self._endpoints[key]
            if source not in existing.discovered_in:
                existing.discovered_in.append(source)
            return None
        ep.discovered_in.append(source)
        self._endpoints[key] = ep

        # Don't probe login/logoff endpoints — could break our session.
        if tp == "loginData" or "logout" in tag.lower() or "logoff" in tag.lower():
            ep.skipped_reason = "auth-related"
            return ep

        # Don't probe data/hidden endpoints whose tag screams mutation.
        # menuView is just an HTML template render and is safe to GET; the
        # *_entry / *Mgr URLs that perform actions live under menuData /
        # loginData / hiddenData with explicit POST payloads.
        if tp != "menuView" and self._looks_mutating(tag):
            ep.skipped_reason = "mutating-name"
            return ep

        if prioritize:
            self._endpoint_queue.appendleft(ep)
        else:
            self._endpoint_queue.append(ep)
        return ep

    @staticmethod
    def _looks_mutating(tag: str) -> bool:
        low = tag.lower()
        return any(tok in low for tok in _MUTATING_TOKENS)

    def _fetch_endpoint(self, ep: Endpoint) -> None:
        # If this is a menuData with a known parent view (from menuTreeJSON),
        # arm the session by fetching the parent view first — that is exactly
        # what the browser does on navigation.
        if ep.type == "menuData":
            parent = self._data_parent_view.get(ep.tag)
            if parent and self._requests_made < self.max_requests:
                self._arm_view(parent, source=f"arm-for:{ep.url()}")
            elif (
                ep.tag.endswith("_homepage_lua.lua")
                and self._requests_made < self.max_requests
            ):
                # Dashboard tiles (``*_homepage_lua.lua``) are bound to the
                # synthetic ``homePage`` menuView (the only ``_tag`` not
                # exposed in ``menuTreeJSON``). Hitting any other view in
                # between leaves them serving ``SessionTimeout``, so arm
                # them by re-rendering the dashboard view right before.
                self._arm_view("homePage", source=f"arm-for:{ep.url()}")

        text = self._do_fetch_endpoint(ep)
        if text is None:
            return

        # Mine the response for further endpoints / assets.
        is_view = ep.type == "menuView"
        view_children: List[Endpoint] = []
        for tp, tag, extras in self._extract_endpoints(text):
            child = self._record_endpoint(tp, tag, extras, source=ep.url())
            if (
                is_view
                and child is not None
                and child.skipped_reason is None
                and not child.fetched
                and child.type == "menuData"
            ):
                view_children.append(child)
        if is_view:
            for href in self._extract_asset_links(text):
                self._enqueue_asset(href, source=ep.url())
            # Pairing view→data: il modem popola i menuData solo se la view
            # corrispondente è stata richiesta IMMEDIATAMENTE prima. Eseguo
            # qui i child data, senza interruzioni dalla coda principale.
            for child in view_children:
                if self._requests_made >= self.max_requests:
                    break
                # Remove from queue to avoid double-fetch.
                try:
                    self._endpoint_queue.remove(child)
                except ValueError:
                    pass
                ctext = self._do_fetch_endpoint(child)
                if ctext is not None:
                    # mine for further endpoints (lower priority)
                    for tp, tag, extras in self._extract_endpoints(ctext):
                        self._record_endpoint(tp, tag, extras, source=child.url())

    def _arm_view(self, view_tag: str, source: str) -> None:
        """Fetch ``menuView`` ``view_tag`` to arm the modem for the next data
        call. If we already fetched it as part of the spider, re-issue the GET
        anyway: the modem keeps server-side state per request, not per session,
        and we may have done many other requests in between."""
        view = Endpoint(
            type="menuView",
            tag=view_tag,
            extras={"Menu3Location": "0"},
            discovered_in=[source],
        )
        # Don't pollute the report with a second copy: if we already have this
        # view recorded, update its discovered_in only and re-fetch in place.
        existing = self._endpoints.get(view.key())
        if existing is not None:
            view = existing
            if source not in view.discovered_in:
                view.discovered_in.append(source)
        else:
            self._endpoints[view.key()] = view
        self._do_fetch_endpoint(view)

    def _do_fetch_endpoint(self, ep: Endpoint) -> Optional[str]:
        """Single GET for an endpoint; updates ``ep`` in place. Returns body."""
        url = f"{self.api.base_url}{ep.url()}"
        try:
            self._tick(f"{ep.type:10s} GET {ep.url()}")
            r = self.api.session.get(url, headers=self.api.NO_CACHE, timeout=8)
            self._requests_made += 1
            ep.fetched = True
            ep.status = r.status_code
            ep.content_type = r.headers.get("Content-Type", "")
            text = r.text
            ep.bytes = len(text)
            ep.sample = text[: self.sample_chars]
            self._classify_body(ep, text)
            return text
        except requests.RequestException as e:
            ep.error = str(e)
            self._errors += 1
            return None
        finally:
            time.sleep(self.delay)

    @staticmethod
    def _classify_body(ep: Endpoint, text: str) -> None:
        if not text:
            ep.shape = "empty"
            return
        stripped = text.lstrip()
        # JSON?
        if stripped.startswith(("{", "[")):
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                obj = None
            if obj is not None:
                ep.shape = "json"
                ep.field_names = sorted(obj.keys()) if isinstance(obj, dict) else []
                return
        # HTML?
        low = stripped[:200].lower()
        if "<html" in low or "<!doctype html" in low:
            ep.shape = "html"
            return
        # XML?
        try:
            tree = ET.fromstring(text)
        except ET.ParseError:
            return

        # SessionTimeout sentinel: <ajax_response_xml_root> with
        # <IF_ERRORSTR>SessionTimeout</IF_ERRORSTR>.
        err = tree.findtext("IF_ERRORSTR")
        if err and err.strip() == "SessionTimeout":
            ep.shape = "session-timeout"
            return

        # Shape A: OBJ_FOO_ID with one or more <Instance>.
        for candidate in tree.iter():
            instances = candidate.findall("Instance")
            if instances:
                ep.shape = "xml-instances"
                ep.root_element = candidate.tag
                ep.instance_count = len(instances)
                names: List[str] = []
                for n in instances[0].findall("ParaName"):
                    raw = (n.text or "").strip()
                    bare = raw.rsplit(".", 1)[-1] if "." in raw else raw
                    if bare and bare not in names:
                        names.append(bare)
                ep.field_names = names
                return

        # Shape B: OBJ_FOO_ID present but empty (no <Instance>) — empty list.
        # Heuristic: any direct child whose tag starts with "OBJ_" and has no
        # ParaName children itself, treated as the root.
        for child in list(tree):
            if child.tag.startswith("OBJ_") or child.tag.startswith("ID_"):
                ep.shape = "xml-empty"
                ep.root_element = child.tag
                ep.instance_count = 0
                return

        # Shape C: flat ajax_response_xml_root with direct fields beyond
        # IF_ERROR* markers (e.g. wan_3g_status_lua.lua).
        ignore = {"IF_ERRORSTR", "IF_ERRORID", "IF_ERRORPARAM", "IF_ERRORTYPE"}
        flat_fields: List[str] = []
        for child in list(tree):
            if child.tag not in ignore and not list(child):
                flat_fields.append(child.tag)
        if flat_fields:
            ep.shape = "xml-flat"
            ep.root_element = tree.tag
            ep.instance_count = 1
            ep.field_names = flat_fields
            return

    # ----------------------------------------------------------- misc

    def _tick(self, msg: str) -> None:
        if self.progress_cb:
            try:
                self.progress_cb(msg, self._requests_made, self.max_requests)
            except Exception:
                pass

    def _build_result(self) -> Dict[str, Any]:
        endpoints = sorted(
            (ep.to_dict() for ep in self._endpoints.values()),
            key=lambda d: (d["type"], d["tag"], d["url"]),
        )
        kind_counts: Counter = Counter(d["type"] for d in endpoints)
        fetched = sum(1 for d in endpoints if d["fetched"])
        with_data = sum(
            1 for d in endpoints
            if d["fetched"] and d["shape"] in ("xml-instances", "xml-flat", "json")
        )
        shape_counts = Counter(
            d["shape"] for d in endpoints if d["fetched"] and d["shape"]
        )
        skipped = Counter(
            d["skipped_reason"] for d in endpoints if d["skipped_reason"]
        )
        assets = sorted(
            (a.to_dict() for a in self._assets.values()),
            key=lambda d: d["path"],
        )
        return {
            "endpoints": endpoints,
            "assets": assets,
            "stats": {
                "requests_made": self._requests_made,
                "errors": self._errors,
                "endpoint_count": len(endpoints),
                "endpoint_fetched": fetched,
                "endpoints_with_data": with_data,
                "by_type": dict(kind_counts),
                "by_shape": dict(shape_counts),
                "skipped": dict(skipped),
                "asset_count": len(assets),
            },
        }
