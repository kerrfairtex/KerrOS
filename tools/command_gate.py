"""
tools/command_gate.py
Drop-in gate: tools only fire on explicit command, never on conversational
phrasing like "can you help me with that" or "we should probably...".
"""

import re

_COMMAND_VERBS = [
    "execute", "run", "build", "create", "generate", "make",
    "clone", "scan", "analyze", "write", "save", "delete",
    "install", "download", "deploy", "mkdir", "touch",
]

_NOW_MARKERS = ["now", "please", "go ahead", "do it", "proceed"]

_SLASH_RE = re.compile(r"^\s*/\w+")
_VERB_RE = re.compile(r"\b(" + "|".join(_COMMAND_VERBS) + r")\b", re.IGNORECASE)
_LEADING_VERB_RE = re.compile(r"^\s*(" + "|".join(_COMMAND_VERBS) + r")\b", re.IGNORECASE)
_MARKER_RE = re.compile(
    r"\b(" + "|".join(m.replace(" ", r"\s+") for m in _NOW_MARKERS) + r")\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"\b(can you|could you|should we|do you think|what if|maybe|"
    r"i think|let'?s consider|would it be)\b",
    re.IGNORECASE,
)


def is_explicit_command(text: str) -> bool:
    if not text or not text.strip():
        return False
    if _SLASH_RE.match(text):
        return True
    if _HEDGE_RE.search(text) is not None:
        return False
    if _LEADING_VERB_RE.match(text):
        return True
    has_verb = _VERB_RE.search(text) is not None
    has_marker = _MARKER_RE.search(text) is not None
    return has_verb and has_marker


if __name__ == "__main__":
    tests = [
        ("can you help me with that?", False),
        ("we should probably clone the repo", False),
        ("build the folder now", True),
        ("/clone https://github.com/x/y", True),
        ("create now: TOWELCO web app scaffold", True),
        ("do you think we should scan this site?", False),
        ("go ahead and generate the config", True),
        ("I think the official site is good, replicate it", False),
        ("run backup.sh", True),
        ("execute deploy.py", True),
        ("we could run backup.sh sometime", False),
    ]
    for msg, expected in tests:
        result = is_explicit_command(msg)
        status = "OK" if result == expected else "FAIL"
        print(f"[{status}] {result!s:5} <- {msg!r}")
