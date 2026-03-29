#!/usr/bin/env python3
"""
scripts/auth_google.py
WSL-compatible Google OAuth flow.
Prints the auth URL so you can open it in your Windows browser,
then pastes the redirect URL back to complete auth.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", "token.json")

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",  # out-of-band: no local server needed
    )

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    print("\n" + "="*60)
    print("STEP 1: Open this URL in your Windows browser:")
    print("="*60)
    print(f"\n{auth_url}\n")
    print("="*60)
    print("STEP 2: Sign in, grant access, then copy the code shown.")
    print("="*60 + "\n")

    code = input("STEP 3: Paste the code here and press Enter: ").strip()

    flow.fetch_token(code=code)
    creds = flow.credentials

    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())

    svc = build("calendar", "v3", credentials=creds)
    cal = svc.calendars().get(calendarId="primary").execute()

    print(f"\n✅ Success! Authenticated as: {cal['summary']}")
    print(f"   token.json saved — the agent will use this automatically.\n")

if __name__ == "__main__":
    main()
