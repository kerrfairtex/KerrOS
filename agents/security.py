"""
agents/security.py
Security Agent — runs recon on a target, cross-references findings
against local CVE/CWE/CISA KEV knowledge, produces a risk summary.
"""
import re, os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete
from kernel.access import run_tool, memory_query, memory_search_exact_id
from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"; CY="\033[96m"; GY="\033[90m"; YL="\033[93m"

class SecurityAgent:
    def __init__(self, engine):
        self.engine = engine

    def run(self, target, stream=True):
        if stream:
            print(f"\n  {YL}🛡 Security Agent{R}\n  {GY}Target: {target}{R}\n")

        findings = []

        if stream: print(f"  {GO}⚔ nmap{R}")
        nmap_out = run_tool("nmap", target)
        findings.append(("nmap", nmap_out))

        if stream: print(f"  {GO}⚔ whois{R}")
        whois_out = run_tool("whois", target)
        findings.append(("whois", whois_out))

        if stream: print(f"  {GO}⚔ headers{R}")
        headers_out = run_tool("headers", f"https://{target}")
        findings.append(("headers", headers_out))

        # Pull any CVE/CWE mentions surfaced in tool output, cross-reference KB
        combined = "\n".join(o for _, o in findings)
        cve_ids = re.findall(r'CVE-\d{4}-\d+', combined, re.IGNORECASE)
        kb_context = ""
        for cid in set(cve_ids[:3]):
            hits = memory_search_exact_id(cid)
            if hits:
                kb_context += f"\n[{hits[0][2]}] {hits[0][1][:300]}"

        if not kb_context:
            hits = memory_query(f"{target} vulnerability risk", top_k=3)
            if hits:
                kb_context = "\n".join(f"[{s}] {t[:250]}" for _, t, s in hits)

        tool_summary = "\n\n".join(f"--- {name} ---\n{out[:500]}" for name, out in findings)
        prompt = (
            f"Target: {target}\n\n"
            f"Recon output:\n{tool_summary}\n\n"
            f"[Relevant knowledge]:\n{kb_context or 'None found'}\n\n"
            f"Produce a concise risk assessment: what's exposed, any known CVEs/weaknesses "
            f"relevant to what's found, and recommended next steps."
        )

        if stream: print(f"\n  {GY}Generating risk assessment...{R}\n")
        report = generate_complete(self.engine, user_message=prompt, system=SYSTEM_PROMPT, history=[], stream=False)

        if stream:
            print(f"  {GR}✓ Risk Assessment:{R}\n  {CY}{report}{R}\n")
        return report