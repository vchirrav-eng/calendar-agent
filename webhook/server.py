"""
webhook/server.py
FastAPI server using Twilio for WhatsApp messaging.
Twilio sends inbound messages as form-encoded POST requests.
"""
import os
import logging
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from twilio.rest import Client
from twilio.request_validator import RequestValidator
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
    Key fields: Body (message text), From (sender's WhatsApp number)
    """
    form = await request.form()
    body = form.get("Body", "").strip()
    sender = form.get("From", "")  # format: whatsapp:+917993479200

    log.info("Message from %s: %s", sender, body)

    if not body or not sender:
        return PlainTextResponse(content="", status_code=200)

    background_tasks.add_task(process_and_reply, sender, body)

    # Twilio expects an empty 200 response — actual reply sent via API
    return PlainTextResponse(content="", status_code=200)


async def process_and_reply(sender: str, user_text: str):
    from agent.agent import run_agent
    try:
        reply = run_agent(user_text)
        log.info("Agent reply to %s: %s", sender, reply)
        await send_whatsapp_message(sender, reply)
    except Exception as e:
        log.error("Agent error: %s", e, exc_info=True)
        await send_whatsapp_message(sender, "⚠️ Sorry, something went wrong. Please try again.")


async def send_whatsapp_message(to: str, text: str):
    """Send a WhatsApp message via Twilio."""
    try:
        client = get_twilio_client()
        from_number = f"whatsapp:{TWILIO_WHATSAPP_NUMBER}"
        # Ensure to has whatsapp: prefix
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
