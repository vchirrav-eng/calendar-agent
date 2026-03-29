# Calendar Agent 🗓️

A personal AI calendar assistant that manages your Google Calendar via WhatsApp.
Send natural language messages from WhatsApp and the agent creates, lists, deletes,
checks, and shares events on your behalf.

## Architecture

```
Your iPhone (WhatsApp) ──► Meta Cloud API ──► Webhook (FastAPI)
                                                      │
                                              LangGraph ReAct Agent
                                                      │
                                           ┌──────────┴──────────┐
                                      OpenAI GPT          Google Calendar API
```

## What you can say

| Message | Action |
|---|---|
| `Add dentist Friday 3pm to 4pm` | Creates event |
| `What's on my calendar this week?` | Lists upcoming events |
| `Am I free Thursday?` | Checks availability |
| `Delete dentist appointment on April 4` | Deletes event |
| `Share my calendar with bob@example.com` | Shares (view-only) |
| `Share my calendar with alice@example.com as editor` | Shares (edit access) |

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/calendar-agent
cd calendar-agent
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your keys (see below for where to get each one)
```

### 3. Add Google credentials

- Place your `credentials.json` (downloaded from Google Cloud Console) in the project root
- Run the one-time auth flow — opens a browser for Google sign-in:

```bash
python scripts/auth_google.py
```

This creates `token.json` which the agent uses automatically from then on.

### 4. Test the agent locally (no WhatsApp needed yet)

```bash
python scripts/test_agent.py
```

Try: `What's on my calendar this week?` or `Add lunch with Alex tomorrow at noon to 1pm`

### 5. Run the webhook server locally

```bash
uvicorn webhook.server:app --reload --port 8000
```

### 6. Expose locally for Meta webhook setup (dev only)

Install [ngrok](https://ngrok.com/download) then:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok.io` URL — you'll need it in the next step.

---

## Meta Cloud API Setup

1. Go to [developers.facebook.com](https://developers.facebook.com) → Create App → Business
2. Add **WhatsApp** product
3. Under **WhatsApp → API Setup**, note your:
   - **Phone Number ID** → `WA_PHONE_NUMBER_ID` in `.env`
   - **Temporary Access Token** → `WA_ACCESS_TOKEN` in `.env`
4. Under **WhatsApp → Configuration**:
   - Callback URL: `https://your-ngrok-url/webhook`
   - Verify Token: the string you put in `WA_VERIFY_TOKEN` in `.env`
   - Click **Verify and Save**
   - Under **Webhook fields**, subscribe to **messages**
5. **Add your personal WhatsApp number as a test recipient** under API Setup

> For production: generate a permanent System User access token in Meta Business Manager
> instead of the temporary one.

---

## Deploy to Railway (free tier)

1. Push to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add all environment variables from `.env` in the Railway dashboard
4. Upload `credentials.json` and `token.json` as files (Railway → Files tab)
   or base64-encode them as env vars (see note below)
5. Railway gives you a public HTTPS URL — use that as your Meta webhook callback URL

> **Note on token.json in production**: The OAuth token file must persist across deploys.
> Easiest approach: run `python scripts/auth_google.py` locally, then copy the contents
> of `token.json` into a `GOOGLE_TOKEN_JSON` env var, and update `calendar_auth.py` to
> write it from the env var on startup.

---

## Environment Variables

| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `WA_PHONE_NUMBER_ID` | Meta Developer Console → WhatsApp → API Setup |
| `WA_ACCESS_TOKEN` | Meta Developer Console → WhatsApp → API Setup |
| `WA_VERIFY_TOKEN` | Any string you choose (you set this yourself) |
| `GOOGLE_CREDENTIALS_FILE` | Path to `credentials.json` from Google Cloud Console |
| `GOOGLE_TOKEN_FILE` | Path to `token.json` (auto-generated after first auth) |
| `CALENDAR_TIMEZONE` | Your timezone, e.g. `America/Chicago` |

---

## Project structure

```
calendar-agent/
├── agent/
│   ├── __init__.py
│   ├── calendar_auth.py     # Google OAuth flow
│   ├── calendar_tools.py    # LangChain @tool functions
│   └── agent.py             # LangGraph ReAct agent
├── webhook/
│   ├── __init__.py
│   └── server.py            # FastAPI webhook server
├── scripts/
│   ├── auth_google.py       # One-time Google auth
│   └── test_agent.py        # Local CLI test
├── .env.example
├── .gitignore
├── Procfile
├── requirements.txt
└── README.md
```
