"""ADR-049: local LLM residual soft on-ramps (proxy / multinode / pull)."""

from __future__ import annotations

import unittest

from adapters.llm.local_llm_proxy import (
    LocalLlmProxyConfig,
    LocalLlmProxyPlanner,
    build_local_llm_proxy,
)
from adapters.llm.model_pull import (
    ModelPullConfig,
    ModelPullService,
    build_model_pull,
)
from adapters.llm.vllm_multinode import (
    VllmMultinodeConfig,
    VllmMultinodePlanner,
    build_vllm_multinode,
)


class LocalLlmProxyTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(LocalLlmProxyConfig.from_mapping({}).enabled)
        self.assertIsNone(build_local_llm_proxy({}))

    def test_fake_plan_never_production_tls(self):
        planner = LocalLlmProxyPlanner(
            cfg=LocalLlmProxyConfig(
                enabled=True,
                allow_tls=True,
                allow_live=True,
                token="dev",
            )
        )
        out = planner.plan()
        self.assertTrue(out["ok"])
        self.assertTrue(out["loopback"])
        self.assertFalse(out["production_tls"])
        self.assertFalse(out["public_bind_ok"])


class VllmMultinodeTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(VllmMultinodeConfig.from_mapping({}).enabled)
        self.assertIsNone(build_vllm_multinode({}))

    def test_fake_plan_never_cluster_ready(self):
        planner = VllmMultinodePlanner(
            cfg=VllmMultinodeConfig(enabled=True, allow_live=True, tensor_parallel=2)
        )
        out = planner.plan()
        self.assertTrue(out["ok"])
        self.assertEqual(out["node_count"], 2)
        self.assertFalse(out["cluster_ready"])


class ModelPullTest(unittest.TestCase):
    def test_default_off(self):
        self.assertFalse(ModelPullConfig.from_mapping({}).enabled)
        self.assertIsNone(build_model_pull({}))

    def test_fake_pull_never_provisioned(self):
        svc = ModelPullService(
            cfg=ModelPullConfig(
                enabled=True,
                backend="fake",
                allow_pull=True,
                models=["llama3.2"],
            )
        )
        planned = svc.plan()
        self.assertEqual(planned["status"], "planned")
        self.assertFalse(planned["provisioned_production"])
        pulled = svc.pull("llama3.2")
        self.assertTrue(pulled.get("dry_run"))
        self.assertFalse(pulled["provisioned_production"])


if __name__ == "__main__":
    unittest.main()
