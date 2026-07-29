"""YAML tool/LLM workflow action tests (ADR-013)."""

from __future__ import annotations

import unittest

from runtime.event_bus import EventBus
from runtime.workflow_yaml import (
    WorkflowActionContext,
    WorkflowYamlError,
    action_context_from_config,
    parse_workflow_yaml,
)
from runtime.workflows import WorkflowEngine, WorkflowState
from kernel.boot import boot, shutdown


class ToolLlmActionTest(unittest.TestCase):
    def test_tool_action_with_injected_runner(self):
        calls = []

        def fake_tool(name, args):
            calls.append((name, args))
            return f"ok:{args}"

        svc = WorkflowActionContext(
            bus=EventBus(),
            run_tool=fake_tool,
            allowed_tools=frozenset({"calc"}),
        )
        defs = parse_workflow_yaml(
            """
name: test.tool
steps:
  - id: expr
    action: set
    params: { value: "1+1" }
  - id: out
    action: tool
    depends_on: [expr]
    params: { tool: calc, args: "{{ expr }}" }
""",
            services=svc,
        )
        engine = WorkflowEngine(bus=svc.bus, action_context=svc)
        engine.register(defs[0])
        run = engine.run("test.tool")
        self.assertEqual(run.state, WorkflowState.COMPLETED)
        self.assertEqual(calls, [("calc", "1+1")])
        self.assertEqual(run.results["out"], "ok:1+1")

    def test_tool_not_on_allowlist(self):
        svc = WorkflowActionContext(
            run_tool=lambda n, a: "nope",
            allowed_tools=frozenset({"calc"}),
        )
        defs = parse_workflow_yaml(
            """
name: test.deny
steps:
  - id: x
    action: tool
    params: { tool: bash, args: "echo hi" }
""",
            services=svc,
        )
        engine = WorkflowEngine(action_context=svc)
        engine.register(defs[0])
        with self.assertRaises(PermissionError):
            engine.run("test.deny")

    def test_llm_action_injected(self):
        def fake_llm(prompt, system=None, history=None, max_tokens=1024, **kwargs):
            return f"echo:{prompt}:{system}:{max_tokens}"

        svc = WorkflowActionContext(llm_complete=fake_llm, allow_llm=True)
        defs = parse_workflow_yaml(
            """
name: test.llm
steps:
  - id: name
    action: set
    params: { value: KerrOS }
  - id: ans
    action: llm
    depends_on: [name]
    params:
      prompt: "hi {{ name }}"
      system: "sys"
      max_tokens: 16
""",
            services=svc,
        )
        engine = WorkflowEngine(action_context=svc)
        engine.register(defs[0])
        run = engine.run("test.llm")
        self.assertEqual(run.results["ans"], "echo:hi KerrOS:sys:16")

    def test_llm_disabled(self):
        svc = WorkflowActionContext(
            llm_complete=lambda *a, **k: "x",
            allow_llm=False,
        )
        defs = parse_workflow_yaml(
            """
name: test.llm.off
steps:
  - id: a
    action: llm
    params: { prompt: "x" }
""",
            services=svc,
        )
        engine = WorkflowEngine(action_context=svc)
        engine.register(defs[0])
        with self.assertRaises(RuntimeError):
            engine.run("test.llm.off")

    def test_config_star_allowlist(self):
        ctx = action_context_from_config({"allowed_tools": ["*"]})
        self.assertIsNone(ctx.resolved_allowed_tools())


class BootToolWorkflowTest(unittest.TestCase):
    def tearDown(self):
        shutdown()

    def test_boot_registers_and_runs_demo_tool_calc(self):
        shutdown()
        boot()
        from kernel import resolve

        wf = resolve("workflow_engine")
        self.assertIn("demo.tool_calc", wf.list_workflows())
        self.assertIn("demo.llm_echo", wf.list_workflows())
        run = wf.run("demo.tool_calc")
        self.assertEqual(run.state, WorkflowState.COMPLETED)
        self.assertIn("= 4", str(run.results.get("result")))
        shutdown()


if __name__ == "__main__":
    unittest.main()
