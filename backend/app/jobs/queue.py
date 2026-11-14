"""A small durable job queue stored in SQLite, executed by a separate worker process."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy import select, update

from ..db.models import Job
from ..db.session import SessionLocal


def enqueue(db, type_: str, params: dict) -> Job:
    job = Job(type=type_, params=params)
    db.add(job)
    db.commit()
    return job


def claim_next() -> Job | None:
    with SessionLocal() as db:
        job = db.scalars(select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)).first()
        if not job:
            return None
        res = db.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(status="running", started_at=datetime.now(UTC), message="started")
        )
        db.commit()
        if res.rowcount != 1:
            return None
        db.refresh(job)
        return job


class JobContext:
    """Passed to task functions: report progress/logs, check for cancellation."""

    def __init__(self, job_id: str, min_interval: float = 0.75):
        self.job_id = job_id
        self.min_interval = min_interval
        self._last = 0.0
        self._pending_log: list[str] = []

    def log(self, msg: str) -> None:
        line = f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {msg}"
        print(f"{self.job_id}: {msg}", flush=True)
        with SessionLocal() as db:
            job = db.get(Job, self.job_id)
            job.log = (job.log + line + "\n")[-200_000:]
            job.message = msg
            db.commit()

    def progress(self, fraction: float, msg: str = "", force: bool = False) -> None:
        t = time.time()
        if not force and t - self._last < self.min_interval:
            return
        self._last = t
        with SessionLocal() as db:
            db.execute(
                update(Job)
                .where(Job.id == self.job_id)
                .values(progress=max(0.0, min(1.0, float(fraction))), message=msg or Job.message)
            )
            db.commit()

    def cancelled(self) -> bool:
        with SessionLocal() as db:
            return bool(db.scalar(select(Job.cancel_requested).where(Job.id == self.job_id)))


class Cancelled(Exception):
    pass


def finish(job_id: str, status: str, result: dict | None = None, error: str | None = None) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        job.status = status
        job.finished_at = datetime.now(UTC)
        job.result = result
        job.error = error
        if status == "succeeded":
            job.progress = 1.0
            job.message = "completed"
        db.commit()


def recover_stale() -> int:
    """Jobs left 'running' by a crashed worker are marked failed on worker start."""
    with SessionLocal() as db:
        res = db.execute(
            update(Job)
            .where(Job.status == "running")
            .values(status="failed", error="Worker stopped while the job was running", finished_at=datetime.now(UTC))
        )
        db.commit()
        return res.rowcount
