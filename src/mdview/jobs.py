"""In-process job registry for asynchronous trajectory processing.

``POST /api/prepare`` hands the heavy MDAnalysis work to this registry instead of
blocking the request; the browser polls ``GET /api/prepare/{job_id}`` for progress
and the result. Jobs are keyed by the same content-address as
:func:`mdview.process.prepare`, so two identical in-flight requests share one job.

A single worker thread runs the queue: trajectory processing is disk/CPU heavy and
mdview targets one workstation, so serializing is safer than thrashing. Cache hits
never reach here — the endpoint returns them synchronously — so the queue only ever
holds real work.
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

# work(progress) does the processing and returns the response payload dict.
Work = Callable[[Callable[[int, int], None]], dict]

_MAX_WORKERS = 1
# Keep at most this many finished jobs for late polls, then forget the oldest.
_KEEP_FINISHED = 64


class Job:
    """One processing request: its status, progress, and result/error."""

    __slots__ = ("id", "key", "status", "current", "total", "result", "error")

    def __init__(self, key: str) -> None:
        self.id = uuid.uuid4().hex
        self.key = key
        self.status = "queued"  # queued | running | done | error
        self.current = 0
        self.total = 0
        self.result: dict | None = None
        self.error: str | None = None

    def as_dict(self) -> dict:
        """JSON view for the status endpoint (result fields merged in when done)."""
        payload = {
            "job_id": self.id,
            "status": self.status,
            "current": self.current,
            "total": self.total,
        }
        if self.status == "done" and self.result is not None:
            payload.update(self.result)
        if self.status == "error":
            payload["detail"] = self.error or "processing failed"
        return payload


class JobRegistry:
    """Thread-backed registry of processing jobs, deduplicated by cache key."""

    def __init__(self, max_workers: int = _MAX_WORKERS) -> None:
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="mdview-prepare"
        )
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: dict[str, Job] = {}  # key -> queued/running job

    def submit(self, key: str, work: Work) -> Job:
        """Return the in-flight job for ``key``, or start a new one.

        ``work(progress)`` performs the processing, calling ``progress(current,
        total)`` as it goes, and returns the response payload dict.
        """
        with self._lock:
            existing = self._active.get(key)
            if existing is not None:
                return existing
            job = Job(key)
            self._jobs[job.id] = job
            self._active[key] = job
            self._prune_locked()
        self._pool.submit(self._run, job, work)
        return job

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def _run(self, job: Job, work: Work) -> None:
        job.status = "running"

        def progress(current: int, total: int) -> None:
            job.current = current
            job.total = total

        try:
            job.result = work(progress)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001 - surfaced to the client as detail
            job.error = str(exc)
            job.status = "error"
        finally:
            with self._lock:
                if self._active.get(job.key) is job:
                    del self._active[job.key]

    def _prune_locked(self) -> None:
        """Forget the oldest finished jobs beyond the keep limit (dict is ordered)."""
        finished = [j for j in self._jobs.values() if j.status in ("done", "error")]
        excess = len(finished) - _KEEP_FINISHED
        for job in finished[:max(0, excess)]:
            self._jobs.pop(job.id, None)
