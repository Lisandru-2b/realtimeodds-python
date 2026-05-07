"""Gateway protocol — wire message parsing and version negotiation.

Mirrors the contract documented in `realtimeodds-spec/schemas/v1/wire/` and
the SDK-side checks performed by `@lisandru-2b/sb-gateway-client`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# The protocol version this SDK speaks. Must match the major (and preferably the
# minor) of the version the gateway advertises in `hello`.
SDK_PROTOCOL_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class _Compatible:
    kind: Literal["compatible"] = "compatible"


@dataclass(frozen=True, slots=True)
class _Warning:
    reason: str
    kind: Literal["warning"] = "warning"


@dataclass(frozen=True, slots=True)
class _Incompatible:
    reason: str
    kind: Literal["incompatible"] = "incompatible"


VersionCheckResult = _Compatible | _Warning | _Incompatible


_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")


def _parse_version(v: str) -> tuple[int, int] | None:
    m = _VERSION_RE.match(v)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def check_protocol_compatibility(
    server_version: str, sdk_version: str = SDK_PROTOCOL_VERSION
) -> VersionCheckResult:
    """Compare server and SDK protocol versions per PROTOCOL.md.

    - Different major  → incompatible (refuse connection)
    - Same major, server minor > SDK minor → warning (connect but flag)
    - Same major, server minor ≤ SDK minor → compatible
    """
    sdk = _parse_version(sdk_version)
    if sdk is None:
        raise ValueError(
            f"Invalid SDK protocol version {sdk_version!r} (must be <major>.<minor>)"
        )
    server = _parse_version(server_version)
    if server is None:
        return _Incompatible(reason=f"Server sent invalid protocol version {server_version!r}")
    if server[0] != sdk[0]:
        return _Incompatible(
            reason=(
                f"Server protocol {server_version} has a different major than "
                f"SDK {sdk_version}"
            )
        )
    if server[1] > sdk[1]:
        return _Warning(
            reason=(
                f"Server protocol {server_version} is newer than SDK {sdk_version}; "
                "consider upgrading the realtimeodds package to use new features"
            )
        )
    return _Compatible()


def is_auth_close_code(code: int) -> bool:
    """4001 / 4002 / 4003 are fatal auth close codes per the spec."""
    return code in (4001, 4002, 4003)


def auth_close_message(code: int, reason: str = "") -> str:
    meaning = {
        4001: "missing apiKey",
        4002: "invalid apiKey",
        4003: "quota or rate-limit exceeded",
    }.get(code, f"auth failed ({code})")
    if not reason or reason.lower() == meaning.lower():
        return meaning
    return f"{meaning}: {reason}"
