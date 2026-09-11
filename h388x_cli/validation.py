"""Validation helpers for mutating H388X operations.

These models intentionally validate only constraints that are protocol-level,
well established, or explicitly observed in the WebUI. Firmware-specific
constraints that are not known with confidence remain server-validated.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .devices import is_valid_mac, norm_mac


class WriteSpec(BaseModel):
    """Base model for modem write payload validation."""

    model_config = ConfigDict(str_strip_whitespace=True)


class DhcpReservationSpec(WriteSpec):
    mac: str
    ip_address: str
    name: str

    @field_validator("mac")
    @classmethod
    def validate_mac(cls, value: str) -> str:
        value = norm_mac(value)
        if not is_valid_mac(value):
            raise ValueError("must be a valid 48-bit MAC address")
        return value

    @field_validator("ip_address")
    @classmethod
    def validate_ipv4(cls, value: str) -> str:
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("must be a valid IPv4 address") from exc
        if parsed.version != 4:
            raise ValueError("must be an IPv4 address")
        return str(parsed)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value:
            raise ValueError("must not be empty")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("must not contain control characters")
        return value


class PortForwardSpec(WriteSpec):
    description: str
    protocol: str
    external_port: int
    external_port_end: int
    internal_client: str
    internal_port: int
    remote_host: str = "0.0.0.0"
    remote_host_end: str = "0.0.0.0"

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        value = value.upper()
        if value not in {"TCP", "UDP", "BOTH"}:
            raise ValueError("must be TCP/UDP/BOTH")
        return value

    @field_validator("external_port", "external_port_end", "internal_port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("must be in range 1..65535")
        return value

    @field_validator("internal_client")
    @classmethod
    def validate_internal_client(cls, value: str) -> str:
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("must be a valid IPv4 address") from exc
        if parsed.version != 4:
            raise ValueError("must be an IPv4 address")
        return str(parsed)

    @field_validator("remote_host", "remote_host_end")
    @classmethod
    def validate_remote_host(cls, value: str) -> str:
        # The WebUI uses 0.0.0.0 for "any"; tolerate an empty value read back
        # from firmware, but validate any concrete address supplied by users.
        if not value:
            return value
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            raise ValueError("must be a valid IPv4 address or empty") from exc
        if parsed.version != 4:
            raise ValueError("must be an IPv4 address or empty")
        return str(parsed)

    @model_validator(mode="after")
    def validate_range(self) -> "PortForwardSpec":
        if self.external_port_end < self.external_port:
            raise ValueError("external_port_end must be >= external_port")
        return self


class UrlFilterSpec(WriteSpec):
    name: str
    url: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not 1 <= len(value) <= 32:
            raise ValueError("must contain 1..32 characters")
        if not value.isascii():
            raise ValueError("must contain ASCII characters only")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("must not contain control characters")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not 1 <= len(value) <= 128:
            raise ValueError("must contain 1..128 characters")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("must not contain control characters")
        return value


class IpFilterSpec(WriteSpec):
    name: str
    protocol: str
    target: str = "allow"
    filter_index: int = 1
    ip_version: str = "4"
    source_ip: str = ""
    dest_ip: str = ""
    min_src_port: str = ""
    max_src_port: str = ""
    min_dst_port: str = ""
    max_dst_port: str = ""
    dscp: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not 1 <= len(value) <= 32:
            raise ValueError("must contain 1..32 characters")
        if not value.isascii():
            raise ValueError("must contain ASCII characters only")
        if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
            raise ValueError("must not contain control characters")
        return value

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, value: str) -> str:
        upper = value.upper()
        if upper in {"ICMP", "TCP", "UDP"}:
            return upper
        if value.isdigit() and 1 <= int(value) <= 255:
            return str(int(value))
        raise ValueError("must be ICMP/TCP/UDP or a protocol number in 1..255")

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        lower = value.lower()
        aliases = {"allow": "allow", "permit": "allow", "deny": "deny", "drop": "deny"}
        if lower not in aliases:
            raise ValueError("must be allow/deny")
        return aliases[lower]

    @field_validator("filter_index")
    @classmethod
    def validate_filter_index(cls, value: int) -> int:
        if not 1 <= value <= 20:
            raise ValueError("must be in range 1..20")
        return value

    @field_validator("ip_version")
    @classmethod
    def validate_ip_version(cls, value: str) -> str:
        if value not in {"4", "6", "-1"}:
            raise ValueError("must be 4, 6, or -1 (any)")
        return value

    @field_validator("source_ip", "dest_ip")
    @classmethod
    def validate_optional_ip(cls, value: str) -> str:
        if not value:
            return value
        try:
            return str(ipaddress.ip_address(value))
        except ValueError as exc:
            raise ValueError("must be a valid IP address or empty") from exc

    @field_validator("min_src_port", "max_src_port", "min_dst_port", "max_dst_port")
    @classmethod
    def validate_optional_port(cls, value: str) -> str:
        if value == "":
            return value
        if not value.isdigit() or not 1 <= int(value) <= 65535:
            raise ValueError("must be empty or a port in range 1..65535")
        return str(int(value))

    @field_validator("dscp")
    @classmethod
    def validate_dscp(cls, value: str) -> str:
        if value == "":
            return value
        if not value.isdigit() or not 0 <= int(value) <= 63:
            raise ValueError("must be empty or in range 0..63")
        return str(int(value))

    @model_validator(mode="after")
    def validate_port_ranges(self) -> "IpFilterSpec":
        for low_name, high_name in (
            ("min_src_port", "max_src_port"),
            ("min_dst_port", "max_dst_port"),
        ):
            low = getattr(self, low_name)
            high = getattr(self, high_name)
            if low and high and int(high) < int(low):
                raise ValueError(f"{high_name} must be >= {low_name}")
        return self


def validation_error_message(exc: Exception) -> str:
    """Return a compact user-facing message for a Pydantic validation error."""
    errors = getattr(exc, "errors", None)
    if callable(errors):
        parts: list[str] = []
        for error in errors():
            location = ".".join(str(part) for part in error.get("loc", ())) or "input"
            message = error.get("msg", "invalid value")
            if message.startswith("Value error, "):
                message = message[len("Value error, "):]
            parts.append(f"{location}: {message}")
        if parts:
            return "; ".join(parts)
    return str(exc)


def model_data(model: BaseModel) -> dict[str, Any]:
    """Small compatibility helper used when building modem payloads."""
    return model.model_dump()
