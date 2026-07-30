"""ADR-063 context compressor + process registry + session hooks."""

from __future__ import annotations

import unittest

from core.context_compressor import compress_context, prune_tool_outputs
from core.session_hooks import (
    emit_session_hook,
    list_session_hooks,
    register_session_hook,
    reset_session_hooks_for_tests,
)
from tools.process_registry import ProcessRegistry


class ContextCompressorTest(unittest.TestCase):
    def test_prune_and_compress(self):
        msgs = [{"role": "tool", "content": "x" * 2000}]
        pruned = prune_tool_outputs(msgs, max_tool_chars=100)
        self.assertIn("[pruned]", pruned[0]["content"])

        hist = []
        for i in range(20):
            hist.append({"role": "user", "content": f"question {i} about topic"})
            hist.append({"role": "assistant", "content": f"answer {i} detailed response"})
        out, meta = compress_context(hist, keep_last=4, context_size=400, max_tokens=50)
        self.assertTrue(meta["mode"] in ("extractive", "llm"))
        self.assertLess(len(out), len(hist))


class SessionHooksTest(unittest.TestCase):
    def test_emit(self):
        reset_session_hooks_for_tests()
        seen = []

        def _h(payload):
            seen.append(payload.get("event"))

        register_session_hook("session_start", "t", _h)
        emit_session_hook("session_start", {"session_id": "x"})
        self.assertEqual(seen, ["session_start"])
        self.assertIn("t", list_session_hooks()["session_start"])


class ProcessRegistryTest(unittest.TestCase):
    def test_spawn_poll(self):
        from tools.process_registry import ProcessRegistry

        reg = ProcessRegistry(backend_name="fake")
        out = reg.spawn("printf hello")
        self.assertTrue(out["ok"], out)
        info = reg.poll(out["id"])
        self.assertEqual(info.get("status"), "exited")
        self.assertIn("fake", info.get("output_tail") or "")


if __name__ == "__main__":
    unittest.main()
