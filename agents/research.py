"""
agents/research.py
Research Agent — breaks a broad question into sub-queries, searches
the knowledge base for each, synthesizes a combined answer.
"""
import os, sys
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete
from rag.store import search
from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; CY="\033[96m"; GY="\033[90m"; YL="\033[93m"

DECOMPOSE_PROMPT = (
    "Break this research question into 2-4 short, specific search queries "
    "(one per line, no numbering, no explanation) that would together answer it.\n\n"
    "Question: {question}"
)

SYNTH_PROMPT = (
    "Synthesize a clear answer to the research question using ONLY the knowledge below. "
    "Note any gaps if the knowledge is incomplete.\n\n"
    "Question: {question}\n\n{knowledge}"
)

class ResearchAgent:
    def __init__(self, engine):
        self.engine = engine

    def run(self, question, stream=True):
        if stream:
            print(f"\n  {YL}🔎 Research Agent{R}\n  {GY}Question: {question}{R}\n")

        decompose_out = generate_complete(self.engine, 
            user_message=DECOMPOSE_PROMPT.format(question=question),
            system=SYSTEM_PROMPT, history=[], stream=False,
        )
        sub_queries = [q.strip("-• ").strip() for q in decompose_out.split("\n") if q.strip()][:4]
        if not sub_queries:
            sub_queries = [question]

        if stream:
            print(f"  {GO}Sub-queries:{R}")
            for q in sub_queries: print(f"    • {q}")
            print()

        all_chunks = []
        seen = set()
        for q in sub_queries:
            hits = search(q, top_k=3)
            for _, text, src in hits:
                key = text[:50]
                if key not in seen:
                    all_chunks.append(f"[{src}] {text[:300]}")
                    seen.add(key)

        knowledge = "[Relevant knowledge]:\n" + "\n".join(all_chunks) if all_chunks else "No matching knowledge found."

        if stream:
            print(f"  {GY}{len(all_chunks)} unique knowledge chunk(s) gathered. Synthesizing...{R}\n")

        answer = generate_complete(self.engine, 
            user_message=SYNTH_PROMPT.format(question=question, knowledge=knowledge),
            system=SYSTEM_PROMPT, history=[], stream=False,
        )

        if stream:
            print(f"  {GR}✓ Synthesis:{R}\n  {CY}{answer}{R}\n")
        return answer