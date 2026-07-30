"""
runtime/agent_jobs.py
=====================
Persisted agent cron jobs (ADR-062).

Jobs live in data/agent_cron/jobs.json. Schedule is a 5-field cron expression
parsed by runtime.cron. Execution records prompts for the REPL/daemon to run;
this module does not spawn LLMs by itself.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from runtime.cron import CronError, _matches as cron_matches, parse_cron

BASE = Path(os.path.expanduser("~/offline_ai"))
JOBS_DIR = BASE / "data" / "agent_cron"
JOBS_FILE = JOBS_DIR / "jobs.json"
_lock = threading.RLock()


def _ensure() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not JOBS_FILE.is_file():
        JOBS_FILE.write_text("[]\n", encoding="utf-8")


def _load() -> list[dict[str, Any]]:
    _ensure()
    try:
        data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(jobs: list[dict[str, Any]]) -> None:
    _ensure()
    tmp = JOBS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, indent=2) + "\n", encoding="utf-8")
    tmp.replace(JOBS_FILE)


def list_jobs(*, include_paused: bool = True) -> list[dict[str, Any]]:
    with _lock:
        jobs = _load()
    if include_paused:
        return jobs
    return [j for j in jobs if not j.get("paused")]


def create_job(name: str, schedule: str, prompt: str) -> dict[str, Any]:
    name = (name or "").strip() or "job"
    prompt = (prompt or "").strip()
    schedule = (schedule or "").strip()
    if not prompt:
        return {"ok": False, "error": "prompt required"}
    try:
        cron_parse = parse_cron  # alias for clarity in create_job
        cron_parse(schedule)
    except CronError as exc:
        return {"ok": False, "error": f"bad schedule: {exc}"}
    # light injection scan
    low = prompt.lower()
    if "ignore previous instructions" in low or "system prompt override" in low:
        return {"ok": False, "error": "prompt blocked by safety scan"}
    job = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "schedule": schedule,
        "prompt": prompt,
        "paused": False,
        "created_at": time.time(),
        "last_run_at": None,
        "run_count": 0,
    }
    with _lock:
        jobs = _load()
        jobs.append(job)
        _save(jobs)
    return {"ok": True, "job": job}


def pause_job(job_id: str) -> dict[str, Any]:
    return _set_paused(job_id, True)


def resume_job(job_id: str) -> dict[str, Any]:
    return _set_paused(job_id, False)


def _set_paused(job_id: str, paused: bool) -> dict[str, Any]:
    with _lock:
        jobs = _load()
        for j in jobs:
            if j.get("id") == job_id or j.get("name") == job_id:
                j["paused"] = paused
                _save(jobs)
                return {"ok": True, "job": j}
    return {"ok": False, "error": "job not found"}


def remove_job(job_id: str) -> dict[str, Any]:
    with _lock:
        jobs = _load()
        keep = [j for j in jobs if j.get("id") != job_id and j.get("name") != job_id]
        if len(keep) == len(jobs):
            return {"ok": False, "error": "job not found"}
        _save(keep)
    return {"ok": True}


def due_jobs(now: Optional[float] = None) -> list[dict[str, Any]]:
    """Return non-paused jobs whose cron matches the current local minute."""
    import datetime as _dt

    ts = now or time.time()
    dt = _dt.datetime.fromtimestamp(ts)
    out = []
    with _lock:
        for j in _load():
            if j.get("paused"):
                continue
            try:
                expr = parse_cron(j["schedule"])
            except CronError:
                continue
            if cron_matches(expr, dt):
                # skip if already run this minute
                last = j.get("last_run_at")
                if last and abs(ts - float(last)) < 50:
                    continue
                out.append(j)
    return out


def mark_run(job_id: str) -> None:
    with _lock:
        jobs = _load()
        for j in jobs:
            if j.get("id") == job_id:
                j["last_run_at"] = time.time()
                j["run_count"] = int(j.get("run_count") or 0) + 1
                _save(jobs)
                return
