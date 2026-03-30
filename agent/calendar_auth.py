"""
agent/calendar_auth.py
Google Calendar authentication.
- Production (Railway): reads GOOGLE_TOKEN_B64 env var (base64 encoded token.json)
- Local: reads token.json file directly
"""
import os
import json
import base64
import logging
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")


def get_calendar_service():
    """
    Returns an authenticated Google Calendar API service.
    Tries GOOGLE_TOKEN_B64 env var first (Railway), falls back to token.json (local).
    """
    creds = None

    # --- Production: base64-encoded token ---
    token_b64 = os.environ.get("GOOGLE_TOKEN_B64")
    if token_b64:
        try:
            token_data = json.loads(base64.b64decode(token_b64).decode())
            log.info("Loaded Google credentials from GOOGLE_TOKEN_B64")
            creds = Credentials(
                token=token_data.get("token"),
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id"),
                client_secret=token_data.get("client_secret"),
                scopes=token_data.get("scopes", SCOPES),
            )
        except Exception as e:
            log.error("Failed to parse GOOGLE_TOKEN_B64: %s", e)

    # --- Local: read from token.json file ---
    elif os.path.exists(TOKEN_FILE):
        log.info("Loaded Google credentials from %s", TOKEN_FILE)
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_TOKEN_B64 env var (production) or run scripts/auth_google.py (local)."
        )

    # Refresh if expired
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            log.info("Refreshing expired Google token...")
            creds.refresh(Request())
            log.info("Token refreshed successfully.")
            # Write back locally if possible
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, "w") as f:
                    f.write(creds.to_json())
        else:
            raise RuntimeError("Google credentials invalid and cannot be refreshed.")

    return build("calendar", "v3", credentials=creds)
