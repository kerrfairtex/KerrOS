import json, os, datetime

BASE = os.path.expanduser("~/offline_ai")
MEM = f"{BASE}/data/memory.json"
PROFILE = f"{BASE}/data/profile.json"
_short = []

def init_session():
    """Call on startup to reset in-memory session. Does not wipe memory.json."""
    global _short
    _short = []
    try:
        from memory.session_store import start_session
        from core.session_hooks import emit_session_hook

        sid = start_session()
        emit_session_hook("session_start", {"session_id": sid})
    except Exception:
        pass

def _load(p, d):
    if not os.path.exists(p): return d
    with open(p) as f: return json.load(f)

def _save(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f: json.dump(d, f, indent=2)

def _sanitize(text):
    import re
    # Strip ALL escape sequences (ANSI + terminal control codes)
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    # Strip ChatML tokens
    for tok in ["<|im_start|>","<|im_end|>","<|endoftext|>"]:
        text = text.replace(tok, "")
    # Reject anything that looks like tool output or context injection
    bad = [
        "example usage","llama-simple","llama.cpp/build",
        "-c 2048","-o 100000","[Online error","Assistant: ",
        "[Domain:","[Tool output]","Analyze the tool output",
        "Now give your final","[Your reasoning",
        "PING ","bytes of data","icmp_seq","rtt min",
        "nmap scan","port scan","packets transmitted",
        "User: ","user\n","assistant\n",
    ]
    for b in bad:
        if b in text: return None
    # Reject if too long (likely a prompt leak)
    if len(text) > 1000: return None
    return text.strip()

def add_message(role, content):
    global _short
    content = _sanitize(content)
    if not content or len(content) < 3: return
    # Deduplicate — skip if last entry is identical
    if _short and _short[-1]["role"] == role and _short[-1]["content"] == content:
        return
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = {"role": role, "content": content, "time": ts}
    _short.append(entry)
    hist = _load(MEM, [])
    # Deduplicate persistent history too
    if hist and hist[-1].get("role") == role and hist[-1].get("content") == content:
        return
    hist.append(entry)
    _save(MEM, hist[-50:])
    try:
        from memory.session_fts import index_message

        index_message(role, content, ts=ts, source="live")
    except Exception:
        pass
    try:
        from memory.session_store import index_turn

        index_turn(role, content, ts=ts, source="live")
    except Exception:
        pass
    if len(_short) >= 15:
        _compress()

def _compress():
    global _short
    old, recent = _short[:-6], _short[-6:]
    summary = " | ".join([f"{m['role']}: {m['content'][:50]}" for m in old])
    _short = [{"role":"system","content":f"[Earlier]: {summary}","time":"compressed"}] + recent

def get_recent(n=12): return _short[-n:]
def get_history(n=20):
    entries = _load(MEM, [])[-n:]
    clean = []
    bad = ["example usage","llama-simple","-c 2048","[Online error",
           "User: ","Assistant: ","<|im_start|>","[Domain:","[Tool output]",
           "Analyze the tool output","now give your final"]
    for e in entries:
        c = e.get("content","").strip()
        if not c or len(c) < 3: continue
        if any(b.lower() in c.lower() for b in bad): continue
        if e.get("role") not in ("user","assistant"): continue
        clean.append({"role":e["role"],"content":c})
    return clean
def clear_session():
    global _short
    _short = []
    print("[Memory cleared]")

def get_profile(): return _load(PROFILE, {})

def update_profile(key, value):
    p = _load(PROFILE, {})
    p[key] = value
    _save(PROFILE, p)

def extract_and_learn(text):
    # Also store in semantic memory
    try:
        from memory.semantic import extract_and_store
        learned = extract_and_store(text)
        if learned:
            print(f"  \033[92m[Memory]\033[0m Learned: {', '.join(learned)}")
    except Exception:
        pass

def extract_and_learn_legacy(text):
    lower = text.lower()
    p = _load(PROFILE, {})
    changed = False
    triggers = {
        "my name is":"user_name","call me":"user_name",
        "i am a":"user_role","i'm a":"user_role",
        "i study":"user_study","i work at":"user_company",
        "i live in":"user_location","i specialize in":"user_specialty",
        "i am learning":"user_learning","my goal is":"user_goal",
        "i use":"user_tools","i prefer":"user_preference",
    }
    for phrase, key in triggers.items():
        if phrase in lower:
            idx = lower.index(phrase) + len(phrase)
            val = text[idx:].strip().split(".")[0].split(",")[0].strip()
            if val and len(val) < 100:
                p[key] = val
                changed = True
    if changed:
        _save(PROFILE, p)
        print("[Memory] Learned from your message.")
