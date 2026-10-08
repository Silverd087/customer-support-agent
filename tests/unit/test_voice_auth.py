from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Request, status

from src.adapters.voice import verify_twilio_signature


class TestVoiceAuth:
    @pytest.mark.asyncio
    async def test_verify_twilio_signature_raises_on_invalid(self,mocker):
        mock_validator = Mock()
        mock_validator.validate.return_value = False

        mocker.patch("src.adapters.voice.validator",mock_validator)
        scope = {
            "type": "http",
            "method": "POST",
            "headers": [(b"x-twilio-signature", b"test-signature")],
        }
        async def receive():
            return {
                "type": "http.request",
                "body": b"CallSid=CA12345&From=%2B1234567890",
                "more_body": False,
            }

        request = Request(scope, receive)
        with pytest.raises(HTTPException) as exc_info:
            await verify_twilio_signature(request)
        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert exc_info.value.detail == "Invalid Twilio signature"
    
    
    @pytest.mark.asyncio
    async def test_verify_twilio_signature_stores_call_sid_on_success(self,mocker):
        mock_validator = Mock()
        mock_validator.validate.return_value = True
        mocker.patch("src.adapters.voice.validator",mock_validator)
        body_data = b"CallSid=CA123456789&From=%2B1234567890"

        scope = {
        "type": "http",
        "method": "POST",
        "headers": [
            (b"content-type", b"application/x-www-form-urlencoded"),
            (b"x-twilio-signature", b"test-signature"),
        ],
    }

        async def receive():
            return {
                "type": "http.request",
                "body": body_data,
                "more_body": False,
            }
        
        request = Request(scope, receive)
        mock_redis = mocker.patch("src.adapters.voice.redis_cache")
        await verify_twilio_signature(request)
        mock_redis.set.assert_called_once_with("verified call:CA123456789",1,ex=60)

