import os, json
from memory.manager import get_recent, get_profile
from rag.store import search
from prompts.system import SYSTEM_PROMPT
from core.config import cfg

def _tokens(t): return len(t) // 4

def build(user_input, tool_result=None, domain=None):
    c = cfg()
    budget = c["context_size"] - c["max_tokens"] - 200
    profile = get_profile()
    profile_str = ""
    if profile:
        parts = [f"{k}: {v}" for k,v in profile.items() if not k.startswith("last_")]
        if parts: profile_str = "\n[User]: " + " | ".join(parts)
    system = SYSTEM_PROMPT + profile_str + "\n"
    rag_str = ""
    hits = search(user_input, top_k=2)
    if hits:
        rag_str = "\n[Knowledge]:\n" + "\n".join([f"• {t[:200]}" for _,t,_ in hits]) + "\n"
    tool_str = f"\n[Tool output]:\n{str(tool_result)[:800]}\n" if tool_result else ""
    domain_str = f"\n[Domain: {domain}]\n" if domain else ""
    from memory.manager import get_history
    history = get_history(n=6)
    history_str = ""
    bad = ["[Domain:","[Tool output]","Analyze the tool","<|im_start|>",
           "User: ","Assistant: ","PING ","bytes from","icmp_seq"]
    for m in history:
        c = m.get("content","").strip()
        if not c or len(c) < 3 or len(c) > 500: continue
        if any(b in c for b in bad): continue
        label = "User" if m["role"]=="user" else "Assistant"
        line = f"{label}: {c}\n"
        if _tokens(system+rag_str+tool_str+domain_str+history_str+line) < budget:
            history_str += line
    return (f"{system}{domain_str}{rag_str}{tool_str}\n"
            f"{history_str}User: {user_input}\nAssistant:")

def build_chat(user_input, tool_result=None, domain=None):
    """Returns (system_prompt, user_prompt) tuple for chat template"""
    from prompts.system import SYSTEM_PROMPT
    c = cfg()
    profile = get_profile()
    profile_str = ""
    if profile:
        parts = [f"{k}: {v}" for k,v in profile.items() if not k.startswith("last_")]
        if parts: profile_str = "\n[User]: " + " | ".join(parts)
    tool_str = f"\n[Tool output]:\n{str(tool_result)[:600]}\n" if tool_result else ""
    domain_str = f"\n[Domain: {domain}]\n" if domain else ""
    # Inject semantic memory context
    semantic_str = ""
    try:
        from memory.semantic import build_context_string
        sc = build_context_string()
        if sc: semantic_str = f"\n[Known about user]:\n{sc}\n"
    except Exception:
        pass

    # Inject relevant RAG knowledge (skills, docs) based on user query
    rag_str = ""
    try:
        import re as _re
        from rag.store import search_by_category, search_multi_category, search_exact_id
        u = user_input.lower()

        multi_rules = [
            (["secure coding", "vulnerable code", "code review security", "insecure code"], ["cwe", "owasp"]),
            (["threat actor", "apt group", "adversary technique"], ["mitre", "capec"]),
            (["defensive detection", "detection rule", "log detection"], ["sigma", "yara"]),
            (["exploit chain", "attack pattern"], ["capec", "cwe"]),
            (["actively exploited", "exploited in the wild"], ["cisa", "cve"]),
        ]

        cat = None
        multi_cats = None
        for keywords, cats in multi_rules:
            if any(k in u for k in keywords):
                multi_cats = cats
                break

        if not multi_cats:
            if _re.search(r'cve-\d{4}-\d+', u): cat = "cve"
            elif _re.search(r'cwe-\d+', u): cat = "cwe"
            elif "capec" in u: cat = "capec"
            elif _re.search(r'\bt1\d{3}\b', u) or "att&ck" in u or "mitre" in u: cat = "mitre"
            elif "owasp" in u or "cheat sheet" in u: cat = "owasp"
            elif "nist" in u or "sp 800" in u: cat = "nist"
            elif "sigma rule" in u or "sigma" in u: cat = "sigma"
            elif "yara" in u: cat = "yara"
            elif "kev" in u or "known exploited" in u: cat = "cisa"

        if multi_cats:
            hits = search_exact_id(user_input) or search_multi_category(user_input, multi_cats, top_k=4)
        else:
            hits = search_exact_id(user_input) or search_by_category(user_input, category=cat, top_k=4)
        if hits:
            chunks = []
            for _, text, src in hits:
                chunks.append(f"[{src}] {text[:300]}")
            rag_str = "\n[Relevant knowledge]:\n" + "\n".join(chunks) + "\n"
    except Exception:
        pass

    # Context-aware system prompt
    academic_keywords = ["chapter","thesis","research","apa","abstract",
        "introduction","literature","methodology","bibliography","citation",
        "title","conclusion","findings","objective","scope"]
    is_academic = any(k in user_input.lower() for k in academic_keywords)

    if is_academic:
        from prompts.system import SYSTEM_PROMPT as SP
        system_base = (
            "You are an expert academic writing assistant with deep knowledge of "
            "APA 7th edition formatting, research methodology, and thesis writing. "
            "You help students structure chapters, write literature reviews, "
            "format citations, and develop research papers. Be specific and detailed."
        )
    else:
        system_base = SYSTEM_PROMPT

    system = system_base + profile_str + semantic_str + rag_str
    user = f"{domain_str}{tool_str}{user_input}"
    return system, user
