from unittest.mock import Mock

import pytest
from websockets.exceptions import InvalidHandshake, InvalidStatus, WebSocketException

from adapters.utils import is_transient_websocket_error


class TestVoiceTransientErrors:
    def test_transient_os_error(self):
        exc = OSError()
        assert is_transient_websocket_error(exc) is True

    def test_transient_connection_refused_error(self):
        exc = ConnectionRefusedError()
        assert is_transient_websocket_error(exc) is True
    def test_transient_connection_reset_error(self):
        exc = ConnectionResetError()
        assert is_transient_websocket_error(exc) is True

    def test_transient_timeout_error(self):
        exc = TimeoutError()
        assert is_transient_websocket_error(exc) is True

    def test_transient_invalid_handshake(self):
        exc = InvalidHandshake()
        assert is_transient_websocket_error(exc) is True

    @pytest.mark.parametrize(
    "status_code, expected",
    [
        (408, True),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
    ],
)
    def test_transient_status_code(self,status_code,expected):
        exc = InvalidStatus(response=Mock(status_code=status_code))
        assert is_transient_websocket_error(exc) is expected

    @pytest.mark.parametrize(
    "status_code, expected",
    [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
    ],
)
    def test_non_transient_status_code(self,status_code,expected):
        exc = InvalidStatus(response=Mock(status_code=status_code))
        assert is_transient_websocket_error(exc) is expected


    @pytest.mark.parametrize(
    "name, expected",
    [
        ("Timeout", True),
        ("Reset", True),
        ("Aborted", True),
    ],
)
    def test_transient_named_exception(self,name,expected):
        exc = type(name, (WebSocketException,), {})()
        assert is_transient_websocket_error(exc) is expected

    @pytest.mark.parametrize(
    "name, expected",
    [
        ("some_random_name_1", False),
        ("some_random_name_2", False),
        ("some_random_name_3", False),
    ],
)
    def test_non_transient_exception(self,name,expected):
        exc = type(name, (WebSocketException,), {})()
        assert is_transient_websocket_error(exc) is expected