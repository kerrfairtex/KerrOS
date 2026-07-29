"""
memory/semantic.py
==================
Semantic memory — stores facts KerrOS learns about you,
your environment, and topics you've discussed.
Persists across all sessions.
"""
import json, os, datetime, re

BASE = os.path.expanduser("~/offline_ai")
SEMANTIC_PATH = f"{BASE}/data/semantic.json"

def _semantic_path() -> str:
    return os.environ.get("KERROS_SEMANTIC_PATH") or SEMANTIC_PATH

def _load():
    path = _semantic_path()
    if not os.path.exists(path): return {}
    with open(path) as f: return json.load(f)

def _save(data):
    path = _semantic_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f: json.dump(data, f, indent=2)

def store(key: str, value: str, category: str = "general"):
    """Store a semantic fact."""
    data = _load()
    if category not in data: data[category] = {}
    data[category][key] = {
        "value": value,
        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    _save(data)

def get(key: str, category: str = "general"):
    """Retrieve a fact."""
    data = _load()
    return data.get(category, {}).get(key, {}).get("value")

def get_category(category: str):
    """Get all facts in a category."""
    return _load().get(category, {})

def get_all():
    return _load()

def extract_and_store(text: str):
    """Auto-extract facts from user messages."""
    lower = text.lower()
    learned = []

    patterns = {
        # Identity
        "user": {
            "my name is":     "name",
            "call me":        "name",
            "i am ":          "role",
            "i'm a ":         "role",
            "i work at ":     "company",
            "i study at ":    "school",
            "i live in ":     "location",
            "i'm from ":      "origin",
            "i'm studying ":  "study",
        },
        # Technical
        "tech": {
            "i use ":         "tools",
            "i prefer ":      "preference",
            "i specialize in":"specialty",
            "my setup is ":   "setup",
            "i'm learning ":  "learning",
            "my goal is ":    "goal",
            "i'm working on ":"project",
        },
        # Network/Security
        "network": {
            "my ip is ":      "ip",
            "my router is ":  "router",
            "my network is ": "network",
            "my ssid is ":    "ssid",
        }
    }

    data = _load()
    for category, triggers in patterns.items():
        for phrase, key in triggers.items():
            if phrase in lower:
                idx = lower.index(phrase) + len(phrase)
                val = text[idx:].strip().split(".")[0].split(",")[0].strip()
                # Clean: stop at first conjunction/preposition
                import re
                val = re.split(r'\b(and|or|but|at|in|from|with|for)\b', val)[0].strip()
                if val and 2 < len(val) < 60:
                    if category not in data: data[category] = {}
                    data[category][key] = {
                        "value": val,
                        "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    learned.append(f"{category}.{key} = {val}")

    if learned:
        _save(data)
        return learned
    return []

def build_context_string():
    """Build a short context string for injection into prompts."""
    data = _load()
    parts = []

    user = data.get("user", {})
    if user.get("name"): parts.append(f"User's name: {user['name']['value']}")
    if user.get("role"): parts.append(f"User's role: {user['role']['value']}")
    if user.get("school"): parts.append(f"User studies at: {user['school']['value']}")
    if user.get("specialty"): parts.append(f"Specialty: {user['specialty']['value']}")

    tech = data.get("tech", {})
    if tech.get("project"): parts.append(f"Current project: {tech['project']['value']}")
    if tech.get("learning"): parts.append(f"Learning: {tech['learning']['value']}")
    if tech.get("goal"): parts.append(f"Goal: {tech['goal']['value']}")

    # P6: high-confidence Reflection Agent lessons (category lessons_learned).
    lessons = data.get("lessons_learned") or {}
    if lessons:
        # Prefer most recently updated entries.
        ranked = sorted(
            lessons.items(),
            key=lambda kv: kv[1].get("updated", ""),
            reverse=True,
        )
        for _, meta in ranked[:3]:
            value = (meta or {}).get("value") or ""
            if value:
                parts.append(f"Lesson learned: {value}")

    return "\n".join(parts) if parts else ""
