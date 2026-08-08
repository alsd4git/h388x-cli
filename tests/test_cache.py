"""Tests for the on-disk session cache (``_save_cache`` / ``_load_cache``).

The cache lets subsequent CLI invocations against the same modem skip
the (slow) login handshake by reusing the SID cookie + session token.
These tests exercise the round-trip locally; the live login flow is
stubbed out.
"""

import json

import pytest

from h388x_cli.api import ZTEH388XAPI, _default_cache_dir


HOST = "http://modem.test"


def _new_api(tmp_path, host=HOST, user="admin", enabled=True):
    return ZTEH388XAPI(
        host, user, "password",
        cache_enabled=enabled, cache_dir=tmp_path,
    )


# --- path layout -----------------------------------------------------------

def test_default_cache_dir_uses_xdg_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    p = _default_cache_dir()
    assert p == tmp_path / "h388x-cli"


def test_cache_path_is_per_host_and_user(tmp_path):
    a = _new_api(tmp_path, host="http://a.test", user="admin")
    b = _new_api(tmp_path, host="http://b.test", user="admin")
    c = _new_api(tmp_path, host="http://a.test", user="other")
    paths = {a._cache_path(), b._cache_path(), c._cache_path()}
    assert len(paths) == 3, "different (host, user) pairs must map to distinct files"


# --- save / load roundtrip -------------------------------------------------

def test_save_then_load_roundtrip(tmp_path):
    a = _new_api(tmp_path)
    a.session_token = "TOK-XYZ"
    a.session.cookies.set("SID", "abc123")
    a._save_cache()

    # A fresh instance should hydrate from the file written above.
    b = _new_api(tmp_path)
    assert b.session_token == "TOK-XYZ"
    assert b.session.cookies.get("SID") == "abc123"


def test_save_requires_sid_cookie(tmp_path):
    """Without a SID cookie the cache write is a no-op (nothing useful to keep)."""
    a = _new_api(tmp_path)
    a.session_token = "TOK"
    a._save_cache()
    assert not a._cache_path().exists()


def test_cached_session_handles_duplicate_sid_scopes(tmp_path):
    api = _new_api(tmp_path)
    api.session_token = "TOK"
    api.session.cookies.set("SID", "one", domain="modem.test", path="/")
    api.session.cookies.set("SID", "two", domain="modem.test", path="/admin")

    assert api.has_cached_session is True


def test_save_no_op_when_cache_disabled(tmp_path):
    a = _new_api(tmp_path, enabled=False)
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    assert not a._cache_path().exists()


def test_load_missing_file_does_nothing(tmp_path):
    a = _new_api(tmp_path)
    # Fresh tmp dir → no cache file exists yet.
    assert a.session_token is None
    assert a.session.cookies.get("SID") is None


def test_load_corrupted_cache_is_swallowed(tmp_path):
    a = _new_api(tmp_path)
    a._cache_path().parent.mkdir(parents=True, exist_ok=True)
    a._cache_path().write_text("not json at all {{{")
    # A second instance must come up cleanly even if the file is garbage.
    b = _new_api(tmp_path)
    assert b.session_token is None


def test_clear_cache_removes_file(tmp_path):
    a = _new_api(tmp_path)
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    assert a._cache_path().exists()

    a._clear_cache()
    assert not a._cache_path().exists()


# --- file permissions ------------------------------------------------------

@pytest.mark.skipif(
    not hasattr(__import__("os"), "stat"),
    reason="os.stat() not available",
)
def test_save_writes_0600_permissions(tmp_path):
    import os
    import stat

    a = _new_api(tmp_path)
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    mode = stat.S_IMODE(os.stat(a._cache_path()).st_mode)
    assert mode == 0o600


# --- close vs logout semantics --------------------------------------------

def test_close_preserves_cache(tmp_path):
    a = _new_api(tmp_path)
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    a.close()
    assert a._cache_path().exists(), "close() must keep the cache for resume"


def test_logout_without_token_still_clears_cache(tmp_path):
    """``logout()`` must wipe the cache file even if no live token is set
    (e.g. the user is just trying to free a stale session)."""
    a = _new_api(tmp_path)
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    assert a._cache_path().exists()

    # Drop the token to simulate a stale-but-cached state.
    a.session_token = None
    a.logout()
    assert not a._cache_path().exists()


# --- cache payload shape ---------------------------------------------------

def test_cache_payload_contains_host_user_and_token(tmp_path):
    a = _new_api(tmp_path, host="http://m.example.com", user="admin")
    a.session_token = "TOK"
    a.session.cookies.set("SID", "abc")
    a._save_cache()
    data = json.loads(a._cache_path().read_text())
    assert data["host"] == "http://m.example.com"
    assert data["user"] == "admin"
    assert data["session_token"] == "TOK"
    assert data["cookies"]["SID"] == "abc"
