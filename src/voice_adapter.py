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

router = APIRouter()
OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"

elevenlabs = AsyncElevenLabs(
    api_key=settings.elevenlabs_api_key,
)


@router.post("/voice/incoming")
def incoming_call():
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url="wss://your-domain.ngrok-free.app/ws/call")
    response.append(connect)
    return Response(content=str(response), media_type="application/xml")

@router.websocket("/ws/call")
async def call(twilio_ws:WebSocket):
    await twilio_ws.accept()
    stream_sid = None
    call_sid = None
    reply_task = None

    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "OpenAI-Beta": "realtime=v1"
    }

    async with websockets.connect(OPENAI_REALTIME_URL, additional_headers=headers) as openai_ws:
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