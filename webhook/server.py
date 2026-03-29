"""
webhook/server.py
FastAPI server with two endpoints:

  GET  /webhook  — Meta's one-time webhook verification handshake
  POST /webhook  — Receives inbound WhatsApp messages, runs the agent, replies

Run locally:
    uvicorn webhook.server:app --reload --port 8000

For local testing with Meta, expose via ngrok:
    ngrok http 8000
Then paste the ngrok HTTPS URL into Meta Developer Console → WhatsApp → Configuration.
"""
import os
import logging
import httpx
from fastapi import FastAPI, Request, Query, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Calendar Agent Webhook")

WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "my-secret-verify-token")
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_API_URL = f"https://graph.facebook.com/v19.0/{WA_PHONE_NUMBER_ID}/messages"


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
async def health():
    return {"status": "ok", "service": "calendar-agent"}


# ─────────────────────────────────────────────────────────────────────────────
# Webhook verification (Meta calls this once during setup)
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    """
    Meta sends a GET request to verify the webhook URL.
    We must respond with hub.challenge if the verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == WA_VERIFY_TOKEN:
        log.info("Webhook verified successfully.")
        return PlainTextResponse(content=hub_challenge)
    log.warning("Webhook verification failed — token mismatch.")
    raise HTTPException(status_code=403, detail="Verification failed")


# ─────────────────────────────────────────────────────────────────────────────
# Inbound message handler
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """
    Meta POSTs every inbound WhatsApp message here.
    We immediately return 200 OK (Meta requires this within 15s),
    then process and reply in a background task.
    """
    body = await request.json()
    log.info("Inbound webhook payload: %s", body)

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]

        # Ignore status updates (delivered, read, etc.) — only handle messages
        if "messages" not in change:
            return {"status": "ignored"}

        message = change["messages"][0]

        # Only handle text messages for now
        if message.get("type") != "text":
            return {"status": "non-text ignored"}

        user_text = message["text"]["body"]
        sender_id = message["from"]  # The user's WhatsApp number (e.g. "15125551234")

        log.info("Message from %s: %s", sender_id, user_text)

        # Process in background so we return 200 immediately
        background_tasks.add_task(process_and_reply, sender_id, user_text)

    except (KeyError, IndexError) as e:
        log.error("Unexpected webhook payload structure: %s", e)

    return {"status": "ok"}


async def process_and_reply(sender_id: str, user_text: str):
    """Run the agent and send the response back via WhatsApp Cloud API."""
    # Import here to avoid circular import at module load time
    from agent.agent import run_agent

    try:
        reply = run_agent(user_text)
        log.info("Agent reply to %s: %s", sender_id, reply)
        await send_whatsapp_message(sender_id, reply)
    except Exception as e:
        log.error("Agent error: %s", e)
        await send_whatsapp_message(
            sender_id,
            "⚠️ Sorry, something went wrong. Please try again."
        )


async def send_whatsapp_message(to: str, text: str):
    """Send a plain text WhatsApp message via Meta Cloud API."""
    headers = {
        "Authorization": f"Bearer {WA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(WA_API_URL, json=payload, headers=headers)
        if resp.status_code != 200:
            log.error("Failed to send WA message: %s %s", resp.status_code, resp.text)
        else:
            log.info("WA message sent to %s", to)
