"""ADR-053: Unsloth LoRA → GGUF soft export (Phase D)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.llm.unsloth_finetune import (
    UnslothFinetuneConfig,
    UnslothFinetuneService,
    build_unsloth_finetune,
)
from tools import call_tool


class UnslothFinetuneTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(UnslothFinetuneConfig.from_mapping({}).enabled)
        self.assertIsNone(build_unsloth_finetune({}))

    def test_fake_plan_never_provisioned(self):
        svc = UnslothFinetuneService(
            cfg=UnslothFinetuneConfig(enabled=True, backend="fake", allow_train=True)
        )
        plan = svc.plan()
        self.assertTrue(plan["ok"])
        self.assertTrue(plan["dry_run"])
        self.assertFalse(plan["provisioned_production"])
        self.assertIn("quantize_Q4_K_M", plan["steps"])

    def test_train_and_export_stay_dry_without_gates(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = UnslothFinetuneConfig(
                enabled=True,
                backend="fake",
                allow_train=True,
                allow_export=True,
                output_dir=str(Path(td) / "out"),
                gguf_out=str(Path(td) / "qwen0.5b-q4.gguf"),
            )
            svc = UnslothFinetuneService(cfg=cfg)
            trained = svc.train()
            self.assertTrue(trained.get("dry_run"))
            self.assertFalse(trained["provisioned_production"])
            exported = svc.export()
            self.assertTrue(exported.get("dry_run"))
            self.assertFalse(exported["provisioned_production"])

    def test_soft_train_intent_with_unsloth_backend(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = UnslothFinetuneConfig(
                enabled=True,
                backend="unsloth",
                allow_train=True,
                output_dir=str(Path(td) / "out"),
            )
            svc = UnslothFinetuneService(cfg=cfg)
            # Without HAS_UNSLOTH this stays dry_run; with it writes intent.
            out = svc.train()
            self.assertFalse(out["provisioned_production"])
            self.assertIn(out["status"], ("planned", "soft_intent"))


class FinetuneClawToolsTest(unittest.TestCase):
    def test_finetune_plan_tool(self):
        with patch.dict("os.environ", {"KERROS_FINETUNE": "1"}, clear=False):
            result = call_tool("finetune_plan", {})
            self.assertTrue(result.ok)
            self.assertIn("planned", result.output)
            self.assertFalse(result.data.get("provisioned_production", True))


if __name__ == "__main__":
    unittest.main()
