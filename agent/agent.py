"""
agent/agent.py
LangGraph ReAct agent — Google Calendar assistant.
Maintains per-sender conversation history in memory.
History is automatically cleared at midnight (user's timezone) each day.
"""
import os
import logging
from datetime import datetime, timedelta, date
from collections import defaultdict
import pytz
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from agent.calendar_tools import CALENDAR_TOOLS
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "America/Chicago")

# ─────────────────────────────────────────────────────────────────────────────
# Conversation history store
# {sender_id: {"messages": [...], "date": date}}
# Automatically cleared when the date changes (i.e. at midnight)
# ─────────────────────────────────────────────────────────────────────────────
_history: dict = defaultdict(lambda: {"messages": [], "date": None})
MAX_HISTORY_MESSAGES = 20  # keep last 20 messages per sender (~10 turns)


def _get_today() -> date:
    return datetime.now(pytz.timezone(TIMEZONE)).date()


def _get_history(sender_id: str) -> list:
    """Return message history for sender, clearing it if it's a new day."""
    today = _get_today()
    entry = _history[sender_id]

    if entry["date"] != today:
        if entry["date"] is not None:
            log.info("Clearing history for %s (new day: %s)", sender_id, today)
        entry["messages"] = []
        entry["date"] = today

    return entry["messages"]


def _save_history(sender_id: str, messages: list):
    """Save trimmed message history for sender."""
    # Keep only the last MAX_HISTORY_MESSAGES to cap memory
    _history[sender_id]["messages"] = messages[-MAX_HISTORY_MESSAGES:]
    _history[sender_id]["date"] = _get_today()


def _log_memory_usage():
    """Log current memory usage across all senders."""
    total_msgs = sum(len(v["messages"]) for v in _history.values())
    log.info("History store: %d senders, %d total messages", len(_history), total_msgs)


SYSTEM_PROMPT = """You are a personal calendar assistant managing Google Calendar via WhatsApp.

CRITICAL DATE RULE: Every user message starts with a [DATE CONTEXT] block listing
exact dates for today and the next 7 days. Use ONLY those dates — never calculate
your own, never use training data for dates. Just read the date from the block.

You can:
- Create events (confirm title, date, start/end time with user if missing)
- List upcoming events
- Check availability on a specific date
- Delete events
- Share the calendar with someone by email

Guidelines:
- Be concise — this is WhatsApp, keep replies short.
- Confirm event details after creating them.
- You have memory of this conversation — use context from earlier messages.
- If the message is ambiguous, ask one clarifying question before acting.
- Never invent event details — only use what the user provides.
"""


def _date_prefix() -> str:
    """Build date context block prepended to every user message."""
    tz = pytz.timezone(TIMEZONE)
    today = datetime.now(tz).date()
    lines = ["[DATE CONTEXT — read these, do not calculate your own dates]"]
    lines.append(f"Today is {today.strftime('%A, %B %-d, %Y')} = {today.isoformat()}")
    lines.append("Next 7 days:")
    for i in range(1, 8):
        d = today + timedelta(days=i)
        lines.append(f"  {d.strftime('%A, %B %-d')} = {d.isoformat()}")
    lines.append("[END DATE CONTEXT]")
    lines.append("")
    return "\n".join(lines)


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
        _agent = create_react_agent(llm, CALENDAR_TOOLS, prompt=SYSTEM_PROMPT)
    return _agent


def run_agent(user_message: str, sender_id: str = "default") -> str:
    """
    Run the agent with conversation history for the given sender.
    History resets automatically at midnight (user's timezone).
    """
    # Get existing history (cleared if new day)
    history = _get_history(sender_id)

    # Prepend date context to user message
    augmented = _date_prefix() + user_message
    history.append(HumanMessage(content=augmented))

    # Run agent with full history
    result = get_agent().invoke({"messages": history})

    # Extract reply from last message
    reply = result["messages"][-1].content

    # Save updated history (AI response appended)
    history.append(AIMessage(content=reply))
    _save_history(sender_id, history)

    _log_memory_usage()
    return reply
