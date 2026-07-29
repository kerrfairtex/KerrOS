"""
runtime/workflows.py
====================
Workflow execution engine (Phase 3).

Runs DAGs of steps with event bus integration, decision log audit, and
optional SQLite persistence so incomplete runs can resume after restart.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

from runtime.event_bus import EventBus
from runtime.workflow_store import WorkflowRunStore

if TYPE_CHECKING:
    from kernel.capability_registry import CapabilityRegistry


StepFn = Callable[[dict[str, Any]], Any]
WORKFLOW_NAME_RE = re.compile(r"^[a-z0-9_.:-]{2,64}$")
WORKFLOW_STEP_ID_RE = re.compile(r"^[a-z0-9_.:-]{1,64}$")


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
    catalog_path: Path | None = None
    store_path: Path | None = None
    capability_registry: "CapabilityRegistry | None" = None
    _definitions: dict[str, WorkflowDefinition] = field(default_factory=dict)
    _runs: dict[str, WorkflowRun] = field(default_factory=dict)
    _catalog: dict[str, dict[str, Any]] = field(default_factory=dict)
    _store: WorkflowRunStore | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.store_path is not None:
            self._store = WorkflowRunStore(Path(self.store_path))

    def register(self, definition: WorkflowDefinition) -> None:
        self._validate_definition(definition)
        self._definitions[definition.name] = definition
        self._persist_definition(definition)
        if self.capability_registry is not None:
            try:
                self.capability_registry.register(
                    name=f"workflow:{definition.name}",
                    kind="workflow",
                    permissions=["standard"],
                    dependencies=[],
                    setup_required=False,
                    setup_state="ready",
                    metadata={
                        "description": definition.description,
                        "steps": len(definition.steps),
                    },
                )
            except Exception:
                pass
        if self.bus:
            self.bus.publish(
                "workflow.registered",
                {"name": definition.name, "steps": len(definition.steps)},
                source="workflow",
            )

    def list_workflows(self) -> list[str]:
        return sorted(self._definitions.keys())

    def load_yaml_dir(self, directory: Path | str) -> list[str]:
        """Register workflows from ``*.yaml`` / ``*.yml`` under directory."""
        from runtime.workflow_yaml import load_workflows_dir

        return load_workflows_dir(self, Path(directory))

    def load_yaml_file(self, path: Path | str) -> list[str]:
        """Register workflow(s) from a single YAML file."""
        from runtime.workflow_yaml import load_workflow_file

        names: list[str] = []
        for definition in load_workflow_file(Path(path), bus=self.bus):
            self.register(definition)
            names.append(definition.name)
        return names

    def get_definition(self, name: str) -> WorkflowDefinition | None:
        return self._definitions.get(name)

    def list_catalog(self) -> list[dict[str, Any]]:
        self._load_catalog()
        return [self._catalog[name] for name in sorted(self._catalog.keys())]

    def list_runs(
        self,
        *,
        limit: int = 20,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent persisted runs (falls back to in-memory if no store)."""
        if self._store is not None:
            return self._store.list_recent(limit=limit, state=state)
        runs = sorted(
            self._runs.values(),
            key=lambda r: r.finished_at or r.started_at or 0,
            reverse=True,
        )
        out = []
        for run in runs:
            if state and run.state.value != state:
                continue
            out.append(self.status(run.id) or {})
            if len(out) >= limit:
                break
        return out

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
        self._checkpoint(run, completed_steps=[])

        try:
            self._execute(definition, run, completed=set())
            run.state = WorkflowState.COMPLETED
            run.error = ""
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
            self._checkpoint(run, completed_steps=list(run.results.keys()))

        return run

    def resume(self, run_id: str) -> WorkflowRun:
        """Continue a pending/running/failed run, skipping completed steps.

        Requires the workflow definition to still be registered (callables are
        not stored in SQLite — only JSON-serializable step results).
        """
        run = self._load_run(run_id)
        if run is None:
            raise KeyError(f"workflow run not found: {run_id}")
        if run.state == WorkflowState.COMPLETED:
            raise ValueError(f"workflow run already completed: {run_id}")

        definition = self._definitions.get(run.workflow)
        if not definition:
            raise KeyError(
                f"workflow definition not registered for resume: {run.workflow}"
            )

        completed = set(run.results.keys())
        # Prefer store's completed_steps if present and richer.
        stored = self._store.get(run_id) if self._store else None
        if stored:
            completed |= set(stored.get("completed_steps") or [])

        run.state = WorkflowState.RUNNING
        run.error = ""
        run.finished_at = None
        if run.started_at is None:
            run.started_at = time.time()
        self._runs[run.id] = run
        self._checkpoint(run, completed_steps=list(completed))

        if self.bus:
            self.bus.publish(
                "workflow.started",
                {"run_id": run.id, "workflow": run.workflow, "resume": True},
                source="workflow",
            )

        try:
            self._execute(definition, run, completed=completed)
            run.state = WorkflowState.COMPLETED
            run.error = ""
            if self.bus:
                self.bus.publish(
                    "workflow.completed",
                    {
                        "run_id": run.id,
                        "workflow": run.workflow,
                        "results": run.results,
                        "resume": True,
                    },
                    source="workflow",
                )
        except Exception as exc:
            run.state = WorkflowState.FAILED
            run.error = str(exc)
            if self.bus:
                self.bus.publish(
                    "workflow.failed",
                    {
                        "run_id": run.id,
                        "workflow": run.workflow,
                        "error": run.error,
                        "resume": True,
                    },
                    source="workflow",
                )
            raise
        finally:
            run.finished_at = time.time()
            self._checkpoint(run, completed_steps=list(run.results.keys()))

        return run

    def status(self, run_id: str) -> dict[str, Any] | None:
        run = self._runs.get(run_id)
        if run is None and self._store is not None:
            row = self._store.get(run_id)
            if not row:
                return None
            return {
                "id": row["id"],
                "workflow": row["workflow"],
                "state": row["state"],
                "results": row["results"],
                "completed_steps": row.get("completed_steps") or [],
                "error": row["error"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "context": row.get("context") or {},
            }
        if not run:
            return None
        return {
            "id": run.id,
            "workflow": run.workflow,
            "state": run.state.value,
            "results": run.results,
            "completed_steps": list(run.results.keys()),
            "error": run.error,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "context": run.context,
        }

    def _load_run(self, run_id: str) -> WorkflowRun | None:
        if run_id in self._runs:
            return self._runs[run_id]
        if self._store is None:
            return None
        row = self._store.get(run_id)
        if not row:
            return None
        run = WorkflowRun(
            id=row["id"],
            workflow=row["workflow"],
            state=WorkflowState(row["state"]),
            context=dict(row.get("context") or {}),
            results=dict(row.get("results") or {}),
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            error=row.get("error") or "",
        )
        self._runs[run.id] = run
        return run

    def _checkpoint(
        self,
        run: WorkflowRun,
        *,
        completed_steps: list[str] | None = None,
    ) -> None:
        if self._store is None:
            return
        steps = (
            list(completed_steps)
            if completed_steps is not None
            else list(run.results.keys())
        )
        try:
            self._store.upsert(
                run_id=run.id,
                workflow=run.workflow,
                state=run.state.value,
                context=run.context,
                results=run.results,
                completed_steps=steps,
                error=run.error,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        except Exception:
            # Persistence must not crash the workflow path.
            pass

    def _execute(
        self,
        definition: WorkflowDefinition,
        run: WorkflowRun,
        *,
        completed: set[str] | None = None,
    ) -> None:
        done: set[str] = set(completed or ())
        # Ensure results already recorded for resumed steps.
        for step_id in list(done):
            if step_id not in run.results:
                run.results[step_id] = None

        while len(done) < len(definition.steps):
            progressed = False
            for step in definition.steps:
                if step.id in done:
                    continue
                if not all(dep in done for dep in step.depends_on):
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
                done.add(step.id)
                progressed = True
                self._checkpoint(run, completed_steps=list(done))

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
                missing = [s.id for s in definition.steps if s.id not in done]
                raise RuntimeError(f"workflow deadlock - unresolved steps: {missing}")

    def _topo_order(self, definition: WorkflowDefinition) -> list[WorkflowStep]:
        """Validate DAG and return topological order (unused at runtime but useful for tests)."""
        steps_by_id = {s.id: s for s in definition.steps}
        visited: set[str] = set()
        visiting: set[str] = set()
        order: list[WorkflowStep] = []

        def visit(step_id: str) -> None:
            if step_id in visited:
                return
            if step_id in visiting:
                raise ValueError(
                    f"workflow cycle detected in '{definition.name}' at step '{step_id}'"
                )
            step = steps_by_id[step_id]
            visiting.add(step_id)
            for dep in step.depends_on:
                if dep not in steps_by_id:
                    raise ValueError(f"unknown dependency {dep} for step {step_id}")
                visit(dep)
            visiting.remove(step_id)
            visited.add(step_id)
            order.append(step)

        for step in definition.steps:
            visit(step.id)
        return order

    def _validate_definition(self, definition: WorkflowDefinition) -> None:
        if not WORKFLOW_NAME_RE.match(definition.name):
            raise ValueError(f"workflow name must match {WORKFLOW_NAME_RE.pattern}")
        step_ids = set()
        for step in definition.steps:
            if not WORKFLOW_STEP_ID_RE.match(step.id):
                raise ValueError(f"invalid workflow step id: {step.id}")
            if step.id in step_ids:
                raise ValueError(f"duplicate workflow step id: {step.id}")
            step_ids.add(step.id)
        self._topo_order(definition)

    def _load_catalog(self) -> None:
        if not self.catalog_path:
            return
        if self._catalog:
            return
        if not self.catalog_path.exists():
            self._catalog = {}
            return
        try:
            data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._catalog = data
        except Exception:
            self._catalog = {}

    def _persist_definition(self, definition: WorkflowDefinition) -> None:
        if not self.catalog_path:
            return
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_catalog()
        payload = {
            "name": definition.name,
            "description": definition.description,
            "steps": [
                {
                    "id": s.id,
                    "depends_on": list(s.depends_on),
                    "description": s.description,
                    "action": getattr(s.action, "__name__", repr(s.action)),
                }
                for s in definition.steps
            ],
            "updated_at": time.time(),
        }
        existing = self._catalog.get(definition.name)
        if existing:
            unchanged = (
                existing.get("name") == payload["name"]
                and existing.get("description") == payload["description"]
                and existing.get("steps") == payload["steps"]
            )
            if unchanged:
                return
        self._catalog[definition.name] = payload
        self.catalog_path.write_text(
            json.dumps(self._catalog, indent=2, sort_keys=True),
            encoding="utf-8",
        )
