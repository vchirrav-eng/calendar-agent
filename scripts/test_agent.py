#!/usr/bin/env python3
"""
scripts/test_agent.py
Test the agent locally without WhatsApp.
"""
import sys
import os

# Add project root to path so 'agent' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.agent import run_agent

print("Calendar Agent — local test mode")
print("Type 'quit' to exit\n")

while True:
    try:
        user_input = input("You: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not user_input:
        continue
    if user_input.lower() in ("quit", "exit"):
        break
    print("Agent:", run_agent(user_input))
    print()
