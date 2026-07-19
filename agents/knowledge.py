"""
agents/knowledge.py
====================
Knowledge Agent — RAG-grounded Q&A with tool execution fallback.
Answers from the local knowledge base (CVE/CWE/CAPEC/MITRE/OWASP/NIST/Sigma/YARA/CISA)
first; falls back to live tool execution (nmap/whois/dig/etc.) when the question
needs real-time/live data the knowledge base can't provide.
"""

import re, os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete

from rag.store import search_exact_id, search_by_category, search_multi_category, search
from tools.router import detect_tool, run_tool
from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"
CY="\033[96m"; GY="\033[90m"; YL="\033[93m"; RE="\033[91m"

MULTI_RULES = [
    (["secure coding", "vulnerable code", "code review security", "insecure code"], ["cwe", "owasp"]),
    (["threat actor", "apt group", "adversary technique"], ["mitre", "capec"]),
    (["defensive detection", "detection rule", "log detection"], ["sigma", "yara"]),
    (["exploit chain", "attack pattern"], ["capec", "cwe"]),
    (["actively exploited", "exploited in the wild"], ["cisa", "cve"]),
]

# Signals that the question needs LIVE data, not static knowledge
LIVE_SIGNALS = [
    (["scan", "port scan", "nmap"],              "nmap",  r'([\d\.]+|[\w\-]+\.[\w\.]+)'),
    (["ping", "reachable", "is up", "latency"],  "ping",  r'([\w\.\-]+\.[a-z]{2,})'),
    (["whois", "who owns", "registrar"],         "whois", r'([\w\-]+\.[\w\.]+)'),
    (["dns records", "resolve", "dig "],         "dig",   r'([\w\-]+\.[\w\.]+)'),
    (["headers of", "http headers"],             "headers", r'(https?://[\w\.\-/]+|[\w\-]+\.[\w\.]+)'),
    (["current ip", "my ip", "geoip"],           "geoip", r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'),
]


class KnowledgeAgent:
    def __init__(self, engine):
        self.engine = engine

    def _route_category(self, query):
        u = query.lower()
        for keywords, cats in MULTI_RULES:
            if any(k in u for k in keywords):
                return None, cats
        if re.search(r'cve-\d{4}-\d+', u): return "cve", None
        if re.search(r'cwe-\d+', u): return "cwe", None
        if "capec" in u: return "capec", None
        if re.search(r'\bt1\d{3}\b', u) or "att&ck" in u or "mitre" in u: return "mitre", None
        if "owasp" in u or "cheat sheet" in u: return "owasp", None
        if "nist" in u or "sp 800" in u: return "nist", None
        if "sigma rule" in u or "sigma" in u: return "sigma", None
        if "yara" in u: return "yara", None
        if "kev" in u or "known exploited" in u: return "cisa", None
        return None, None

    def _detect_live_need(self, query):
        """Return (tool, target) if the query needs live/real-time tool execution."""
        lower = query.lower()
        for keywords, tool, pattern in LIVE_SIGNALS:
            if any(k in lower for k in keywords):
                target = ""
                if pattern:
                    m = re.search(pattern, query)
                    target = m.group(1) if m else ""
                return tool, target
        return None, None

    def _kb_search(self, query):
        """Search local knowledge base using exact-id -> multi-cat -> single-cat -> general fallback chain."""
        exact = search_exact_id(query)
        if exact:
            return exact, "exact-id"

        cat, multi_cats = self._route_category(query)
        if multi_cats:
            hits = search_multi_category(query, multi_cats, top_k=4)
            if hits:
                return hits, f"multi:{'+'.join(multi_cats)}"

        if cat:
            hits = search_by_category(query, category=cat, top_k=4)
            if hits:
                return hits, f"category:{cat}"

        hits = search(query, top_k=4)
        return hits, "general"

    def run(self, query, stream=True):
        if stream:
            print(f"\n  {YL}📚 Knowledge Agent{R}")
            print(f"  {GY}Query: {query}{R}\n")

        # 1. Check if this needs LIVE data (tool execution) rather than static knowledge
        live_tool, live_target = self._detect_live_need(query)
        tool_output = None
        if live_tool:
            if stream:
                print(f"  {GO}⚔ Live data needed → {live_tool} {live_target}{R}")
            tool_output = run_tool(live_tool, live_target)
            if stream:
                preview = tool_output[:150].replace("\n", " ")
                print(f"  {BL}Result:{R} {preview}...\n")

        # 2. Search knowledge base regardless (may supplement live data)
        hits, route = self._kb_search(query)
        if stream:
            print(f"  {GY}KB route: {route} | {len(hits)} hit(s){R}\n")

        kb_context = ""
        if hits:
            chunks = [f"[{src}] {text[:300]}" for _, text, src in hits]
            kb_context = "\n[Relevant knowledge]:\n" + "\n".join(chunks) + "\n"

        # 3. Build grounded prompt
        tool_context = f"\n[Live tool output — {live_tool}]:\n{tool_output[:600]}\n" if tool_output else ""

        if not kb_context and not tool_context:
            final_prompt = (
                f"{query}\n\n"
                f"Note: no matching entries were found in the local knowledge base "
                f"for this query. Answer from general expertise, and say clearly "
                f"that this wasn't found in the local knowledge base."
            )
        else:
            final_prompt = f"{kb_context}{tool_context}\nQuestion: {query}"

        if stream:
            print(f"  {GY}Generating grounded answer...{R}\n")

        answer = generate_complete(self.engine, 
            user_message=final_prompt,
            system=SYSTEM_PROMPT,
            history=[],
            stream=False,
        )

        if stream:
            print(f"  {GR}✓ Answer:{R}")
            print(f"  {CY}{answer}{R}\n")

        return answer