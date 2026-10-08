import pytest
from fastapi import HTTPException, status

from src.api.dependencies import verify_api_key
from src.config import settings


class TestApiDependencies:
    def test_verify_api_key_accepts_correct_key(self):
        try:
            assert verify_api_key(settings.ingestion_api_key) is None
        except HTTPException:
            pytest.fail("verify_api_key raised HTTPException unexpectedly on correct key")
    def test_verify_api_key_rejects_incorrect_key(self):
        with pytest.raises(HTTPException) as exc_info:
            assert verify_api_key("random string")
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Invalid API key"