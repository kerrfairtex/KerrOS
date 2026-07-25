"""
runtime/scheduler.py
====================
In-process job scheduler (Phase 3).

Supports one-shot and interval jobs. Fires events on the kernel EventBus.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from runtime.event_bus import EventBus


JobFn = Callable[[], Any]


@dataclass
class ScheduledJob:
    id: str
    name: str
    interval_s: float | None = None
    run_at: float | None = None
    callback: JobFn | None = None
    enabled: bool = True
    last_run: float | None = None
    run_count: int = 0
    last_error: str = ""


@dataclass
class Scheduler:
    bus: EventBus | None = None
    _jobs: dict[str, ScheduledJob] = field(default_factory=dict)
    _thread: threading.Thread | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def schedule_once(
        self,
        name: str,
        delay_s: float,
        callback: JobFn | None = None,
        *,
        payload: dict[str, Any] | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = ScheduledJob(
            id=job_id,
            name=name,
            run_at=time.time() + max(0.0, delay_s),
            callback=callback,
        )
        with self._lock:
            self._jobs[job_id] = job
        if self.bus:
            self.bus.publish(
                "scheduler.job.scheduled",
                {"job_id": job_id, "name": name, "delay_s": delay_s, **(payload or {})},
                source="scheduler",
            )
        return job_id

    def schedule_interval(
        self,
        name: str,
        interval_s: float,
        callback: JobFn | None = None,
        *,
        payload: dict[str, Any] | None = None,
    ) -> str:
        job_id = str(uuid.uuid4())
        job = ScheduledJob(
            id=job_id,
            name=name,
            interval_s=max(0.1, interval_s),
            run_at=time.time() + max(0.1, interval_s),
            callback=callback,
        )
        with self._lock:
            self._jobs[job_id] = job
        if self.bus:
            self.bus.publish(
                "scheduler.job.scheduled",
                {
                    "job_id": job_id,
                    "name": name,
                    "interval_s": interval_s,
                    **(payload or {}),
                },
                source="scheduler",
            )
        return job_id

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.pop(job_id, None)
        if job and self.bus:
            self.bus.publish(
                "scheduler.job.cancelled",
                {"job_id": job_id, "name": job.name},
                source="scheduler",
            )
        return job is not None

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        return [
            {
                "id": j.id,
                "name": j.name,
                "interval_s": j.interval_s,
                "run_at": j.run_at,
                "enabled": j.enabled,
                "last_run": j.last_run,
                "run_count": j.run_count,
                "last_error": j.last_error,
            }
            for j in jobs
        ]

    def start(self, *, tick_s: float = 0.5) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            args=(tick_s,),
            name="kerros-scheduler",
            daemon=True,
        )
        self._thread.start()
        if self.bus:
            self.bus.publish("scheduler.started", {}, source="scheduler")

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self.bus:
            self.bus.publish("scheduler.stopped", {}, source="scheduler")

    def _loop(self, tick_s: float) -> None:
        while not self._stop.is_set():
            now = time.time()
            due: list[ScheduledJob] = []
            with self._lock:
                for job in list(self._jobs.values()):
                    if not job.enabled or job.run_at is None:
                        continue
                    if now >= job.run_at:
                        due.append(job)

            for job in due:
                self._run_job(job)

            self._stop.wait(tick_s)

    def _run_job(self, job: ScheduledJob) -> None:
        result: Any = None
        error = ""
        try:
            if job.callback:
                result = job.callback()
        except Exception as exc:
            error = str(exc)
            job.last_error = error

        job.last_run = time.time()
        job.run_count += 1

        if self.bus:
            self.bus.publish(
                "scheduler.job.fired",
                {
                    "job_id": job.id,
                    "name": job.name,
                    "result": str(result)[:500] if result is not None else None,
                    "error": error or None,
                },
                source="scheduler",
            )

        with self._lock:
            if job.interval_s:
                job.run_at = time.time() + job.interval_s
            else:
                self._jobs.pop(job.id, None)
