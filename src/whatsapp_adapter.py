import hashlib
import hmac
import json

import requests
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from requests.exceptions import ConnectionError, Timeout
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from cache import redis_cache
from config import settings
from logger import logger
from orchestrator import handle_incoming

router = APIRouter()

TRANSIENT_STATUS_CODES = {408, 429, 502, 503, 504}
EXPIRATION_TIME = 604800
def is_transient_post_error(exc: BaseException):
    if isinstance(exc,requests.exceptions.HTTPError):
        return exc.response is not None and exc.response.status_code in TRANSIENT_STATUS_CODES
    return isinstance(exc,(ConnectionError,Timeout))


@retry(
    retry=retry_if_exception(is_transient_post_error),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=1),
    stop=stop_after_attempt(4),
    reraise=True,
)
def call_post_request_with_retry(url,headers,post_payload):
    response = requests.post(url, headers=headers, json=post_payload)
    response.raise_for_status()
    return response


def verify_meta_signature(raw_body:bytes,signature:str | None,app_secret:str):
    if not signature:
        return False

    elements = signature.split("sha256=")
    if len(elements) != 2:
        return False

    expected_signature = elements[1]

    mac = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256
    )
    generated_signature = mac.hexdigest()

    return hmac.compare_digest(generated_signature,expected_signature)

async def agent_answer(last_message,phone_number,phone_number_id,idempotency_key):
    try:
        result = await handle_incoming(last_message,thread_id=phone_number,channel="whatsapp")
        url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"

        headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"{idempotency_key}"
            }

        post_payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone_number,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": result
            }
        }
        try:
            response = call_post_request_with_retry(url,headers,post_payload)
            logger.info("whatsapp_reply_sent", phone_number=phone_number, status_code=response.status_code)
        except Exception as e:
            logger.error("whatsapp_send_failed", phone_number=phone_number, error=str(e))
    except Exception as e:
        logger.error("whatsapp_background_processing_failed", phone_number=phone_number, message_id=idempotency_key, error=str(e))

@router.get("/webhook")
async def verify_webhook(
    hub_mode:str = Query(None,alias="hub.mode"),
    hub_challenge:str = Query(None,alias="hub.challenge"),
    hub_verify:str = Query(None,alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify == settings.verify_token:
        return PlainTextResponse(content=hub_challenge,status_code=200)
    
    raise HTTPException(status_code=403,detail="Verification token mismatch")


@router.post("/webhook")
async def receive_message(request: Request,background_task:BackgroundTasks):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    if not verify_meta_signature(raw_body, signature, settings.app_secret):
        logger.warning("whatsapp_invalid_signature")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid request signature"
        )
    payload = json.loads(raw_body.decode("utf-8"))
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value["messages"]
        last_message = messages[-1]["text"]["body"]
        phone_number_id = value["metadata"]["phone_number_id"]
        phone_number = messages[-1]["from"]
        logger.info("whatsapp_message_received", phone_number=phone_number, message_id=messages[-1]["id"])
        idempotency_key = messages[-1]["id"]
        was_set = True
        try:
            was_set = bool(redis_cache.set(idempotency_key,1,nx=True,ex=EXPIRATION_TIME))
        except Exception as e:
            logger.error("whatsapp_dedup_check_failed", phone_number=phone_number, message_id=idempotency_key, error=str(e))
        if was_set:
            background_task.add_task(agent_answer,last_message=last_message,phone_number=phone_number,phone_number_id=phone_number_id,idempotency_key=idempotency_key)
        else:
            logger.info("whatsapp_duplicate_delivery_skipped", phone_number=phone_number, message_id=idempotency_key)
        return {"status": "success"}
    except (IndexError, KeyError) as e:
        logger.error("whatsapp_payload_parse_failed", error=str(e))

