"""
webhook/server.py
FastAPI server using Twilio for WhatsApp messaging.
Supports text and audio (voice) messages.
Audio is transcribed via OpenAI Whisper before being passed to the agent.
"""
import os
import logging
import tempfile
import httpx
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from twilio.rest import Client
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Calendar Agent Webhook", redirect_slashes=False)


def get_twilio_client():
    return Client(
        os.environ.get("TWILIO_ACCOUNT_SID"),
        os.environ.get("TWILIO_AUTH_TOKEN"),
    )


def get_openai_client():
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


TWILIO_WHATSAPP_NUMBER = os.environ.get("TWILIO_WHATSAPP_NUMBER", "")


@app.get("/")
async def health():
    return {"status": "ok", "service": "calendar-agent"}


@app.get("/debug")
async def debug():
    return {
        "TWILIO_ACCOUNT_SID_set": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
        "TWILIO_AUTH_TOKEN_set": bool(os.environ.get("TWILIO_AUTH_TOKEN")),
        "TWILIO_WHATSAPP_NUMBER": os.environ.get("TWILIO_WHATSAPP_NUMBER", "NOT_SET"),
        "GOOGLE_TOKEN_B64_set": bool(os.environ.get("GOOGLE_TOKEN_B64")),
        "OPENAI_API_KEY_set": bool(os.environ.get("OPENAI_API_KEY")),
    }


@app.post("/webhook")
@app.post("/webhook/")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Twilio sends inbound WhatsApp messages as form-encoded POST.
    Text messages: Body field
    Audio messages: MediaUrl0 + MediaContentType0 fields
    """
    form = await request.form()

    sender = form.get("From", "")          # e.g. whatsapp:+917993479200
    body = form.get("Body", "").strip()
    media_url = form.get("MediaUrl0", "")
    msg_type = form.get("MediaContentType0", "")

    log.info("Inbound from %s — type=%s body=%s media=%s",
             sender, msg_type or "text", body[:80] if body else "", bool(media_url))

    if not sender:
        return PlainTextResponse(content="", status_code=200)

    # Audio message
    if media_url and msg_type.startswith("audio/"):
        background_tasks.add_task(process_audio_and_reply, sender, media_url)
        return PlainTextResponse(content="", status_code=200)

    # Text message
    if body:
        background_tasks.add_task(process_and_reply, sender, body)
        return PlainTextResponse(content="", status_code=200)

    log.info("Ignored non-text/non-audio message from %s", sender)
    return PlainTextResponse(content="", status_code=200)


async def transcribe_audio(media_url: str) -> str:
    """Download audio from Twilio and transcribe via OpenAI Whisper."""
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            media_url,
            auth=(account_sid, auth_token),
            follow_redirects=True,
            timeout=30.0,
        )
        resp.raise_for_status()
        audio_bytes = resp.content
        content_type = resp.headers.get("content-type", "audio/ogg")

    ext_map = {
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".mp4",
        "audio/amr": ".amr",
        "audio/wav": ".wav",
        "audio/webm": ".webm",
    }
    ext = ext_map.get(content_type.split(";")[0].strip(), ".ogg")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        openai_client = get_openai_client()
        with open(tmp_path, "rb") as audio_file:
            transcript = openai_client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
            )
        log.info("Whisper transcript: %s", transcript.text)
        return transcript.text
    finally:
        os.unlink(tmp_path)


async def process_audio_and_reply(sender: str, media_url: str):
    """Transcribe audio then pass transcript to the agent."""
    try:
        log.info("Transcribing audio from %s", sender)
        transcript = await transcribe_audio(media_url)
        if not transcript.strip():
            await send_whatsapp_message(
                sender,
                "⚠️ I couldn't understand the audio. Please try again or send a text message."
            )
            return
        await process_and_reply(sender, transcript)
    except Exception as e:
        log.error("Audio transcription error: %s", e, exc_info=True)
        await send_whatsapp_message(
            sender,
            "⚠️ Couldn't process the audio message. Please try sending text instead."
        )


async def process_and_reply(sender: str, user_text: str):
    """Run the agent with conversation history and send the reply."""
    from agent.agent import run_agent
    try:
        # Pass sender as the history key — history resets automatically at midnight
        reply = run_agent(user_text, sender_id=sender)
        log.info("Agent reply to %s: %s", sender, reply)
        await send_whatsapp_message(sender, reply)
    except Exception as e:
        log.error("Agent error: %s", e, exc_info=True)
        await send_whatsapp_message(
            sender,
            "⚠️ Sorry, something went wrong. Please try again."
        )


async def send_whatsapp_message(to: str, text: str):
    """Send a WhatsApp message via Twilio."""
    try:
        client = get_twilio_client()
        from_number = f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"
        message = client.messages.create(
            body=text,
            from_=from_number,
            to=to,
        )
        log.info("Twilio message sent: SID=%s", message.sid)
    except Exception as e:
        log.error("Failed to send Twilio message: %s", e, exc_info=True)
