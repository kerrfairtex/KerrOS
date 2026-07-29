"""P6 Reflection Agent: episode review → lesson logging → semantic promotion."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agents.reflection import (
    ReflectionAgent,
    _extract,
    _is_actionable,
    promote_lesson,
)


ANALYSIS_HIGH = """
PATTERN: Repeatedly retries deploy without arming scope_gate first.
LESSON: Always call /scope arm-deploy before any deploy tool.
CONFIDENCE: high
"""

ANALYSIS_MEDIUM = """
PATTERN: Occasional verbose answers when user asked for a short summary.
LESSON: Match answer length to the user's request.
CONFIDENCE: medium
"""

ANALYSIS_NONE = """
PATTERN: No clear pattern.
LESSON: None.
CONFIDENCE: low
"""


class ExtractParseTest(unittest.TestCase):
    def test_extract_fields(self):
        self.assertIn("scope_gate", _extract(ANALYSIS_HIGH, "PATTERN").lower())
        self.assertIn("arm-deploy", _extract(ANALYSIS_HIGH, "LESSON").lower())
        self.assertEqual(_extract(ANALYSIS_HIGH, "CONFIDENCE").lower(), "high")

    def test_is_actionable(self):
        self.assertTrue(
            _is_actionable(
                "Repeatedly fails X",
                "Do Y instead",
                "high",
            )
        )
        self.assertFalse(
            _is_actionable("No clear pattern.", "None.", "low")
        )
        self.assertFalse(_is_actionable("Something", "None", "medium"))


class ReflectionAgentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.reflections = self.root / "reflections.json"
        self.semantic = self.root / "semantic.json"
        self.episodic = self.root / "episodic.json"
        self.env = {
            "KERROS_REFLECTIONS_PATH": str(self.reflections),
            "KERROS_SEMANTIC_PATH": str(self.semantic),
            "KERROS_EPISODIC_PATH": str(self.episodic),
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_env(self):
        return patch.dict(os.environ, self.env, clear=False)

    @patch("agents.reflection.generate_complete")
    def test_high_confidence_saves_and_promotes(self, mock_gen):
        mock_gen.return_value = ANALYSIS_HIGH
        with self._patch_env():
            from memory.episodic import save_session

            save_session("Tried vercel deploy without arming", tags=["deploy"])
            agent = ReflectionAgent(engine=MagicMock())
            with patch.object(
                agent,
                "_gather_failures",
                return_value="- deploy denied: not armed",
            ):
                entry = agent.run(stream=False)

            self.assertTrue(entry["saved"])
            self.assertTrue(entry["promoted"])
            self.assertTrue(self.reflections.is_file())
            data = json.loads(self.reflections.read_text())
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["confidence"], "high")

            from memory.semantic import get_category, build_context_string

            lessons = get_category("lessons_learned")
            self.assertTrue(lessons)
            ctx = build_context_string()
            self.assertIn("Lesson learned:", ctx)
            self.assertIn("arm-deploy", ctx.lower())

    @patch("agents.reflection.generate_complete")
    def test_medium_saves_without_promote(self, mock_gen):
        mock_gen.return_value = ANALYSIS_MEDIUM
        with self._patch_env():
            agent = ReflectionAgent(engine=MagicMock())
            with patch.object(agent, "_gather_episodes", return_value="- ep"):
                with patch.object(agent, "_gather_failures", return_value="none"):
                    entry = agent.run(stream=False)
            self.assertTrue(entry["saved"])
            self.assertFalse(entry["promoted"])
            from memory.semantic import get_category

            self.assertEqual(get_category("lessons_learned"), {})

    @patch("agents.reflection.generate_complete")
    def test_no_pattern_skips_save(self, mock_gen):
        mock_gen.return_value = ANALYSIS_NONE
        with self._patch_env():
            agent = ReflectionAgent(engine=MagicMock())
            with patch.object(agent, "_gather_episodes", return_value="none"):
                with patch.object(agent, "_gather_failures", return_value="none"):
                    entry = agent.run(stream=False)
            self.assertFalse(entry["saved"])
            self.assertFalse(entry["promoted"])
            self.assertFalse(self.reflections.exists())

    def test_history_reads_saved(self):
        with self._patch_env():
            payload = [
                {
                    "timestamp": "2026-01-01 00:00:00",
                    "pattern": "p",
                    "lesson": "l",
                    "confidence": "high",
                }
            ]
            self.reflections.write_text(json.dumps(payload), encoding="utf-8")
            hist = ReflectionAgent(engine=MagicMock()).history()
            self.assertEqual(len(hist), 1)
            self.assertEqual(hist[0]["lesson"], "l")

    def test_promote_lesson_helper(self):
        with self._patch_env():
            self.assertTrue(promote_lesson("Prefer explicit /scope arm-deploy"))
            from memory.semantic import get_category

            self.assertTrue(get_category("lessons_learned"))


class SemanticLessonsTest(unittest.TestCase):
    def test_build_context_includes_lessons(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "semantic.json"
            with patch.dict(os.environ, {"KERROS_SEMANTIC_PATH": str(path)}):
                from memory import semantic

                semantic.store("rule1", "Always arm deploy first", category="lessons_learned")
                ctx = semantic.build_context_string()
                self.assertIn("Always arm deploy first", ctx)


if __name__ == "__main__":
    unittest.main()
