COMPLEX = ["how do","explain","analyze","compare","difference","step by step","vulnerability","exploit","forensic","incident","recommend","investigate","why does","attack","pentest"]

def needs_thinking(text):
    # Check config flag first — if thinking_mode is disabled in config, skip entirely
    try:
        from core.config import cfg
        if not cfg().get("thinking_mode", True):
            return False
    except Exception:
        pass
    lower = text.lower()
    return any(t in lower for t in COMPLEX) or len(text) > 80
