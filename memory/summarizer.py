"""
memory/summarizer.py
====================
Summarizes a conversation session into episodic memory.
Called on /clear or session end.
"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

from memory.episodic import save_session
from memory.manager import get_history

def summarize_session(engine, messages=None):
    """
    Use the AI to summarize the current session.
    Stores result in episodic memory.
    """
    if messages is None:
        messages = get_history(20)

    if not messages or len(messages) < 2:
        return None

    # Build conversation text
    convo = ""
    for m in messages:
        role = "User" if m["role"] == "user" else "KerrOS"
        convo += f"{role}: {m['content'][:200]}\n"

    prompt = f"""Summarize this conversation in 2-3 sentences.
Focus on: what was discussed, what tools were used, what was found.
Be specific and factual.

Conversation:
{convo[:1500]}

Summary:"""

    summary = engine.generate(
        user_message=prompt,
        system="You are a concise summarizer. Output only the summary, nothing else.",
        history=[],
        stream=False,
    )

    # Extract tags
    tags = []
    keywords = ["nmap","ping","osint","scan","exploit","network",
                "web","forensic","mikrotik","esp32","groq","react"]
    for kw in keywords:
        if kw in convo.lower():
            tags.append(kw)

    summary = (summary or "").strip()
    if len(summary) < 10:
        return None

    ep_id = save_session(summary, tags)
    return ep_id, summary
