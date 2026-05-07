"""Protocol version compatibility check."""

from __future__ import annotations

import pytest

from realtimeodds._gateway.protocol import (
    SDK_PROTOCOL_VERSION,
    auth_close_message,
    check_protocol_compatibility,
    is_auth_close_code,
)


def test_compatible_same_version() -> None:
    assert check_protocol_compatibility("1.0", "1.0").kind == "compatible"


def test_warning_when_server_minor_newer() -> None:
    result = check_protocol_compatibility("1.5", "1.0")
    assert result.kind == "warning"


def test_compatible_when_sdk_minor_newer() -> None:
    assert check_protocol_compatibility("1.0", "1.5").kind == "compatible"


def test_incompatible_when_major_differs() -> None:
    assert check_protocol_compatibility("2.0", "1.0").kind == "incompatible"


def test_incompatible_when_server_version_invalid() -> None:
    assert check_protocol_compatibility("not-a-version", "1.0").kind == "incompatible"


def test_invalid_sdk_version_raises() -> None:
    with pytest.raises(ValueError):
        check_protocol_compatibility("1.0", "bad")


def test_default_sdk_version_is_used() -> None:
    assert check_protocol_compatibility(SDK_PROTOCOL_VERSION).kind == "compatible"


def test_auth_close_code_detection() -> None:
    assert is_auth_close_code(4001)
    assert is_auth_close_code(4002)
    assert is_auth_close_code(4003)
    assert not is_auth_close_code(1006)


def test_auth_close_message_includes_meaning() -> None:
    assert "missing apiKey" in auth_close_message(4001, "")
    assert "invalid apiKey" in auth_close_message(4002, "")
    assert "quota" in auth_close_message(4003, "")
