from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class Job:
    id: str
    name: str
    status: str = "queued"
    result: Any = None
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "result": str(self.result) if self.result is not None else None,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class JobManager:
    """Small in-process queue for a local single-user deployment."""

    def __init__(self, max_workers: int = 2):
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="paper-agent",
        )
        self.jobs: dict[str, Job] = {}
        self.futures: dict[str, Future[Any]] = {}
        self.lock = threading.RLock()

    def submit(self, name: str, function: Callable[[], Any]) -> Job:
        job = Job(id=f"job_{uuid4().hex}", name=name)
        with self.lock:
            self.jobs[job.id] = job

        def wrapper() -> Any:
            with self.lock:
                job.status = "running"
                job.started_at = datetime.now(UTC).isoformat()
            try:
                result = function()
                with self.lock:
                    job.result = result
                    job.status = "completed"
                return result
            except Exception as exc:
                with self.lock:
                    job.error = str(exc)
                    job.status = "failed"
                raise
            finally:
                with self.lock:
                    job.finished_at = datetime.now(UTC).isoformat()

        future = self.executor.submit(wrapper)
        with self.lock:
            self.futures[job.id] = future
        return job

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            return self.jobs.get(job_id)

    def list(self) -> list[Job]:
        with self.lock:
            return sorted(
                self.jobs.values(),
                key=lambda job: job.created_at,
                reverse=True,
            )

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            future = self.futures.get(job_id)
            job = self.jobs.get(job_id)
            if not future or not job:
                return False
            cancelled = future.cancel()
            if cancelled:
                job.status = "cancelled"
                job.finished_at = datetime.now(UTC).isoformat()
            return cancelled

    def shutdown(self, wait: bool = True) -> None:
        self.executor.shutdown(wait=wait, cancel_futures=True)
