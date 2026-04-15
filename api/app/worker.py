"""BullMQ consumer loop. Run with: `uv run python -m app.worker`.

Delegates the actual work to `app.pipeline.process_meeting`. The worker
itself is intentionally thin so tests can target the pipeline directly.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any

from bullmq import Job, Worker

from app.config import get_settings
from app.pipeline import process_meeting
from app.queue import JOB_NAME, get_queue_name

logger = logging.getLogger(__name__)


async def _process(job: Job, _job_token: str) -> dict[str, Any]:
    """BullMQ processor — must be async; runs the sync pipeline in a thread."""
    if job.name != JOB_NAME:
        logger.warning("Ignoring unknown job name: %s", job.name)
        return {"skipped": True}

    meeting_id = job.data.get("meeting_id")
    if not meeting_id:
        raise ValueError("Job payload missing 'meeting_id'")

    await asyncio.to_thread(process_meeting, meeting_id)
    return {"meeting_id": meeting_id, "ok": True}


def build_worker(queue_name: str | None = None) -> Worker:
    name = queue_name or get_queue_name()
    return Worker(name, _process, {"connection": get_settings().redis_url})


async def run() -> None:
    logging.basicConfig(level=get_settings().log_level.upper())
    worker = build_worker()
    logger.info("Worker listening on queue '%s'", get_queue_name())

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    logger.info("Shutting down worker")
    await worker.close()


if __name__ == "__main__":
    asyncio.run(run())
