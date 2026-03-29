"""
agent/calendar_tools.py
LangChain tools that wrap Google Calendar API operations.
Each tool is a plain Python function decorated with @tool so LangGraph
can call them during agent reasoning.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
import pytz
from langchain_core.tools import tool
from agent.calendar_auth import get_calendar_service
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "America/Chicago")


def _service():
    """Lazy-load the calendar service (reuses token.json on every call)."""
    return get_calendar_service()


def _localise(dt_str: str, tz_name: str = TIMEZONE) -> str:
    """
    Accept flexible datetime strings and return an RFC3339 string with timezone offset.
    Handles: '2026-04-05 14:00', '2026-04-05T14:00:00', '2026-04-05T14:00:00-05:00'
    """
    tz = pytz.timezone(tz_name)
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            naive = datetime.strptime(dt_str.split("+")[0].split("-05")[0].strip(), fmt)
            return tz.localize(naive).isoformat()
        except ValueError:
            continue
    # Already has offset — return as-is
    return dt_str


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@tool
def create_calendar_event(
    summary: str,
    start_datetime: str,
    end_datetime: str,
    description: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Create a new event on the user's primary Google Calendar.

    Args:
        summary: Event title, e.g. 'Dentist appointment'
        start_datetime: Start time in 'YYYY-MM-DD HH:MM' or ISO format
        end_datetime: End time in 'YYYY-MM-DD HH:MM' or ISO format
        description: Optional notes or details about the event
        location: Optional location string

    Returns:
        Confirmation message with a link to the created event.
    """
    try:
        svc = _service()
        event_body = {
            "summary": summary,
            "start": {"dateTime": _localise(start_datetime), "timeZone": TIMEZONE},
            "end": {"dateTime": _localise(end_datetime), "timeZone": TIMEZONE},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        event = svc.events().insert(calendarId="primary", body=event_body).execute()
        link = event.get("htmlLink", "")
        return f"✅ Created '{summary}' on {start_datetime}. View: {link}"
    except Exception as e:
        return f"❌ Failed to create event: {str(e)}"


@tool
def list_calendar_events(
    days_ahead: int = 7,
    max_results: int = 10,
) -> str:
    """
    List upcoming events on the user's primary Google Calendar.

    Args:
        days_ahead: How many days ahead to look (default: 7)
        max_results: Maximum number of events to return (default: 10)

    Returns:
        A formatted list of upcoming events with times and titles.
    """
    try:
        svc = _service()
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        result = svc.events().list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"📅 No events in the next {days_ahead} days."

        lines = [f"📅 Upcoming events (next {days_ahead} days):"]
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))
            # Parse and reformat for readability
            try:
                dt = datetime.fromisoformat(start)
                start_fmt = dt.strftime("%a %b %-d, %-I:%M %p")
            except Exception:
                start_fmt = start
            lines.append(f"  • {start_fmt} — {e.get('summary', '(no title)')}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to list events: {str(e)}"


@tool
def delete_calendar_event(event_title: str, date: str) -> str:
    """
    Delete a calendar event by matching its title and date.
    Deletes the first matching event found.

    Args:
        event_title: Title/summary of the event to delete (case-insensitive match)
        date: Date of the event in 'YYYY-MM-DD' format

    Returns:
        Confirmation or error message.
    """
    try:
        svc = _service()
        tz = pytz.timezone(TIMEZONE)
        day_start = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        day_end = day_start + timedelta(days=1)

        result = svc.events().list(
            calendarId="primary",
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        match = next(
            (e for e in events if event_title.lower() in e.get("summary", "").lower()),
            None,
        )

        if not match:
            return f"❌ No event matching '{event_title}' found on {date}."

        svc.events().delete(calendarId="primary", eventId=match["id"]).execute()
        return f"🗑️ Deleted '{match['summary']}' on {date}."
    except Exception as e:
        return f"❌ Failed to delete event: {str(e)}"


@tool
def check_availability(date: str) -> str:
    """
    Check what's already scheduled on a given date to assess availability.

    Args:
        date: Date to check in 'YYYY-MM-DD' format

    Returns:
        List of events on that day, or a message saying the day is free.
    """
    try:
        svc = _service()
        tz = pytz.timezone(TIMEZONE)
        day_start = tz.localize(datetime.strptime(date, "%Y-%m-%d"))
        day_end = day_start + timedelta(days=1)

        result = svc.events().list(
            calendarId="primary",
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events = result.get("items", [])
        if not events:
            return f"✅ {date} is clear — no events scheduled."

        lines = [f"📋 Schedule for {date}:"]
        for e in events:
            start = e["start"].get("dateTime", "all day")
            end = e["end"].get("dateTime", "")
            try:
                s = datetime.fromisoformat(start).strftime("%-I:%M %p")
                en = datetime.fromisoformat(end).strftime("%-I:%M %p")
                time_str = f"{s}–{en}"
            except Exception:
                time_str = start
            lines.append(f"  • {time_str}: {e.get('summary', '(no title)')}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ Failed to check availability: {str(e)}"


@tool
def share_calendar(email: str, role: str = "reader") -> str:
    """
    Share the user's primary Google Calendar with another person by email.

    Args:
        email: Email address of the person to share with
        role: 'reader' (view only) or 'writer' (can edit). Defaults to 'reader'.

    Returns:
        Confirmation message.
    """
    try:
        if role not in ("reader", "writer"):
            return "❌ Role must be 'reader' (view only) or 'writer' (can edit)."

        svc = _service()
        rule = {
            "scope": {"type": "user", "value": email},
            "role": role,
        }
        svc.acl().insert(calendarId="primary", body=rule).execute()
        access = "view-only" if role == "reader" else "edit"
        return f"📤 Calendar shared with {email} ({access} access). They'll receive a Google Calendar invite."
    except Exception as e:
        return f"❌ Failed to share calendar: {str(e)}"


# All tools bundled for import into the agent
CALENDAR_TOOLS = [
    create_calendar_event,
    list_calendar_events,
    delete_calendar_event,
    check_availability,
    share_calendar,
]
