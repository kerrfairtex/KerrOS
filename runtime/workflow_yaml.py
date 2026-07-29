"""
runtime/workflow_yaml.py
========================
Declarative workflow definitions from YAML (P3).

Maps YAML steps onto WorkflowEngine via a closed set of built-in actions
(no arbitrary code / eval). Callables still are not serialized to SQLite —
YAML (or Python register) must be loaded before resume.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

from runtime.event_bus import EventBus
from runtime.workflows import (
    WORKFLOW_NAME_RE,
    WorkflowDefinition,
    WorkflowEngine,
    WorkflowStep,
)

StepFn = Callable[[dict[str, Any]], Any]

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.:-]+)\s*\}\}")

BUILTIN_ACTIONS = frozenset(
    {
        "set",
        "echo",
        "get",
        "template",
        "merge",
        "publish",
        "noop",
        "assert_eq",
    }
)


class WorkflowYamlError(ValueError):
    """Invalid workflow YAML."""


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowYamlError(f"{label} must be a mapping")
    return value


def _render_templates(value: Any, ctx: dict[str, Any]) -> Any:
    """Replace ``{{ key }}`` in strings; recurse into dict/list."""
    if isinstance(value, str):
        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in ctx:
                raise KeyError(f"template key not in context: {key}")
            return str(ctx[key])

        if _TEMPLATE_RE.fullmatch(value.strip()):
            # Exact ``{{ key }}`` → raw context value (preserve type).
            m = _TEMPLATE_RE.fullmatch(value.strip())
            assert m is not None
            key = m.group(1)
            if key not in ctx:
                raise KeyError(f"template key not in context: {key}")
            return ctx[key]
        return _TEMPLATE_RE.sub(repl, value)
    if isinstance(value, list):
        return [_render_templates(v, ctx) for v in value]
    if isinstance(value, dict):
        return {k: _render_templates(v, ctx) for k, v in value.items()}
    return value


def build_builtin_action(
    name: str,
    params: Optional[dict[str, Any]] = None,
    *,
    bus: EventBus | None = None,
) -> StepFn:
    """Return a StepFn for a named built-in. Raises WorkflowYamlError if unknown."""
    action = str(name or "").strip().lower()
    if action not in BUILTIN_ACTIONS:
        raise WorkflowYamlError(
            f"unknown workflow action '{name}' "
            f"(allowed: {', '.join(sorted(BUILTIN_ACTIONS))})"
        )
    raw = dict(params or {})

    def _set(ctx: dict[str, Any]) -> Any:
        _ = ctx
        if "value" not in raw:
            raise WorkflowYamlError("set/echo action requires params.value")
        return raw["value"]

    def _get(ctx: dict[str, Any]) -> Any:
        key = raw.get("key")
        if not key:
            raise WorkflowYamlError("get action requires params.key")
        return ctx.get(str(key), raw.get("default"))

    def _template(ctx: dict[str, Any]) -> Any:
        tmpl = raw.get("template")
        if tmpl is None:
            raise WorkflowYamlError("template action requires params.template")
        return _render_templates(tmpl, ctx)

    def _merge(ctx: dict[str, Any]) -> dict[str, Any]:
        keys = raw.get("keys") or []
        if not isinstance(keys, list):
            raise WorkflowYamlError("merge action params.keys must be a list")
        out: dict[str, Any] = {}
        for key in keys:
            val = ctx.get(str(key))
            if isinstance(val, dict):
                out.update(val)
            elif val is not None:
                out[str(key)] = val
        extra = raw.get("extra")
        if isinstance(extra, dict):
            out.update(_render_templates(extra, ctx))
        return out

    def _publish(ctx: dict[str, Any]) -> dict[str, Any]:
        if bus is None:
            raise RuntimeError("publish action requires an EventBus")
        topic = str(raw.get("topic") or "").strip()
        if not topic:
            raise WorkflowYamlError("publish action requires params.topic")
        payload = _render_templates(raw.get("payload") or {}, ctx)
        if not isinstance(payload, dict):
            payload = {"value": payload}
        event = bus.publish(topic, payload, source="workflow")
        return {"topic": topic, "event_id": event.id}

    def _noop(ctx: dict[str, Any]) -> None:
        _ = ctx
        return None

    def _assert_eq(ctx: dict[str, Any]) -> bool:
        key = raw.get("key")
        if not key:
            raise WorkflowYamlError("assert_eq requires params.key")
        expected = raw.get("value")
        actual = ctx.get(str(key))
        if actual != expected:
            raise AssertionError(
                f"assert_eq failed: ctx[{key!r}]={actual!r} != {expected!r}"
            )
        return True

    handlers: dict[str, StepFn] = {
        "set": _set,
        "echo": _set,
        "get": _get,
        "template": _template,
        "merge": _merge,
        "publish": _publish,
        "noop": _noop,
        "assert_eq": _assert_eq,
    }
    fn = handlers[action]
    fn.__name__ = action  # type: ignore[attr-defined]
    fn.__workflow_action__ = action  # type: ignore[attr-defined]
    fn.__workflow_params__ = raw  # type: ignore[attr-defined]
    return fn


def definition_from_mapping(
    data: dict[str, Any],
    *,
    bus: EventBus | None = None,
    source: str = "",
) -> WorkflowDefinition:
    """Build a WorkflowDefinition from a parsed YAML mapping."""
    data = _require_mapping(data, "workflow")
    name = str(data.get("name") or "").strip()
    if not name:
        raise WorkflowYamlError(f"workflow missing name{f' in {source}' if source else ''}")
    if not WORKFLOW_NAME_RE.match(name):
        raise WorkflowYamlError(f"invalid workflow name: {name}")

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise WorkflowYamlError(f"workflow '{name}' needs a non-empty steps list")

    steps: list[WorkflowStep] = []
    for i, step_data in enumerate(steps_raw):
        step_data = _require_mapping(step_data, f"steps[{i}]")
        step_id = str(step_data.get("id") or "").strip()
        if not step_id:
            raise WorkflowYamlError(f"workflow '{name}' step[{i}] missing id")
        action_name = str(step_data.get("action") or "").strip()
        if not action_name:
            raise WorkflowYamlError(
                f"workflow '{name}' step '{step_id}' missing action"
            )
        params = step_data.get("params") or {}
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise WorkflowYamlError(
                f"workflow '{name}' step '{step_id}' params must be a mapping"
            )
        depends = step_data.get("depends_on") or []
        if isinstance(depends, str):
            depends = [depends]
        if not isinstance(depends, list):
            raise WorkflowYamlError(
                f"workflow '{name}' step '{step_id}' depends_on must be a list"
            )
        action = build_builtin_action(action_name, params, bus=bus)
        steps.append(
            WorkflowStep(
                id=step_id,
                action=action,
                depends_on=[str(d) for d in depends],
                description=str(step_data.get("description") or ""),
            )
        )

    return WorkflowDefinition(
        name=name,
        steps=steps,
        description=str(data.get("description") or ""),
    )


def parse_workflow_yaml(
    text: str,
    *,
    bus: EventBus | None = None,
    source: str = "",
) -> list[WorkflowDefinition]:
    """Parse YAML text into one or more workflow definitions."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise WorkflowYamlError(f"YAML parse error{f' in {source}' if source else ''}: {exc}") from exc

    if data is None:
        return []
    if isinstance(data, list):
        return [
            definition_from_mapping(_require_mapping(item, "workflow list item"), bus=bus, source=source)
            for item in data
        ]
    data = _require_mapping(data, "workflow document")
    if "workflows" in data:
        items = data["workflows"]
        if not isinstance(items, list):
            raise WorkflowYamlError("'workflows' must be a list")
        return [
            definition_from_mapping(_require_mapping(item, "workflows[]"), bus=bus, source=source)
            for item in items
        ]
    return [definition_from_mapping(data, bus=bus, source=source)]


def load_workflow_file(
    path: Path,
    *,
    bus: EventBus | None = None,
) -> list[WorkflowDefinition]:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    return parse_workflow_yaml(text, bus=bus, source=str(path))


def load_workflows_dir(
    engine: WorkflowEngine,
    directory: Path,
    *,
    patterns: tuple[str, ...] = ("*.yaml", "*.yml"),
) -> list[str]:
    """Load and register all workflow YAML files under directory. Returns names."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    registered: list[str] = []
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(sorted(directory.glob(pattern)))
    # De-dupe while preserving order
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        for definition in load_workflow_file(path, bus=engine.bus):
            engine.register(definition)
            registered.append(definition.name)
    return registered
