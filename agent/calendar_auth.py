"""
agent/calendar_auth.py
Handles Google OAuth flow and returns an authenticated API resource.
Run this file directly once to generate token.json:
    python -m agent.calendar_auth
"""
import os
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")


def get_calendar_service():
    """
    Returns an authenticated Google Calendar API service object.
    On first run, opens a browser for OAuth consent and saves token.json.
    On subsequent runs, reloads token.json (refreshing automatically if expired).
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


if __name__ == "__main__":
    svc = get_calendar_service()
    print("✅ Google Calendar authenticated successfully.")
    cal = svc.calendars().get(calendarId="primary").execute()
    print(f"   Calendar: {cal['summary']} ({cal['id']})")
