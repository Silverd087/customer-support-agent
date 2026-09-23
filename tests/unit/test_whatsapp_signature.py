import hashlib
import hmac
from unittest.mock import Mock

import pytest
from requests.exceptions import ConnectionError, HTTPError

from adapters.utils import is_transient_post_error, verify_meta_signature


class TestVerifySignature:

    def test_verify_meta_signature_valid(self):
        app_secret = "test_meta_app_secret_12345"
        raw_body= b"test body"

        expected_hex = hmac.new(
            key=app_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        signature_header = f"sha256={expected_hex}"

        assert verify_meta_signature(raw_body,signature_header,app_secret) is True

    def test_verify_meta_signature_invalid(self):
        app_secret = "test_meta_app_secret_12345"
        raw_body= b"test body"


        signature_header = "sha256=invalid_hex_string12345"

        assert verify_meta_signature(raw_body,signature_header,app_secret) is False

    def test_verify_meta_signature_missing_signature(self):
        app_secret = "test_meta_app_secret_12345"
        raw_body= b"test body"
        signature_header = None

        assert verify_meta_signature(raw_body,signature_header,app_secret) is False

    def test_verify_meta_signature_malformed_format(self):
        app_secret = "test_meta_app_secret_12345"
        raw_body= b"test body"


        signature_header = "sha2=invalid_hex_string12345"

        assert verify_meta_signature(raw_body,signature_header,app_secret) is False

class TestWhatsappTransientError:
    def test_is_transient_post_error_connection_error(self):
        exc = ConnectionError()
        assert is_transient_post_error(exc) is True

    @pytest.mark.parametrize(
    "status_code, expected",
    [
        (408,True),
        (429,True),
        (502,True),
        (503,True),
        (504,True),
    ],
)
    def test_is_transient_post_error_transient_http_status(self,status_code,expected):
        exc = HTTPError(response=Mock(status_code=status_code))
        assert is_transient_post_error(exc) is expected

    @pytest.mark.parametrize(
    "status_code, expected",
    [
        (400, False),
        (401, False),
        (403, False),
        (404, False),
        (500, False),
    ],
)
    def test_is_transient_post_error_non_transient_http_status(self,status_code,expected):
        exc = HTTPError(response=Mock(status_code=status_code))
        assert is_transient_post_error(exc) is expected
