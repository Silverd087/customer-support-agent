from fastapi import APIRouter,Query,HTTPException,Request,status
from fastapi.responses import PlainTextResponse
from config import settings
from agent import handle_incoming
import requests
import hashlib
import hmac
import json
from logger import logger

router = APIRouter()

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
async def receive_message(request: Request):
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
        idempotency_key = last_message["id"]
        result = handle_incoming(last_message,thread_id=phone_number,channel="whatsapp")



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
            response = requests.post(url, headers=headers, json=post_payload)
            logger.info("whatsapp_reply_sent", phone_number=phone_number, status_code=response.status_code)
        except Exception as e:
            logger.error("whatsapp_send_failed", phone_number=phone_number, error=str(e))

    except (IndexError, KeyError) as e:
        logger.error("whatsapp_payload_parse_failed", error=str(e))

    return {"status": "success"}        
