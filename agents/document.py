"""
agents/document.py
Document Agent — generates long-form documents (research papers, reports,
technical outlines) section-by-section rather than in one generation call.

Small offline models can't reliably write a full multi-page document in one
shot or via continuation (loses coherence, repeats itself). Splitting into
independent, narrowly-scoped section prompts sidesteps that entirely: each
section is short enough to complete cleanly, and sections are stitched
together at the end into one final document.
"""
import os, sys, time, re
sys.path.insert(0, os.path.expanduser("~/offline_ai"))

from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"
CY="\033[96m"; GY="\033[90m"; YL="\033[93m"; RE="\033[91m"

BASE = os.path.expanduser("~/offline_ai")
OUTPUT_DIR = f"{BASE}/generated_docs"

# Default section templates for common document types
CAPSTONE_SECTIONS = [
    "Title Page (title, proposed by, institution, date)",
    "Abstract (150-250 word summary of the whole project)",
    "Chapter 1: Introduction (background, problem statement, objectives, scope and limitations, significance of the study)",
    "Chapter 2: Review of Related Literature (relevant existing systems, technologies, and research, synthesized narratively)",
    "Chapter 3: Methodology (research design, development methodology e.g. Agile/Waterfall, data gathering, tools and technologies)",
    "Chapter 4: System Design (system architecture, use case diagram description, database design overview)",
    "Chapter 5: Expected Results and Discussion (anticipated outcomes, evaluation criteria)",
    "Chapter 6: Conclusion and Recommendations",
    "References (APA 7th edition format, at least 5 plausible academic-style references)",
]

REPORT_SECTIONS = [
    "Executive Summary",
    "Introduction and Background",
    "Analysis / Findings",
    "Recommendations",
    "Conclusion",
]

SECTION_PROMPT = """You are writing ONE section of a larger document. Write ONLY this section,
fully and completely. Do not write other sections. Do not repeat the section title of previous
sections. Do not add meta-commentary about what you're doing.

Document topic: {topic}

Section to write now: {section}

Write the complete, detailed content for this section only:"""


class DocumentAgent:
    def __init__(self, engine):
        self.engine = engine

    def _pick_template(self, topic):
        t = topic.lower()
        if any(k in t for k in ["capstone", "thesis", "research paper", "chapter"]):
            return CAPSTONE_SECTIONS
        return REPORT_SECTIONS

    def run(self, topic, sections=None, stream=True, save=True):
        sections = sections or self._pick_template(topic)

        if stream:
            print(f"\n  {YL}📄 Document Agent{R}")
            print(f"  {GY}Topic: {topic}{R}")
            print(f"  {GY}{len(sections)} section(s) to generate{R}\n")

        full_doc = []
        for i, section in enumerate(sections, 1):
            if stream:
                print(f"  {GO}⚔ Section {i}/{len(sections)}:{R} {section[:60]}")

            prompt = SECTION_PROMPT.format(topic=topic, section=section)
            content = self.engine.generate(
                user_message=prompt,
                system=SYSTEM_PROMPT,
                history=[],
                stream=False,
            )
            content = (content or "").strip()

            section_title = section.split("(")[0].strip()
            full_doc.append(f"## {section_title}\n\n{content}\n")

            if stream:
                preview = content[:100].replace("\n", " ")
                print(f"    {GY}{preview}...{R}\n")

        document = f"# {topic}\n\n" + "\n".join(full_doc)

        saved_path = None
        if save:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            fname = re.sub(r'[^\w\-]', '_', topic.lower())[:50] + f"_{time.strftime('%Y%m%d_%H%M%S')}.md"
            saved_path = os.path.join(OUTPUT_DIR, fname)
            with open(saved_path, "w") as f:
                f.write(document)

        if stream:
            print(f"  {GR}✓ Document complete{R} ({len(sections)} sections, {len(document)} chars)")
            if saved_path:
                print(f"  {GY}Saved to: {saved_path}{R}\n")

        return document, saved_path
