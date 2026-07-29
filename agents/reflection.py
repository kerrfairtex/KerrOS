"""
agents/reflection.py
Reflection / Self-Improvement Agent (P6 seed).

Reviews recent session episodes and decision-log failures, extracts patterns
(recurring failures, repeated corrections, weak spots), and writes durable
"lessons learned" into reflections.json. High-confidence lessons promote into
semantic memory (category lessons_learned) so future sessions benefit.

Does NOT rewrite code automatically — it surfaces actionable findings for
the user (or a future automation) to act on.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

sys.path.insert(0, os.path.expanduser("~/offline_ai"))
from core.complete import generate_complete

from prompts.system import SYSTEM_PROMPT

R = "\033[0m"
GO = "\033[33m"
GR = "\033[92m"
BL = "\033[94m"
CY = "\033[96m"
GY = "\033[90m"
YL = "\033[93m"
RE = "\033[91m"

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


def reflections_path() -> str:
    return os.environ.get("KERROS_REFLECTIONS_PATH") or REFLECTIONS_PATH


def _load_reflections() -> list[dict[str, Any]]:
    path = reflections_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_reflections(data: list[dict[str, Any]]) -> None:
    path = reflections_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _extract(text: str, label: str) -> str:
    m = re.search(
        rf"{label}:\s*(.+?)(?=\n[A-Z]+:|$)",
        text or "",
        re.IGNORECASE | re.DOTALL,
    )
    return m.group(1).strip() if m else ""


def _is_actionable(pattern: str, lesson: str, confidence: str) -> bool:
    if confidence not in ("high", "medium", "low"):
        return False
    if not pattern or "no clear pattern" in pattern.lower():
        return False
    if not lesson or lesson.lower() in ("none", "n/a", "na"):
        return False
    return True


def promote_lesson(lesson: str) -> bool:
    """Store a high-confidence lesson in semantic memory. Returns True on success."""
    try:
        from memory.semantic import store

        key = (lesson[:60] or "lesson").strip()
        store(key, lesson, category="lessons_learned")
        return True
    except Exception:
        return False


class ReflectionAgent:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def _gather_episodes(self, n: int = 5) -> str:
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
                lines.append(
                    f"- #{ep.get('id', '?')} ({ep.get('time', '')}): {summary} [{tags}]"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"[episodic memory unavailable: {e}]"

    def _gather_failures(self, n: int = 10) -> str:
        """Collect recent deny/fail outcomes from the decision log (KOS-008)."""
        failures: list[str] = []
        try:
            from kernel.decision_log import get_decision_log

            log = get_decision_log()
            for rec in log.read_recent(limit=max(n * 3, 30)):
                outcome = (rec.outcome or "").lower()
                dtype = (rec.decision_type or "").lower()
                if outcome in ("deny", "denied", "fail", "failed", "error", "blocked"):
                    failures.append(
                        f"- [{rec.timestamp:.0f}] {rec.actor}/{rec.decision_type}: "
                        f"{rec.input_summary[:120]} → {rec.outcome}"
                        + (f" ({rec.reason[:80]})" if rec.reason else "")
                    )
                elif "fail" in dtype or "error" in dtype:
                    failures.append(
                        f"- [{rec.timestamp:.0f}] {rec.actor}/{rec.decision_type}: "
                        f"{rec.input_summary[:120]} → {rec.outcome}"
                    )
                if len(failures) >= n:
                    break
        except Exception as e:
            return f"[decision log unavailable: {e}]"

        if not failures:
            return (
                "No recent deny/fail decisions in the audit log "
                "(scope_gate / deploy / verification)."
            )
        return "\n".join(failures[:n])

    def run(self, stream: bool = True) -> dict[str, Any]:
        if stream:
            print(
                f"\n  {YL}🪞 Reflection Agent{R}\n"
                f"  {GY}Reviewing recent session history...{R}\n"
            )

        episodes_str = self._gather_episodes()
        failures_str = self._gather_failures()

        if stream:
            print(f"  {GY}Episodes gathered.{R}")

        prompt = REFLECT_PROMPT.format(
            episodes=episodes_str, failures=failures_str
        )
        analysis = generate_complete(
            self.engine,
            user_message=prompt,
            system=SYSTEM_PROMPT,
            history=[],
            stream=False,
        )

        pattern = _extract(analysis, "PATTERN")
        lesson = _extract(analysis, "LESSON")
        confidence = _extract(analysis, "CONFIDENCE").lower().strip()

        entry: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "pattern": pattern,
            "lesson": lesson,
            "confidence": confidence,
            "saved": False,
            "promoted": False,
        }

        is_real = _is_actionable(pattern, lesson, confidence)
        if is_real:
            reflections = _load_reflections()
            reflections.append(
                {
                    "timestamp": entry["timestamp"],
                    "pattern": pattern,
                    "lesson": lesson,
                    "confidence": confidence,
                }
            )
            _save_reflections(reflections)
            entry["saved"] = True

            if confidence == "high":
                entry["promoted"] = promote_lesson(lesson)

        if stream:
            print(f"  {GR}✓ Reflection complete{R}")
            print(f"  {BL}Pattern:{R} {pattern}")
            print(f"  {BL}Lesson:{R} {lesson}")
            print(f"  {BL}Confidence:{R} {confidence}")
            if entry["saved"]:
                promo = "  + promoted to semantic memory" if entry["promoted"] else ""
                print(f"  {GY}Saved to reflections.json{promo}{R}\n")
            else:
                print(f"  {GY}No actionable pattern found — nothing saved.{R}\n")

        return entry

    def history(self, n: int = 10) -> list[dict[str, Any]]:
        """Return recent saved reflections."""
        return _load_reflections()[-n:]
