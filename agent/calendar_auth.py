"""
agent/calendar_auth.py
Google Calendar authentication.
- Locally: reads credentials.json + token.json files
- On Railway/production: reads GOOGLE_TOKEN_JSON env var (no files needed)
"""
import os
import json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")


def get_calendar_service():
    """
    Returns an authenticated Google Calendar API service.
    Prefers GOOGLE_TOKEN_JSON env var (Railway) over token.json file (local).
    Auto-refreshes expired tokens and writes back if possible.
    """
    creds = None

    # --- Production path: read from env var ---
    token_json_str = os.getenv("GOOGLE_TOKEN_JSON")
    if token_json_str:
        token_data = json.loads(token_json_str)
        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
            scopes=token_data.get("scopes", SCOPES),
        )

    # --- Local path: read from token.json file ---
    elif os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_TOKEN_JSON env var (production) or run scripts/auth_google.py (local)."
        )

    # Refresh if expired
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Write back locally if file exists
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
        else:
            raise RuntimeError("Google credentials expired and cannot be refreshed.")

    return build("calendar", "v3", credentials=creds)
