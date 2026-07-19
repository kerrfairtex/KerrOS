"""
memory/episodic.py
==================
Episodic memory — stores session summaries.
Each session gets summarized and stored permanently.
Allows KerrOS to remember what happened in past sessions.
"""
import json, os, datetime

BASE = os.path.expanduser("~/offline_ai")
EPISODIC_PATH = f"{BASE}/data/episodic.json"

def _load():
    if not os.path.exists(EPISODIC_PATH): return []
    with open(EPISODIC_PATH) as f: return json.load(f)

def _save(data):
    os.makedirs(os.path.dirname(EPISODIC_PATH), exist_ok=True)
    with open(EPISODIC_PATH, "w") as f: json.dump(data, f, indent=2)

def save_session(summary: str, tags: list = None):
    """Save a session summary to episodic memory."""
    episodes = _load()
    episode = {
        "id": len(episodes) + 1,
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "tags": tags or [],
    }
    episodes.append(episode)
    _save(episodes[-50:])  # keep last 50 sessions
    return episode["id"]

def get_recent_episodes(n=5):
    """Get last N session summaries."""
    return _load()[-n:]

def search_episodes(keyword):
    """Search episodes by keyword."""
    keyword = keyword.lower()
    return [e for e in _load() if keyword in e["summary"].lower()
            or any(keyword in t.lower() for t in e.get("tags",[]))]

def get_all_episodes():
    return _load()
