"""ADR-062 agent cron jobs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AgentJobsTest(unittest.TestCase):
    def test_create_list_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("runtime.agent_jobs.BASE", base):
                with patch("runtime.agent_jobs.JOBS_DIR", base / "data" / "agent_cron"):
                    with patch(
                        "runtime.agent_jobs.JOBS_FILE",
                        base / "data" / "agent_cron" / "jobs.json",
                    ):
                        from runtime import agent_jobs as aj

                        out = aj.create_job("daily", "0 9 * * *", "summarize inbox")
                        self.assertTrue(out["ok"])
                        jobs = aj.list_jobs()
                        self.assertEqual(len(jobs), 1)
                        rem = aj.remove_job(jobs[0]["id"])
                        self.assertTrue(rem["ok"])

    def test_rejects_bad_cron(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with patch("runtime.agent_jobs.BASE", base):
                with patch("runtime.agent_jobs.JOBS_DIR", base / "data" / "agent_cron"):
                    with patch(
                        "runtime.agent_jobs.JOBS_FILE",
                        base / "data" / "agent_cron" / "jobs.json",
                    ):
                        from runtime import agent_jobs as aj

                        out = aj.create_job("x", "not a cron", "hello")
                        self.assertFalse(out["ok"])


if __name__ == "__main__":
    unittest.main()
