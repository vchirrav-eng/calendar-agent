"""
webhook/server.py
FastAPI server — handles Meta Cloud API webhook verification and inbound messages.
"""
import os
import logging
import httpx
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Calendar Agent Webhook")

WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "")
WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_API_URL = f"https://graph.facebook.com/v19.0/{WA_PHONE_NUMBER_ID}/messages"


@app.get("/")
async def health():
    return {"status": "ok", "service": "calendar-agent"}


@app.get("/webhook")
async def verify_webhook(request: Request):
    """
    Meta sends hub.mode, hub.challenge, hub.verify_token as query params.
    FastAPI Query() with alias handles dots, but reading from request.query_params
    directly is more reliable when Meta sends both dot and underscore variants.
    """
    params = request.query_params

    # Accept both dot-notation and underscore-notation
    mode = params.get("hub.mode") or params.get("hub_mode")
    challenge = params.get("hub.challenge") or params.get("hub_challenge")
    token = params.get("hub.verify_token") or params.get("hub_verify_token")

    log.info("Webhook verify — mode=%s token=%s challenge=%s", mode, token, challenge)

    if mode == "subscribe" and token == WA_VERIFY_TOKEN:
        log.info("Webhook verified successfully.")
        return PlainTextResponse(content=challenge)

    log.warning("Verification failed — token mismatch. Got: %s Expected: %s", token, WA_VERIFY_TOKEN)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    """Receive inbound WhatsApp messages and process them via the agent."""
    body = await request.json()
    log.info("Inbound payload: %s", body)

    try:
        entry = body["entry"][0]
        change = entry["changes"][0]["value"]

        if "messages" not in change:
            return {"status": "ignored"}

        message = change["messages"][0]

        if message.get("type") != "text":
            return {"status": "non-text ignored"}

        user_text = message["text"]["body"]
        sender_id = message["from"]

        log.info("Message from %s: %s", sender_id, user_text)
        background_tasks.add_task(process_and_reply, sender_id, user_text)

    except (KeyError, IndexError) as e:
        log.error("Unexpected payload structure: %s", e)

    return {"status": "ok"}


async def process_and_reply(sender_id: str, user_text: str):
    from agent.agent import run_agent
    try:
        reply = run_agent(user_text)
        log.info("Agent reply to %s: %s", sender_id, reply)
        await send_whatsapp_message(sender_id, reply)
    except Exception as e:
        log.error("Agent error: %s", e)
        await send_whatsapp_message(sender_id, "⚠️ Sorry, something went wrong. Please try again.")


async def send_whatsapp_message(to: str, text: str):
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
