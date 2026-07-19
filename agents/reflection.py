"""
agents/reflection.py
Reflection / Self-Improvement Agent.

Reviews recent session episodes and tool/code outcomes, extracts patterns
(recurring failures, repeated corrections, weak spots), and writes durable
"lessons learned" into a dedicated reflections log. Optionally promotes
high-confidence lessons into semantic memory so future sessions benefit.

Does NOT modify code automatically — it surfaces actionable findings for
the user (or a future automation) to act on. Safer default for a system
that touches real files/tools.
"""
import os, sys, json, time
sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete

from prompts.system import SYSTEM_PROMPT

R="\033[0m"; GO="\033[33m"; GR="\033[92m"; BL="\033[94m"
CY="\033[96m"; GY="\033[90m"; YL="\033[93m"; RE="\033[91m"

BASE = os.path.expanduser("~/offline_ai")
REFLECTIONS_PATH = f"{BASE}/data/reflections.json"

REFLECT_PROMPT = """You are reviewing recent AI assistant session history to improve future performance.

Recent episodes/interactions:
{episodes}

Recent tool/code failures observed:
{failures}

Based on this, identify:
1. PATTERN: any recurring mistake, weak spot, or repeated failure (1-2 sentences). If none, say "No clear pattern."
2. LESSON: one concrete, actionable rule to follow going forward to avoid this (1 sentence). If no pattern, say "None."
3. CONFIDENCE: high | medium | low — how confident you are this is a real, recurring pattern (not a one-off).

Respond in this exact format:
PATTERN: <text>
LESSON: <text>
CONFIDENCE: <high|medium|low>"""


def _load_reflections():
    if not os.path.exists(REFLECTIONS_PATH):
        return []
    try:
        with open(REFLECTIONS_PATH) as f:
            return json.load(f)
    except Exception:
        return []


def _save_reflections(data):
    os.makedirs(os.path.dirname(REFLECTIONS_PATH), exist_ok=True)
    with open(REFLECTIONS_PATH, "w") as f:
        json.dump(data, f, indent=2)


class ReflectionAgent:
    def __init__(self, engine):
        self.engine = engine

    def _gather_episodes(self, n=5):
        """Pull recent episode summaries if episodic memory is available."""
        try:
            from memory.episodic import get_recent_episodes
            eps = get_recent_episodes(n)
            if not eps:
                return "No recent episodes recorded."
            lines = []
            for ep in eps:
                summary = ep.get("summary", "")[:200]
                tags = ", ".join(ep.get("tags", [])) if ep.get("tags") else ""
                lines.append(f"- #{ep.get('id','?')} ({ep.get('time','')}): {summary} [{tags}]")
            return "\n".join(lines)
        except Exception as e:
            return f"[episodic memory unavailable: {e}]"

    def _gather_failures(self, n=10):
        """Scan generated_code/ dirs for FAIL markers left by CodeAgent runs, if any log exists."""
        failures = []
        gen_dir = f"{BASE}/generated_code"
        if os.path.isdir(gen_dir):
            for root, _, files in os.walk(gen_dir):
                for fn in files:
                    if fn.endswith(".py") or fn.endswith(".sh"):
                        continue  # code itself isn't a failure signal on its own
        # Fallback: no structured failure log exists yet — return honest note.
        if not failures:
            return "No structured failure log available yet (CodeAgent/ReactAgent do not currently persist failure history to disk)."
        return "\n".join(failures[:n])

    def run(self, stream=True):
        if stream:
            print(f"\n  {YL}🪞 Reflection Agent{R}\n  {GY}Reviewing recent session history...{R}\n")

        episodes_str = self._gather_episodes()
        failures_str = self._gather_failures()

        if stream:
            print(f"  {GY}Episodes gathered.{R}")

        prompt = REFLECT_PROMPT.format(episodes=episodes_str, failures=failures_str)
        analysis = generate_complete(self.engine, 
            user_message=prompt, system=SYSTEM_PROMPT, history=[], stream=False,
        )

        pattern = self._extract(analysis, "PATTERN")
        lesson = self._extract(analysis, "LESSON")
        confidence = self._extract(analysis, "CONFIDENCE").lower()

        entry = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pattern": pattern,
            "lesson": lesson,
            "confidence": confidence,
        }

        reflections = _load_reflections()
        valid_confidence = confidence in ("high", "medium", "low")
        is_real = (
            pattern and "no clear pattern" not in pattern.lower()
            and lesson and lesson.lower() not in ("none", "")
            and valid_confidence
        )
        if is_real:
            reflections.append(entry)
            _save_reflections(reflections)

            # Promote high-confidence lessons into semantic memory, if available
            if confidence == "high":
                try:
                    from memory.semantic import add_fact
                    add_fact("lessons_learned", lesson[:60], lesson)
                except Exception:
                    pass

        if stream:
            print(f"  {GR}✓ Reflection complete{R}")
            print(f"  {BL}Pattern:{R} {pattern}")
            print(f"  {BL}Lesson:{R} {lesson}")
            print(f"  {BL}Confidence:{R} {confidence}")
            if is_real:
                print(f"  {GY}Saved to reflections.json{'  + promoted to semantic memory' if confidence=='high' else ''}{R}\n")
            else:
                print(f"  {GY}No actionable pattern found — nothing saved.{R}\n")

        return entry

    def _extract(self, text, label):
        import re
        m = re.search(rf'{label}:\s*(.+?)(?=\n[A-Z]+:|$)', text, re.IGNORECASE | re.DOTALL)
        return m.group(1).strip() if m else ""

    def history(self, n=10):
        """Return recent saved reflections."""
        return _load_reflections()[-n:]