# Calendar Agent 🗓️

A personal AI calendar assistant that manages your Google Calendar via WhatsApp.
Send text or voice messages from WhatsApp and the agent creates, lists, checks,
deletes, and shares events on your behalf — running 24/7 in the cloud.

## Architecture

```
Your iPhone (WhatsApp)
        │
        ▼
   Twilio API
  (WhatsApp channel)
        │
        ▼
  Railway (FastAPI)
  webhook/server.py
        │
   ┌────┴────┐
   │         │
Text msg   Voice msg
   │         │
   │    OpenAI Whisper
   │    (transcription)
   │         │
   └────┬────┘
        │
  LangGraph ReAct Agent
  (GPT-4o-mini)
        │
  Google Calendar API
  (read/write/share)
        │
  Reply back to WhatsApp
```

## What you can say (text or voice)

| Message | Action |
|---|---|
| `Am I free this Friday?` | Checks availability |
| `What's on my calendar this week?` | Lists upcoming events |
| `Add dentist Tuesday at 10am to 11am` | Creates event |
| `Delete dentist appointment on April 7` | Deletes event |
| `Share my calendar with bob@example.com` | Shares view-only |
| `Share my calendar with alice@example.com as editor` | Shares with edit access |

---

## Stack

| Component | Service | Cost |
|---|---|---|
| WhatsApp channel | Twilio sandbox (dev) / paid number (prod) | Free sandbox |
| Voice transcription | OpenAI Whisper (`whisper-1`) | ~$0.006/min |
| AI reasoning | OpenAI GPT-4o-mini | ~$0.001/msg |
| Calendar | Google Calendar API | Free |
| Hosting | Railway | Free tier |

---

## Local Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/calendar-agent
cd calendar-agent
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys
```

### 3. Google Calendar auth (one-time)

Place your `credentials.json` from Google Cloud Console in the project root, then:

```bash
python3 scripts/auth_google.py
```

This opens a browser (or prints a URL for WSL users) — sign in, grant access.
Creates `token.json` which the agent uses automatically.

### 4. Test the agent locally

```bash
python3 scripts/test_agent.py
```

### 5. Run the webhook server locally

```bash
uvicorn webhook.server:app --reload --port 8000
```

### 6. Expose via ngrok (for local Twilio testing)

```bash
ngrok http 8000
# Copy the https://xxxx.ngrok-free.app URL
```

---

## Twilio Setup

### Sandbox (free, for development)

1. Sign up at [twilio.com](https://twilio.com)
2. Go to **Messaging → Try it out → Send a WhatsApp message**
3. Follow the sandbox activation — send the join code from your iPhone WhatsApp
4. Under **Sandbox settings**, set:
   - **When a message comes in**: `https://your-domain.com/webhook`
   - Method: `HTTP POST`
5. Note your:
   - **Account SID** (`ACxxxxxxx`)
   - **Auth Token**
   - **Sandbox number** (e.g. `+14155238886`)

### Production (paid, permanent)

1. Go to **Messaging → Senders → WhatsApp Senders**
2. Register a phone number and connect your Meta Business Account
3. Use that number as `TWILIO_WHATSAPP_NUMBER`

---

## Deploy to Railway

### 1. Push to GitHub

```bash
git init
git add .
git commit -m "Initial calendar agent"
git remote add origin https://github.com/YOUR_USERNAME/calendar-agent
git push -u origin main
```

### 2. Create Railway project

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Select your repo

### 3. Set environment variables

Use the Railway CLI (most reliable method):

```bash
npm install -g @railway/cli
railway login
railway link   # run from project root
railway variables set OPENAI_API_KEY=sk-...
railway variables set TWILIO_ACCOUNT_SID=ACxxxxxxx
railway variables set TWILIO_AUTH_TOKEN=xxxxxxx
railway variables set TWILIO_WHATSAPP_NUMBER=+14155238886
railway variables set CALENDAR_TIMEZONE=America/Chicago
railway variables set PORT=8000
```

### 4. Set Google token (base64 encoded — avoids JSON escaping issues)

```bash
# Run locally to encode token.json
python3 -c "
import base64
with open('token.json') as f:
    data = f.read()
print(base64.b64encode(data.encode()).decode())
"

# Set in Railway (base64 has no special characters)
railway variables set GOOGLE_TOKEN_B64=eyJ0b2tlbiI6...
railway redeploy
```

### 5. Update Twilio webhook URL

In Twilio Console → **Sandbox settings**, update:
```
https://your-railway-app.up.railway.app/webhook
```

---

## Environment Variables

| Variable | Description | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID | Twilio Console → Account Info |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | Twilio Console → Account Info |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp number | Twilio Console → sandbox number |
| `GOOGLE_TOKEN_B64` | Base64-encoded token.json | Generated locally via `auth_google.py` |
| `CALENDAR_TIMEZONE` | Your timezone | e.g. `America/Chicago`, `America/New_York` |
| `PORT` | Server port | Set to `8000` |

---

## Project Structure

```
calendar-agent/
├── agent/
│   ├── __init__.py
│   ├── calendar_auth.py     # Google OAuth — reads GOOGLE_TOKEN_B64 or token.json
│   ├── calendar_tools.py    # LangChain @tool functions (create, list, delete, share)
│   └── agent.py             # LangGraph ReAct agent with date context injection
├── webhook/
│   ├── __init__.py
│   └── server.py            # FastAPI — handles text + voice via Twilio + Whisper
├── scripts/
│   ├── auth_google.py       # One-time Google OAuth (WSL-compatible)
│   └── test_agent.py        # Local CLI test without WhatsApp
├── .env.example
├── .gitignore               # credentials.json and token.json excluded
├── Procfile                 # Railway/Heroku deploy command
├── requirements.txt
└── README.md
```

---

## How Voice Messages Work

1. You send a WhatsApp voice note
2. Twilio receives it and POSTs the audio URL to `/webhook`
3. The server downloads the audio using Twilio credentials
4. Sends it to OpenAI Whisper (`whisper-1`) for transcription
5. The transcript is passed to the calendar agent — same as typed text
6. Reply is sent back to your WhatsApp

Supported audio formats: OGG, MP3, MP4, AMR, WAV, WebM

---

## Maintenance Notes

### Google token refresh
The Google access token expires every hour but auto-refreshes using the
`refresh_token`. No manual action needed. The setup breaks only if you:
- Revoke access at [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
- Delete the Google Cloud project
- Reset the OAuth client secret

If you reset the client secret, run `auth_google.py` locally again and
update `GOOGLE_TOKEN_B64` in Railway.

### Meta/Twilio access token
The Twilio Auth Token never expires. No rotation needed.

### Twilio sandbox limitation
The sandbox requires periodic re-joining and only works for registered test numbers.
For permanent production use, register a proper WhatsApp Business number in Twilio.
