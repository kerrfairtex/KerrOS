"""Workflow YAML definition tests (ADR-010)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.event_bus import EventBus
from runtime.workflow_yaml import (
    WorkflowYamlError,
    load_workflows_dir,
    parse_workflow_yaml,
)
from runtime.workflows import WorkflowEngine, WorkflowState
from kernel.boot import boot, shutdown


DEMO_YAML = """
name: test.hello
description: unit demo
steps:
  - id: a
    action: set
    params:
      value: hi
  - id: b
    action: template
    depends_on: [a]
    params:
      template: "{{ a }} there"
"""


class ParseWorkflowYamlTest(unittest.TestCase):
    def test_parse_and_run(self):
        bus = EventBus()
        defs = parse_workflow_yaml(DEMO_YAML, bus=bus)
        self.assertEqual(len(defs), 1)
        engine = WorkflowEngine(bus=bus)
        engine.register(defs[0])
        run = engine.run("test.hello")
        self.assertEqual(run.state, WorkflowState.COMPLETED)
        self.assertEqual(run.results["a"], "hi")
        self.assertEqual(run.results["b"], "hi there")

    def test_publish_action(self):
        bus = EventBus()
        seen = []
        bus.subscribe("wf.ping", lambda e: seen.append(e.payload))
        defs = parse_workflow_yaml(
            """
name: test.publish
steps:
  - id: go
    action: publish
    params:
      topic: wf.ping
      payload: {ok: true}
""",
            bus=bus,
        )
        engine = WorkflowEngine(bus=bus)
        engine.register(defs[0])
        engine.run("test.publish")
        self.assertEqual(seen, [{"ok": True}])

    def test_unknown_action_rejected(self):
        with self.assertRaises(WorkflowYamlError):
            parse_workflow_yaml(
                """
name: bad.action
steps:
  - id: x
    action: eval
    params: {}
"""
            )

    def test_multi_doc_workflows_key(self):
        defs = parse_workflow_yaml(
            """
workflows:
  - name: multi.one
    steps:
      - id: a
        action: noop
  - name: multi.two
    steps:
      - id: a
        action: set
        params: {value: 1}
"""
        )
        self.assertEqual([d.name for d in defs], ["multi.one", "multi.two"])

    def test_assert_eq(self):
        engine = WorkflowEngine()
        defs = parse_workflow_yaml(
            """
name: test.assert
steps:
  - id: n
    action: set
    params: {value: 3}
  - id: check
    action: assert_eq
    depends_on: [n]
    params: {key: n, value: 3}
"""
        )
        engine.register(defs[0])
        run = engine.run("test.assert")
        self.assertTrue(run.results["check"])

    def test_load_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "one.yaml").write_text(DEMO_YAML, encoding="utf-8")
            engine = WorkflowEngine(bus=EventBus())
            names = load_workflows_dir(engine, directory)
            self.assertEqual(names, ["test.hello"])
            self.assertIn("test.hello", engine.list_workflows())


class BootLoadsYamlWorkflowsTest(unittest.TestCase):
    def tearDown(self):
        shutdown()

    def test_boot_registers_demo_workflows(self):
        shutdown()
        boot()
        from kernel import resolve

        wf = resolve("workflow_engine")
        names = wf.list_workflows()
        self.assertIn("demo.hello", names)
        self.assertIn("demo.assert", names)
        run = wf.run("demo.assert")
        self.assertEqual(run.state, WorkflowState.COMPLETED)
        shutdown()


if __name__ == "__main__":
    unittest.main()
