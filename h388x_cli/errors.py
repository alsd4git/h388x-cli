"""Public error types raised by h388x-cli read operations."""

from __future__ import annotations

import re


def safe_modem_error(body: str) -> str:
    """Expose only the numeric modem error ID, never response contents."""
    match = re.search(r"<IF_ERRORID>\s*(-?\d+)\s*</IF_ERRORID>", str(body))
    if match:
        return f"Modem rejected the operation (IF_ERRORID={match.group(1)})."
    return "Modem rejected the operation."


class H388XError(RuntimeError):
    """Base class for operational errors that callers can handle explicitly."""

    code = "h388x_error"
    exit_code = 1


class TransportError(H388XError):
    """The modem could not be reached or the HTTP exchange failed locally."""

    code = "transport_error"


class AuthenticationError(H388XError):
    """Authentication could not be established."""

    code = "authentication_error"


class SessionExpiredError(AuthenticationError):
    """The authenticated session expired and could not be recovered."""

    code = "session_expired"


class ProtocolError(H388XError):
    """The modem returned an HTTP/protocol response that cannot be accepted."""

    code = "protocol_error"


class ParseError(ProtocolError):
    """A successful response could not be parsed according to the H388X protocol."""

    code = "parse_error"
