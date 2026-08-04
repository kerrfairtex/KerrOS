"""ADR-106 unified multi-agent / Scout memory."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class UnifiedMemoryTest(unittest.TestCase):
    def _patch_base(self, tmp: Path):
        root = tmp / "data" / "agent_memory"
        return (
            patch("memory.unified_store.BASE", tmp),
            patch("memory.unified_store.ROOT", root),
            patch("memory.unified_store.STORES", root / "stores"),
            patch("memory.unified_store.VERSIONS", root / "versions"),
            patch("memory.unified_store.META", root / "meta.json"),
            patch("memory.unified_store.ATTACH", root / "attachments.json"),
            patch("tools.memory_graph.BASE", tmp),
            patch("tools.memory_graph.GRAPH_PATH", root / "graph.json"),
        )

    def test_seed_scout_layout_and_prefs(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us

                us._initialized = False
                out = us.ensure_defaults()
                self.assertTrue(out["ok"])
                pref = us.read("scout", "notes/user_preference.md")
                self.assertTrue(pref["exists"])
                self.assertIn("Mahesh", pref["content"])
                self.assertIn("Barili", pref["content"])
                self.assertIn("Robert@", pref["content"])
                self.assertTrue(us.read("org", "conventions.md")["exists"])
                # org is read-only
                bad = us.write("org", "conventions.md", "nope")
                self.assertFalse(bad["ok"])

    def test_optimistic_concurrency_and_versioning(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us

                us._initialized = False
                us.ensure_defaults()
                sid = "sess-a"
                us.attach(sid, "team", us.ACCESS_RW, agent="agent_a")
                r1 = us.read("team", "deploy.md")
                w1 = us.write(
                    "team",
                    "deploy.md",
                    "deploy via make\n",
                    expected_sha256=r1["sha256"],
                    session_id=sid,
                    agent="agent_a",
                    reason="user corrected on PRs",
                )
                self.assertTrue(w1["ok"])
                self.assertGreaterEqual(w1["version"], 2)  # seed was v1
                # stale sha → conflict
                conflict = us.write(
                    "team",
                    "deploy.md",
                    "ship via /deploy.sh\n",
                    expected_sha256=r1["sha256"],
                    session_id=sid,
                    agent="agent_b",
                )
                self.assertTrue(conflict.get("conflict"))
                # agent B retries with current sha
                r2 = us.read("team", "deploy.md")
                w2 = us.write(
                    "team",
                    "deploy.md",
                    r2["content"] + "reason: PR #412\n",
                    expected_sha256=r2["sha256"],
                    session_id=sid,
                    agent="agent_b",
                )
                self.assertTrue(w2["ok"])
                hist = us.history("team", "deploy.md")
                self.assertGreaterEqual(len(hist), 3)
                agents = [h.get("agent") for h in hist]
                self.assertIn("agent_a", agents)
                # rollback to agent_a revision
                v_a = next(h["version"] for h in hist if h.get("agent") == "agent_a")
                rb = us.rollback("team", "deploy.md", v_a, session_id=sid, agent="agent_c")
                self.assertTrue(rb["ok"])
                self.assertIn("deploy via make", us.read("team", "deploy.md")["content"])

    def test_shared_attach_scopes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us

                us._initialized = False
                us.bootstrap_session("A", agent="agent_a")
                us.bootstrap_session("B", agent="agent_b")
                us.write(
                    "team",
                    "flash_task.md",
                    "learned from A\n",
                    session_id="A",
                    agent="agent_a",
                )
                # B can read what A wrote (same store)
                got = us.read("team", "flash_task.md", session_id="B")
                self.assertIn("learned from A", got["content"])
                # org attach is read-only
                denied = us.write(
                    "org",
                    "security.md",
                    "hack",
                    session_id="B",
                    agent="agent_b",
                )
                self.assertFalse(denied["ok"])

    def test_export_import_and_graph(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us
                from memory import manage
                from tools.memory_graph import add_node, link, query, memory_graph

                us._initialized = False
                us.ensure_defaults()
                dest = tmp / "export_scout"
                exp = manage.export_store("scout", dest)
                self.assertTrue(exp["ok"])
                self.assertTrue((dest / "notes" / "user_preference.md").is_file())
                add_node("Robert@", kind="contact")
                link("Robert@", "high_priority", rel="priority")
                q = query("Robert")
                self.assertTrue(q["ok"])
                self.assertGreaterEqual(len(q["nodes"]), 1)
                out = json.loads(memory_graph("neighbors Robert@"))
                self.assertTrue(out["ok"])

    def test_dreaming_heuristic(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us
                from memory import dreaming

                us._initialized = False
                us.ensure_defaults()
                with patch(
                    "memory.dreaming._recent_turns",
                    return_value=[
                        {
                            "session_id": "s1",
                            "role": "user",
                            "content": "Please always prefer bullet points. Never auto-send.",
                        },
                        {
                            "session_id": "s1",
                            "role": "user",
                            "content": "Follow-up task: email Robert@ about Q2 planning",
                        },
                    ],
                ):
                    result = dreaming.dream(session_id="dream1", apply=True)
                self.assertTrue(result["ok"])
                self.assertTrue(result["applied"])
                flash = us.read("team", "flash_task.md")["content"]
                self.assertIn("Dream", flash)

    def test_kerros_memory_tool_facade(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            patches = self._patch_base(tmp)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7]:
                import memory.unified_store as us
                from memory.kerros_memory import kerros_memory

                us._initialized = False
                st = json.loads(kerros_memory("bootstrap tool-sess"))
                self.assertTrue(st["ok"])
                listed = json.loads(kerros_memory("status"))
                self.assertTrue(listed["enabled"])
                names = {s["name"] for s in listed["stores"]}
                self.assertEqual({"org", "team", "scout"}, names)


if __name__ == "__main__":
    unittest.main()
