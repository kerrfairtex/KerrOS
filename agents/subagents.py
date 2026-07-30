"""
agents/subagents.py
====================
Hermes-style subagent delegation (ADR-061) — native KerrOS port.

Default-off. Enable with KERROS_SUBAGENTS=1.
Concurrency capped at 2 and reduced further when available RAM is low.
Each child uses a restricted agent set and still goes through normal
tool gates when those agents call tools.
"""

from __future__ import annotations

import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Optional

ALLOWED_AGENTS = frozenset({"knowledge", "research", "code", "react"})
DEFAULT_MAX_WORKERS = 2
# Require this much *available* MiB to allow N workers.
RAM_FOR_ONE_MIB = 1024
RAM_FOR_TWO_MIB = 2048

# Live AdaptiveEngine (or compatible) bound by the CLI so router tools
# do not fall back to a no-op stub when KerrOS is already chatting.
_bound_engine: Any = None
_bound_lock = threading.Lock()


def bind_engine(engine: Any) -> None:
    """Bind the REPL AdaptiveEngine for delegate_task tool dispatches."""
    global _bound_engine
    with _bound_lock:
        _bound_engine = engine


def get_bound_engine() -> Any:
    with _bound_lock:
        return _bound_engine


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def available_ram_mib() -> Optional[int]:
    """Return MemAvailable MiB from /proc/meminfo, or None if unknown."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb // 1024
    except Exception:
        return None
    return None


def is_subagents_enabled(cfg: Optional[dict[str, Any]] = None) -> bool:
    env = os.environ.get("KERROS_SUBAGENTS")
    if env is not None:
        return _truthy(env)
    data = cfg or {}
    block = data.get("subagents") if isinstance(data.get("subagents"), dict) else {}
    return _truthy(block.get("enabled", False))


def resolve_max_workers(cfg: Optional[dict[str, Any]] = None) -> int:
    data = cfg or {}
    block = data.get("subagents") if isinstance(data.get("subagents"), dict) else {}
    wanted = int(block.get("max_workers") or os.environ.get("KERROS_SUBAGENTS_MAX") or DEFAULT_MAX_WORKERS)
    wanted = max(1, min(wanted, DEFAULT_MAX_WORKERS))
    avail = available_ram_mib()
    if avail is None:
        return min(wanted, 1)  # unknown RAM → serial-safe default of 1 when enabled
    if avail >= RAM_FOR_TWO_MIB:
        return wanted
    if avail >= RAM_FOR_ONE_MIB:
        return 1
    return 0  # too little RAM


@dataclass
class SubagentResult:
    agent: str
    task: str
    ok: bool
    output: str
    error: str = ""


@dataclass
class DelegationPlan:
    enabled: bool
    max_workers: int
    ram_mib: Optional[int]
    jobs: list[dict[str, str]] = field(default_factory=list)
    note: str = ""


def _run_one(agent: str, task: str, engine: Any) -> SubagentResult:
    name = (agent or "knowledge").strip().lower()
    if name not in ALLOWED_AGENTS:
        return SubagentResult(
            agent=name,
            task=task,
            ok=False,
            output="",
            error=f"agent not allowlisted for subagents: {name}",
        )
    try:
        if name == "code":
            from agents.code import CodeAgent

            out = CodeAgent(engine).run(task, stream=False)
        elif name == "research":
            from agents.research import ResearchAgent

            out = ResearchAgent(engine).run(task, stream=False)
        elif name == "react":
            from agents.react import ReactAgent

            out = ReactAgent(engine).run(task, stream=False)
        else:
            from agents.knowledge import KnowledgeAgent

            out = KnowledgeAgent(engine).run(task, stream=False)
        text = out if isinstance(out, str) else str(out)
        return SubagentResult(agent=name, task=task, ok=True, output=text[:4000])
    except Exception as exc:
        return SubagentResult(agent=name, task=task, ok=False, output="", error=str(exc))


def parse_delegate_args(raw: str) -> list[dict[str, str]]:
    """Parse 'knowledge: q1 || research: q2' or JSON-ish lines."""
    text = (raw or "").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split("||") if p.strip()]
    jobs: list[dict[str, str]] = []
    for part in parts:
        if ":" in part:
            agent, task = part.split(":", 1)
            jobs.append({"agent": agent.strip().lower(), "task": task.strip()})
        else:
            jobs.append({"agent": "knowledge", "task": part})
    return jobs


def plan_delegation(
    jobs: list[dict[str, str]],
    *,
    cfg: Optional[dict[str, Any]] = None,
) -> DelegationPlan:
    enabled = is_subagents_enabled(cfg)
    ram = available_ram_mib()
    workers = resolve_max_workers(cfg) if enabled else 0
    note = ""
    if not enabled:
        note = "subagents disabled — set KERROS_SUBAGENTS=1"
    elif workers == 0:
        note = f"insufficient RAM (available={ram} MiB) — refusing parallel subagents"
    return DelegationPlan(
        enabled=enabled and workers > 0,
        max_workers=max(workers, 0),
        ram_mib=ram,
        jobs=jobs,
        note=note,
    )


def delegate_tasks(
    jobs: list[dict[str, str]],
    engine: Any,
    *,
    cfg: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Run independent agent jobs with capped concurrency. Converges results."""
    plan = plan_delegation(jobs, cfg=cfg)
    if not plan.jobs:
        return {"ok": False, "error": "no jobs", "plan": plan.__dict__, "results": []}
    if not plan.enabled:
        # Soft fallback: run first job serially via knowledge if disabled,
        # but report clearly — do not silently pretend parallelism.
        return {
            "ok": False,
            "error": plan.note or "subagents unavailable",
            "plan": plan.__dict__,
            "results": [],
            "production_parallel": False,
        }

    results: list[SubagentResult] = []
    lock = threading.Lock()

    def _job(j: dict[str, str]) -> SubagentResult:
        r = _run_one(j.get("agent", "knowledge"), j.get("task", ""), engine)
        with lock:
            results.append(r)
        return r

    with ThreadPoolExecutor(max_workers=plan.max_workers) as pool:
        futs = [pool.submit(_job, j) for j in plan.jobs[:8]]
        for fut in as_completed(futs):
            try:
                fut.result()
            except Exception:
                pass

    # Stable order by original jobs
    by_task = {(r.agent, r.task): r for r in results}
    ordered: list[dict[str, Any]] = []
    for j in plan.jobs:
        key = (j.get("agent", "knowledge"), j.get("task", ""))
        r = by_task.get(key)
        if r is None:
            continue
        ordered.append(
            {
                "agent": r.agent,
                "task": r.task,
                "ok": r.ok,
                "output": r.output,
                "error": r.error,
            }
        )

    summary_lines = ["[delegate] converged results:"]
    for r in ordered:
        status = "ok" if r["ok"] else f"fail:{r.get('error')}"
        snippet = (r.get("output") or "")[:240].replace("\n", " ")
        summary_lines.append(f"- {r['agent']}: {status} — {snippet}")

    return {
        "ok": all(r["ok"] for r in ordered) if ordered else False,
        "plan": {
            "enabled": plan.enabled,
            "max_workers": plan.max_workers,
            "ram_mib": plan.ram_mib,
            "jobs": plan.jobs,
            "note": plan.note,
        },
        "results": ordered,
        "summary": "\n".join(summary_lines),
        "production_parallel": True,
    }
