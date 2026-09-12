from fastapi import APIRouter,WebSocket,Response,WebSocketDisconnect
from twilio.twiml.voice_response import Connect, VoiceResponse
import json
import base64
from agent import handle_incoming
import asyncio
import websockets
from config import settings
from elevenlabs import AsyncElevenLabs,VoiceSettings
from logger import logger
from tenacity import retry,retry_if_exception,wait_exponential_jitter,stop_after_attempt
from typing import Set
from websockets.exceptions import (
    InvalidHandshake,
    WebSocketException,
    InvalidStatus
)

TRANSIENT_HANDSHAKE_STATUSES: Set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests (Rate limit)
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}

def is_transient_websocket_error(exc:BaseException):
    if isinstance(exc,(OSError,ConnectionRefusedError,ConnectionResetError,TimeoutError)):
        return True
    if isinstance(exc,(InvalidHandshake)):
        return True
    if isinstance(exc,InvalidStatus):
        return exc.response.status_code in TRANSIENT_HANDSHAKE_STATUSES
    if isinstance(exc, WebSocketException):
        exc_name = type(exc).__name__
        return any(k in exc_name for k in ("Timeout", "Reset", "Aborted"))
    return False

@retry(
    retry=retry_if_exception(is_transient_websocket_error),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=1),
    stop=stop_after_attempt(4),
    reraise=True,
)
async def websocket_connect_with_retry(url,headers):
    return await websockets.connect(url, additional_headers=headers)

router = APIRouter()
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

elevenlabs = AsyncElevenLabs(
    api_key=settings.elevenlabs_api_key,
)


@router.post("/voice/incoming")
def incoming_call():
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"wss://{settings.domain}/ws/call")
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/ws/call")
async def call(twilio_ws:WebSocket):
    await twilio_ws.accept()
    stream_sid = None
    call_sid = None
    reply_task = None
    openai_ws = None

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    try:
        openai_ws = await websocket_connect_with_retry(OPENAI_REALTIME_URL,headers)
        session_update = {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio":{
                    "input": {
                        "format": {
                        "type": "audio/pcmu",
                        },
                        "transcription":{
                            "model": "gpt-live-transcribe"
                        },
                        "turn_detection": {
                            "type": "semantic_vad",
                            } 
                        },
                    }
                }
            }
        
        await openai_ws.send(json.dumps(session_update))
        try:
            async def generate_and_play_reply(transcript, stream_sid):
                result = await asyncio.to_thread(handle_incoming,transcript,stream_sid,"voice")
                audio_response = elevenlabs.text_to_speech.stream(
                    voice_id="pNInz6obpgDQGcFmaJgB",
                    output_format="ulaw_8000",
                    text=result,
                    model_id="eleven_multilingual_v2",
                    voice_settings=VoiceSettings(
                        stability=0.0,
                        similarity_boost=1.0,
                        style=0.0,
                        use_speaker_boost=True,
                        speed=1.0,
                        ),
                    )
                async for chunk in audio_response:
                    audio_b64 = base64.b64encode(chunk).decode("utf-8")
                    twilio_msg = {
                        "event": "media",
                        "streamSid": stream_sid,
                        "media": {
                            "payload": audio_b64
                            }
                        }
                    await twilio_ws.send_text(json.dumps(twilio_msg))
            async def receive_from_twilio():
                nonlocal call_sid
                nonlocal stream_sid
                try:
                    while True:
                        message_text = await twilio_ws.receive_text()
                        data = json.loads(message_text)
                        event_type = data.get("event")

                        if event_type == "connected":
                            logger.info("twilio_stream_connected")
                        elif event_type == "start":
                            stream_sid = data["start"]["streamSid"]
                            call_sid = data["start"]["callSid"]
                            logger.info("call_started", call_sid=call_sid, stream_sid=stream_sid)

                        elif event_type == "media":
                            audio_append = {
                                "type": "input_audio_buffer.append",
                                "audio": data["media"]["payload"]
                            }
                            await openai_ws.send(json.dumps(audio_append))
                        elif event_type == "stop":
                            logger.info("call_ended", call_sid=call_sid, stream_sid=stream_sid)

                except Exception as e:
                    logger.error("twilio_receive_error", call_sid=call_sid, error=str(e))

            async def receive_from_openai():
                nonlocal reply_task
                nonlocal stream_sid
                try:
                      async for raw_msg in openai_ws:
                           event = json.loads(raw_msg)
                           event_type = event.get("type")
                           if event_type == "input_audio_buffer.speech_started":
                                logger.info("speech_started", call_sid=call_sid)
                                if reply_task and not reply_task.done():
                                    logger.info("speech_interrupted", call_sid=call_sid)
                                    reply_task.cancel()
                                    await twilio_ws.send_text(json.dumps({"event": "clear", "streamSid": stream_sid}))
                           elif event_type == "input_audio_buffer.speech_stopped":
                                logger.info("speech_stopped", call_sid=call_sid)
                           elif event_type == "conversation.item.input_audio_transcription.completed":
                                logger.info("transcript_received", call_sid=call_sid)
                                reply_task = asyncio.create_task(generate_and_play_reply(event["transcript"],stream_sid=stream_sid))

                except Exception as e:
                    logger.error("openai_receive_error", call_sid=call_sid, error=str(e))

            await asyncio.gather(receive_from_twilio(), receive_from_openai())
        finally:
                logger.info("call_cleanup", call_sid=call_sid)
    finally:
        if openai_ws:
            await openai_ws.close()