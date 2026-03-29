"""
agent/agent.py
LangGraph ReAct agent — Google Calendar assistant.
"""
import os
from datetime import datetime, timedelta, date
import pytz
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from agent.calendar_tools import CALENDAR_TOOLS
from dotenv import load_dotenv

load_dotenv()

TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "America/Chicago")

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
- If the message is ambiguous, ask one clarifying question before acting.
- Never invent event details — only use what the user provides.
"""


def _date_prefix() -> str:
    """
    Build date context showing today + next 7 days.
    Uses a rolling 7-day window instead of ISO week to avoid
    Mon-anchored week confusion when today is Saturday/Sunday.
    """
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


def run_agent(user_message: str) -> str:
    """Prepend date context, run the agent, return plain-text reply."""
    augmented = _date_prefix() + user_message
    result = get_agent().invoke({
        "messages": [HumanMessage(content=augmented)]
    })
    return result["messages"][-1].content
