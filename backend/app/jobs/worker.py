"""Worker process: ``python -m app.jobs.worker``. Runs queued jobs one at a time."""

from __future__ import annotations

import signal
import time
import traceback

from ..db.init import init_db
from .queue import Cancelled, JobContext, claim_next, finish, recover_stale
from .tasks import TASKS, on_task_failed

_running = True


def _stop(*_):
    global _running
    _running = False


def run_job(job) -> None:
    ctx = JobContext(job.id)
    fn = TASKS.get(job.type)
    if fn is None:
        finish(job.id, "failed", error=f"Unknown job type {job.type}")
        return
    try:
        result = fn(job.params, ctx)
        finish(job.id, "succeeded", result=result)
    except Cancelled:
        on_task_failed(job.type, job.params, "cancelled")
        finish(job.id, "cancelled", error="Cancelled by user")
    except Exception as e:  # report every failure to the UI with its traceback
        tb = traceback.format_exc()
        ctx.log(f"ERROR: {e}")
        on_task_failed(job.type, job.params, "failed", str(e))
        finish(job.id, "failed", error=f"{e}\n\n{tb}")


def main(poll_seconds: float = 1.0, once: bool = False) -> None:
    init_db()
    n = recover_stale()
    if n:
        print(f"Marked {n} stale running job(s) as failed")
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print("Sylva worker ready", flush=True)
    while _running:
        job = claim_next()
        if job is None:
            if once:
                return
            time.sleep(poll_seconds)
            continue
        print(f"Running {job.type} {job.id}", flush=True)
        run_job(job)


if __name__ == "__main__":
    main()
