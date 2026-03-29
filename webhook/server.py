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

# redirect_slashes=False prevents 307 redirects on trailing slash
app = FastAPI(title="Calendar Agent Webhook", redirect_slashes=False)

def get_verify_token():
    return os.environ.get("WA_VERIFY_TOKEN", "")

def get_access_token():
    return os.environ.get("WA_ACCESS_TOKEN", "")

def get_phone_number_id():
    return os.environ.get("WA_PHONE_NUMBER_ID", "")


@app.get("/")
async def health():
    return {"status": "ok", "service": "calendar-agent"}


@app.get("/debug")
async def debug():
    token = os.environ.get("WA_VERIFY_TOKEN", "NOT_SET")
    return {
        "WA_VERIFY_TOKEN_set": token != "NOT_SET",
        "WA_VERIFY_TOKEN_length": len(token),
        "WA_VERIFY_TOKEN_value": token,
        "all_env_keys": [k for k in os.environ.keys() if k.startswith("WA_")]
    }


async def _verify(request: Request):
    """Shared verification logic for both /webhook and /webhook/"""
    params = request.query_params
    mode = params.get("hub.mode") or params.get("hub_mode")
    challenge = params.get("hub.challenge") or params.get("hub_challenge")
    token = params.get("hub.verify_token") or params.get("hub_verify_token")
    verify_token = get_verify_token()

    log.info("Webhook verify — mode=%s token=%s challenge=%s", mode, token, challenge)
    log.info("Server verify token = '%s' (len=%d)", verify_token, len(verify_token))

    if mode == "subscribe" and token == verify_token:
        log.info("Webhook verified successfully.")
        return PlainTextResponse(content=challenge)

    log.warning("Verification failed — Got: '%s' Expected: '%s'", token, verify_token)
    raise HTTPException(status_code=403, detail="Verification failed")


async def _receive(request: Request, background_tasks: BackgroundTasks):
    """Shared inbound message handler for both /webhook and /webhook/"""
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


# Register both with and without trailing slash
@app.get("/webhook")
@app.get("/webhook/")
async def verify_webhook(request: Request):
    return await _verify(request)


@app.post("/webhook")
@app.post("/webhook/")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    return await _receive(request, background_tasks)


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
    phone_id = get_phone_number_id()
    wa_api_url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(wa_api_url, json=payload, headers=headers)
        if resp.status_code != 200:
            log.error("Failed to send WA message: %s %s", resp.status_code, resp.text)
        else:
            log.info("WA message sent to %s", to)
