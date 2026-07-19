COMPLEX = ["how do","explain","analyze","compare","difference","step by step","vulnerability","exploit","forensic","incident","recommend","investigate","why does","attack","pentest"]

def needs_thinking(text):
    lower = text.lower()
    return any(t in lower for t in COMPLEX) or len(text) > 80
