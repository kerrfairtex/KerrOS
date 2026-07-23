"""
runtime/workflows.py
====================
Workflow execution engine (Phase 3).

Runs DAGs of steps with event bus integration and decision log audit.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from runtime.event_bus import EventBus


StepFn = Callable[[dict[str, Any]], Any]


class WorkflowState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowStep:
    id: str
    action: StepFn
    depends_on: list[str] = field(default_factory=list)
    description: str = ""


@dataclass
class WorkflowDefinition:
    name: str
    steps: list[WorkflowStep]
    description: str = ""


@dataclass
class WorkflowRun:
    id: str
    workflow: str
    state: WorkflowState = WorkflowState.PENDING
    context: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] = field(default_factory=dict)
    started_at: float | None = None
    finished_at: float | None = None
    error: str = ""


@dataclass
class WorkflowEngine:
    bus: EventBus | None = None
    _definitions: dict[str, WorkflowDefinition] = field(default_factory=dict)
    _runs: dict[str, WorkflowRun] = field(default_factory=dict)

    def register(self, definition: WorkflowDefinition) -> None:
        self._definitions[definition.name] = definition
        if self.bus:
            self.bus.publish(
                "workflow.registered",
                {"name": definition.name, "steps": len(definition.steps)},
                source="workflow",
            )

    def list_workflows(self) -> list[str]:
        return sorted(self._definitions.keys())

    def run(
        self,
        name: str,
        *,
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> WorkflowRun:
        definition = self._definitions.get(name)
        if not definition:
            raise KeyError(f"workflow not found: {name}")

        run = WorkflowRun(
            id=run_id or str(uuid.uuid4()),
            workflow=name,
            context=dict(context or {}),
        )
        self._runs[run.id] = run

        if self.bus:
            self.bus.publish(
                "workflow.started",
                {"run_id": run.id, "workflow": name},
                source="workflow",
            )

        run.state = WorkflowState.RUNNING
        run.started_at = time.time()

        try:
            self._execute(definition, run)
            run.state = WorkflowState.COMPLETED
            if self.bus:
                self.bus.publish(
                    "workflow.completed",
                    {"run_id": run.id, "workflow": name, "results": run.results},
                    source="workflow",
                )
        except Exception as exc:
            run.state = WorkflowState.FAILED
            run.error = str(exc)
            if self.bus:
                self.bus.publish(
                    "workflow.failed",
                    {"run_id": run.id, "workflow": name, "error": run.error},
                    source="workflow",
                )
            raise
        finally:
            run.finished_at = time.time()

        return run

    def status(self, run_id: str) -> dict[str, Any] | None:
        run = self._runs.get(run_id)
        if not run:
            return None
        return {
            "id": run.id,
            "workflow": run.workflow,
            "state": run.state.value,
            "results": run.results,
            "error": run.error,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
        }

    def _execute(self, definition: WorkflowDefinition, run: WorkflowRun) -> None:
        completed: set[str] = set()
        steps_by_id = {s.id: s for s in definition.steps}

        while len(completed) < len(definition.steps):
            progressed = False
            for step in definition.steps:
                if step.id in completed:
                    continue
                if not all(dep in completed for dep in step.depends_on):
                    continue

                if self.bus:
                    self.bus.publish(
                        "workflow.step.started",
                        {
                            "run_id": run.id,
                            "workflow": definition.name,
                            "step": step.id,
                        },
                        source="workflow",
                    )

                ctx = {**run.context, **run.results}
                result = step.action(ctx)
                run.results[step.id] = result
                completed.add(step.id)
                progressed = True

                if self.bus:
                    self.bus.publish(
                        "workflow.step.completed",
                        {
                            "run_id": run.id,
                            "workflow": definition.name,
                            "step": step.id,
                        },
                        source="workflow",
                    )

            if not progressed:
                missing = [s.id for s in definition.steps if s.id not in completed]
                raise RuntimeError(f"workflow deadlock — unresolved steps: {missing}")

    def _topo_order(self, definition: WorkflowDefinition) -> list[WorkflowStep]:
        """Validate DAG and return topological order (unused at runtime but useful for tests)."""
        steps_by_id = {s.id: s for s in definition.steps}
        visited: set[str] = set()
        order: list[WorkflowStep] = []

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            step = steps_by_id[step_id]
            for dep in step.depends_on:
                if dep not in steps_by_id:
                    raise ValueError(f"unknown dependency {dep} for step {step_id}")
                visit(dep)
            visited.add(step_id)
            order.append(step)

        for step in definition.steps:
            visit(step.id)
        return order
